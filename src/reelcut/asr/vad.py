"""Silero VAD through onnxruntime: speech regions of a 16 kHz mono signal.

The model is the official `silero_vad.onnx` from the snakers4/silero-vad release, downloaded
into the model cache by `reelcut setup`. The post-processing follows the reference
`get_speech_timestamps` of that release, without its maximum-speech splitting.
"""

import hashlib
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from reelcut import APP_NAME
from reelcut.analysis.models import Span
from reelcut.errors import DependencyError
from reelcut.paths import models_dir

SAMPLE_RATE = 16_000
WINDOW = 512
CONTEXT = 64

SILERO_VERSION = "6.2.3"
SILERO_URL = (
    f"https://raw.githubusercontent.com/snakers4/silero-vad/v{SILERO_VERSION}"
    "/src/silero_vad/data/silero_vad.onnx"
)
# SHA-256 of the v6.2.3 file, computed from the download on 2026-10-24.
SILERO_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"


@dataclass(frozen=True)
class VadParams:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 100
    speech_pad_ms: int = 30


def vad_model_path() -> Path:
    return models_dir() / f"silero_vad-{SILERO_VERSION}.onnx"


def install_vad_model() -> Path:
    """Download the pinned Silero VAD model into the cache, unless it is already there."""
    dest = vad_model_path()
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.download")
    with urllib.request.urlopen(SILERO_URL, timeout=120) as response:
        tmp.write_bytes(response.read())
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if digest != SILERO_SHA256:
        tmp.unlink()
        raise DependencyError(f"Silero VAD download has SHA-256 {digest}, expected {SILERO_SHA256}")
    tmp.replace(dest)
    return dest


class SileroVad:
    def __init__(self, path: Path | None = None) -> None:
        import onnxruntime

        model = path or vad_model_path()
        if not model.is_file():
            raise DependencyError(
                f"the Silero VAD model is not in {model.parent}",
                hint=f"run `{APP_NAME} setup` once while online",
            )
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.log_severity_level = 4
        self._session = onnxruntime.InferenceSession(
            str(model), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def probabilities(self, samples: npt.NDArray[np.float32]) -> list[float]:
        """Speech probability of each 512-sample window (32 ms), in order."""
        padded = np.pad(samples.astype(np.float32), (0, -len(samples) % WINDOW))
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, CONTEXT), dtype=np.float32)
        rate = np.array(SAMPLE_RATE, dtype=np.int64)
        probs: list[float] = []
        for offset in range(0, len(padded), WINDOW):
            chunk = np.concatenate([context, padded[None, offset : offset + WINDOW]], axis=1)
            out, state = self._session.run(None, {"input": chunk, "state": state, "sr": rate})
            probs.append(float(np.asarray(out).reshape(-1)[0]))
            context = chunk[:, -CONTEXT:]
        return probs

    def speech(
        self, samples: npt.NDArray[np.float32], params: VadParams | None = None
    ) -> list[Span]:
        return speech_spans(self.probabilities(samples), len(samples), params)


def speech_spans(
    probs: Sequence[float], total_samples: int, params: VadParams | None = None
) -> list[Span]:
    """Turn per-window speech probabilities into padded speech regions, in seconds."""
    p = params or VadParams()
    neg_threshold = max(p.threshold - 0.15, 0.01)
    min_speech = SAMPLE_RATE * p.min_speech_ms / 1000
    min_silence = SAMPLE_RATE * p.min_silence_ms / 1000
    pad = int(SAMPLE_RATE * p.speech_pad_ms / 1000)

    regions: list[list[int]] = []
    start: int | None = None
    silence_from = 0
    for index, prob in enumerate(probs):
        at = WINDOW * index
        if prob >= p.threshold:
            silence_from = 0
            if start is None:
                start = at
            continue
        if start is not None and prob < neg_threshold:
            if not silence_from:
                silence_from = at
            if at - silence_from >= min_silence:
                if silence_from - start > min_speech:
                    regions.append([start, silence_from])
                start, silence_from = None, 0
    if start is not None and total_samples - start > min_speech:
        regions.append([start, total_samples])

    # Pad each region, splitting a gap shorter than two pads evenly between its neighbours.
    for index, region in enumerate(regions):
        if index == 0:
            region[0] = max(0, region[0] - pad)
        if index + 1 < len(regions):
            following = regions[index + 1]
            gap = following[0] - region[1]
            if gap < 2 * pad:
                region[1] += gap // 2
                following[0] -= gap // 2
            else:
                region[1] = min(total_samples, region[1] + pad)
                following[0] = max(0, following[0] - pad)
        else:
            region[1] = min(total_samples, region[1] + pad)
    return [
        Span(start=round(a / SAMPLE_RATE, 3), end=round(b / SAMPLE_RATE, 3)) for a, b in regions
    ]
