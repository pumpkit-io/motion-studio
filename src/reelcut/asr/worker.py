"""The speech-to-text worker: `python -m reelcut.asr.worker` reads a WorkerRequest on stdin.

It loads the VAD and Whisper models once, analyses every job and prints a WorkerResponse on
stdout. The parent holds the heavy-model lock for the worker's whole life. Exit 2 means a
missing dependency, anything else non-zero is a bug.
"""

import os
import resource
import sys

from reelcut.analysis.models import LanguageGuess
from reelcut.asr import SpeechJob, SpeechResult, WorkerRequest, WorkerResponse
from reelcut.asr.backends import ASRBackend, load_backend, load_samples
from reelcut.asr.speech import align_to_speech, uncovered
from reelcut.asr.vad import SileroVad
from reelcut.errors import DependencyError

# Clips with less detected speech than this get no language and no transcript.
MIN_SPEECH_S = 0.3


def analyse(job: SpeechJob, vad: SileroVad, backend: ASRBackend) -> SpeechResult:
    regions = vad.speech(load_samples(job.wav))
    if sum(r.end - r.start for r in regions) < MIN_SPEECH_S:
        return SpeechResult(id=job.id, vad=regions, language=None, words=[])
    if job.language is None:
        language = backend.detect_language(job.wav, regions, job.candidates)
    else:
        language = LanguageGuess(code=job.language, confidence=1.0)
    prompt = job.prompts.get(language.code)
    words = align_to_speech(backend.transcribe(job.wav, language.code, prompt, regions), regions)
    # Whisper sometimes skips a whole sentence; one pass per missed region usually recovers it.
    for region in uncovered(regions, words):
        words += align_to_speech(
            backend.transcribe(job.wav, language.code, prompt, [region]), [region]
        )
    return SpeechResult(
        id=job.id, vad=regions, language=language, words=sorted(words, key=lambda w: w.start)
    )


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    return round(peak / 1e6 if sys.platform == "darwin" else peak / 1e3, 1)


def main() -> int:
    request = WorkerRequest.model_validate_json(sys.stdin.read())
    # Model libraries may print progress; only the response may reach the parent's stdout.
    out, sys.stdout = sys.stdout, sys.stderr
    try:
        vad = SileroVad(request.vad_model)
        backend = load_backend(request.backend, request.model)
    except (DependencyError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return DependencyError.exit_code
    results = [analyse(job, vad, backend) for job in request.jobs]
    response = WorkerResponse(pid=os.getpid(), peak_rss_mb=_peak_rss_mb(), results=results)
    out.write(response.model_dump_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
