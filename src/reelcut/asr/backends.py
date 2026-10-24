"""The `ASRBackend` protocol (guide §8 Phase 4) and its mlx-whisper and faster-whisper backends.

Only the worker process imports this module: loading either backend pulls in the model runtime.
Both decode only the windows that hold speech (`speech.windows`), with Whisper's hallucination
guards; the worker then fits the words to the VAD regions.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
import soundfile

from reelcut.analysis.models import LanguageGuess, Span, TranscribedWord
from reelcut.asr.speech import windows

SAMPLE_RATE = 16_000
DETECT_SECONDS = 30
# Skip silences this long when a segment looks hallucinated (needs word timestamps).
HALLUCINATION_SILENCE_S = 2.0


class ASRBackend(Protocol):
    name: str

    def detect_language(
        self, wav16k: Path, regions: Sequence[Span], candidates: Sequence[str]
    ) -> LanguageGuess: ...

    def transcribe(
        self,
        wav16k: Path,
        language: str,
        initial_prompt: str | None,
        regions: Sequence[Span] | None,
    ) -> list[TranscribedWord]: ...


def load_samples(wav16k: Path) -> npt.NDArray[np.float32]:
    samples, rate = soundfile.read(str(wav16k), dtype="float32", always_2d=True)
    if rate != SAMPLE_RATE:
        raise ValueError(f"{wav16k} is {rate} Hz, expected {SAMPLE_RATE}")
    return np.ascontiguousarray(samples.mean(axis=1), dtype=np.float32)


def speech_only(
    samples: npt.NDArray[np.float32], regions: Sequence[Span]
) -> npt.NDArray[np.float32]:
    """The first 30 s of detected speech, joined: what language ID listens to."""
    parts: list[npt.NDArray[np.float32]] = []
    total = 0
    for region in regions:
        part = samples[int(region.start * SAMPLE_RATE) : int(region.end * SAMPLE_RATE)]
        parts.append(part)
        total += len(part)
        if total >= DETECT_SECONDS * SAMPLE_RATE:
            break
    joined = np.concatenate(parts) if parts else samples
    return joined[: DETECT_SECONDS * SAMPLE_RATE]


def best_candidate(probs: dict[str, float], candidates: Sequence[str]) -> LanguageGuess:
    """The likeliest language reelcut has a data file for; confidence is the model's own."""
    code = max(candidates, key=lambda c: probs.get(c, 0.0))
    return LanguageGuess(code=code, confidence=round(min(1.0, probs.get(code, 0.0)), 3))


def clip_timestamps(
    samples: npt.NDArray[np.float32], regions: Sequence[Span] | None
) -> list[float]:
    """Flat start, end, start, end ... list in seconds, as both backends take it."""
    duration = len(samples) / SAMPLE_RATE
    spans = windows(regions, duration) if regions else [Span(start=0, end=duration)]
    return [t for span in spans for t in (span.start, span.end)]


def _word(text: str, start: float, end: float, probability: float) -> TranscribedWord:
    start = max(0.0, start)
    return TranscribedWord(
        text=text.strip(),
        start=round(start, 3),
        end=round(max(start, end), 3),
        conf=round(min(1.0, max(0.0, probability)), 3),
    )


class MlxWhisper:
    name = "mlx-whisper"

    def __init__(self, model_dir: str) -> None:
        import mlx.core as mx  # pyright: ignore[reportMissingImports]
        from mlx_whisper.transcribe import ModelHolder  # pyright: ignore[reportMissingImports]

        self._model_dir = model_dir
        self._model: Any = ModelHolder.get_model(model_dir, mx.float16)

    def detect_language(
        self, wav16k: Path, regions: Sequence[Span], candidates: Sequence[str]
    ) -> LanguageGuess:
        import mlx.core as mx  # pyright: ignore[reportMissingImports]
        from mlx_whisper.audio import (  # pyright: ignore[reportMissingImports]
            N_FRAMES,
            N_SAMPLES,
            log_mel_spectrogram,
            pad_or_trim,
        )

        audio = speech_only(load_samples(wav16k), regions)
        mel = log_mel_spectrogram(audio, n_mels=self._model.dims.n_mels, padding=N_SAMPLES)
        segment = pad_or_trim(mel, N_FRAMES, axis=-2).astype(mx.float16)
        _, probs = self._model.detect_language(segment)
        return best_candidate(dict(probs), candidates)

    def transcribe(
        self,
        wav16k: Path,
        language: str,
        initial_prompt: str | None,
        regions: Sequence[Span] | None,
    ) -> list[TranscribedWord]:
        import mlx_whisper  # pyright: ignore[reportMissingImports]

        samples = load_samples(wav16k)
        result: dict[str, Any] = mlx_whisper.transcribe(
            samples,
            path_or_hf_repo=self._model_dir,
            language=language,
            initial_prompt=initial_prompt,
            word_timestamps=True,
            condition_on_previous_text=False,
            hallucination_silence_threshold=HALLUCINATION_SILENCE_S,
            clip_timestamps=clip_timestamps(samples, regions),
            verbose=None,
        )
        return [
            _word(w["word"], w["start"], w["end"], w.get("probability", 1.0))
            for segment in result.get("segments", [])
            for w in segment.get("words", [])
        ]


class FasterWhisper:
    name = "faster-whisper"

    def __init__(self, model_dir: str) -> None:
        from faster_whisper import WhisperModel  # pyright: ignore[reportMissingImports]

        self._model = WhisperModel(model_dir, device="cpu", compute_type="int8")

    def detect_language(
        self, wav16k: Path, regions: Sequence[Span], candidates: Sequence[str]
    ) -> LanguageGuess:
        audio = speech_only(load_samples(wav16k), regions)
        _, _, all_probs = self._model.detect_language(audio)
        return best_candidate(dict(all_probs), candidates)

    def transcribe(
        self,
        wav16k: Path,
        language: str,
        initial_prompt: str | None,
        regions: Sequence[Span] | None,
    ) -> list[TranscribedWord]:
        samples = load_samples(wav16k)
        segments, _ = self._model.transcribe(
            samples,
            language=language,
            initial_prompt=initial_prompt,
            word_timestamps=True,
            condition_on_previous_text=False,
            hallucination_silence_threshold=HALLUCINATION_SILENCE_S,
            vad_filter=False,
            clip_timestamps=clip_timestamps(samples, regions),
        )
        return [
            _word(w.word, w.start, w.end, w.probability)
            for segment in segments
            for w in segment.words or []
        ]


def load_backend(name: str, model_dir: str) -> ASRBackend:
    if name == "mlx-whisper":
        return MlxWhisper(model_dir)
    if name == "faster-whisper":
        return FasterWhisper(model_dir)
    raise ValueError(f"unknown backend {name!r}")
