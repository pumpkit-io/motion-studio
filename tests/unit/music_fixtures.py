"""A stand-in ACE-Step worker and voice detector for `motion-studio music` tests.

The worker speaks the real one's protocol: one job per stdin line, one result per stdout line,
the model "loaded" once per process.
"""

import json
from pathlib import Path

import numpy as np

from motion_studio.analysis import Span

# Per job it writes a 48 kHz stereo click track at the job's BPM; loud noise (vocals to the stub
# detector) for the seeds listed in VOCAL_SEEDS; the numpy expression of t in BASS_HEAVY; or, when
# SECTIONED exists, the sectioned bed below. Every job is appended to jobs.jsonl with the pid.
FAKE_WORKER = """
import json, os, sys
from pathlib import Path
import numpy as np, soundfile as sf

here = Path(__file__).parent
SR = 48000
FIRST_BEAT_S = 0.25
# Bars and layers per section: intro, build, drop, ending, then two seconds of silence.
SECTIONS = [(8, {"hat"}), (8, {"hat", "kick"}), (8, {"hat", "kick", "lead"}), (4, {"hat"})]


def sectioned(bpm):
    beat = 60 / bpm
    bars = sum(n for n, _ in SECTIONS)
    y = np.zeros(int((FIRST_BEAT_S + bars * 4 * beat + 2.0) * SR))
    n = np.arange(int(0.08 * SR))
    hat = 0.08 * np.random.default_rng(1).uniform(-1, 1, len(n)) * np.exp(-n / 300)
    kick = 0.6 * np.sin(2 * np.pi * 55 * n / SR) * np.exp(-n / 2500)
    m = np.arange(int(0.9 * beat * SR))
    lead = 0.15 * np.sin(2 * np.pi * 660 * m / SR) * np.exp(-m / (0.2 * SR))

    def add(t, sound):
        i = round(t * SR)
        y[i:i + len(sound)] += sound

    t = FIRST_BEAT_S
    for count, layers in SECTIONS:
        for b in range(count * 4):
            at = t + b * beat
            if "hat" in layers:
                add(at, hat)
                add(at + beat / 2, 0.6 * hat)
            if "kick" in layers:
                add(at, kick)
            if "lead" in layers:
                add(at, lead)
        t += count * 4 * beat
    return y


def clicks(job, n):
    y = np.zeros(n)
    click = 0.3 * np.sin(2 * np.pi * 1000 * np.arange(2400) / SR) * np.exp(-np.arange(2400) / 300)
    step = 60 / (job["bpm"] or 120)
    t = 0.5
    while t * SR + 2400 < n:
        i = int(t * SR)
        y[i:i + 2400] += click
        t += step
    return y


first = True
for line in sys.stdin:
    if not line.strip():
        continue
    job = json.loads(line)
    with open(here / "jobs.jsonl", "a") as log:
        log.write(json.dumps({**job, "pid": os.getpid()}) + "\\n")
    vocal = here / "VOCAL_SEEDS"
    vocal_seeds = json.loads(vocal.read_text()) if vocal.exists() else []
    n = int(job["duration"] * SR)
    t = np.arange(n) / SR
    if job["seed"] in vocal_seeds:
        y = np.random.default_rng(0).uniform(-0.9, 0.9, n)
    elif (here / "BASS_HEAVY").exists():
        y = eval((here / "BASS_HEAVY").read_text(), {"np": np, "t": t})
    elif (here / "SECTIONED").exists():
        # Quiet enough that the stand-in voice detector hears no speech in it.
        y = 0.25 * sectioned(job["bpm"] or 120)
    else:
        y = clicks(job, n)
    out = Path(job["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, np.stack([y, y], axis=1).astype(np.float32), SR)
    print("model chatter on stderr", file=sys.stderr)
    result = {"wav": str(out), "seed": job["seed"], "load_s": 1.0 if first else 0.0,
              "generate_s": 2.0, "pid": os.getpid()}
    first = False
    print(json.dumps(result), flush=True)
"""


class LoudIsSpeech:
    """Stands in for Silero: any 0.5 s window with an RMS above 0.1 counts as speech."""

    def __init__(self, path: Path | None = None) -> None:
        pass

    def speech(self, samples: np.ndarray, params: object = None) -> list[Span]:
        window = 8000
        spans: list[Span] = []
        for start in range(0, len(samples) - window + 1, window):
            if float(np.sqrt(np.mean(samples[start : start + window] ** 2))) > 0.1:
                spans.append(Span(start=start / 16000, end=(start + window) / 16000))
        return spans


def jobs(worker: Path) -> list[dict[str, object]]:
    log = worker / "jobs.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]
