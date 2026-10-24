"""Generate the synthetic test fixtures and their ground truth.

macOS only: the talking clips are spoken with `say`. Everything else needs only ffmpeg.
Each line is synthesised on its own and the silences are inserted as zero samples, so the
ground truth is computed from sample counts instead of being measured afterwards.

Usage: uv run python scripts/make_fixtures.py [--media-dir DIR] [--ground-truth-dir DIR]
"""

from __future__ import annotations

import argparse
import array
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

SAMPLE_RATE = 48_000
FPS = 30
TALKING_SIZE = (1080, 1920)
BROLL_SIZE = (1920, 1080)
BROLL_SECONDS = 6
TINY_SIZE = (360, 640)
TINY_SECONDS = 2
# The presenter holds still through the silent tail, so analyze reports it as static (>= 2 s).
TAIL_MS = 3000
FACE_PHOTO = FIXTURES / "faces" / "neil_armstrong_960.jpg"
# A 500 px square around the face in the photo, shown 720 px wide: a phone-selfie face size.
FACE_CROP = "crop=500:500:350:100,scale=720:720"

# `say` pads each line with near-silence; trim to this level, keeping 10 ms so attacks survive.
TRIM_THRESHOLD = 40
TRIM_PAD_MS = 10

# The VFR remux needs pts == dts, so the talking clips are encoded without B-frames.
VIDEO_TIMESCALE = 90_000
FRAME_TICKS = VIDEO_TIMESCALE // FPS
# Every third frame is shown 10 ms late, so frame durations alternate 43/23/33 ms around 30 fps.
VFR_SETTS = f"setts=ts=N*{FRAME_TICKS}+if(eq(mod(N\\,3)\\,1)\\,900\\,0)"

BITEXACT = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags", "+bitexact"]


@dataclass(frozen=True)
class Say:
    text: str
    # "line" starts a new utterance; "continue" and "filler" extend the current one.
    kind: str = "line"
    complete: bool = True


@dataclass(frozen=True)
class Silence:
    ms: int
    context: str


@dataclass(frozen=True)
class TalkingClip:
    name: str
    language: str
    voice: str
    filler: str
    script: tuple[Say | Silence, ...]
    # Indices into the clip's utterances: the abandoned first attempt and the complete retake.
    retake: tuple[int, int]


EN = TalkingClip(
    name="en_talking",
    language="en",
    voice="Samantha",
    filler="um",
    script=(
        Silence(800, "head"),
        Say("Hi, welcome back to the channel."),
        Silence(1500, "between_utterances"),
        Say("Today,"),
        Silence(300, "around_filler"),
        Say("um", kind="filler"),
        Silence(300, "around_filler"),
        Say("I want to show you how I edit my videos.", kind="continue"),
        Silence(1200, "between_utterances"),
        Say("The most important thing to remember is", complete=False),
        Silence(900, "between_utterances"),
        Say("The most important thing to remember is to keep every sentence short."),
        Silence(1500, "between_utterances"),
        Say("Thanks for watching, and see you next time."),
        Silence(TAIL_MS, "tail"),
    ),
    retake=(2, 3),
)

IT = TalkingClip(
    name="it_talking",
    language="it",
    voice="Alice",
    filler="ehm",
    script=(
        Silence(800, "head"),
        Say("Ciao, bentornati sul canale."),
        Silence(1500, "between_utterances"),
        Say("Oggi,"),
        Silence(300, "around_filler"),
        Say("ehm", kind="filler"),
        Silence(300, "around_filler"),
        Say("vi faccio vedere come monto i miei video.", kind="continue"),
        Silence(1200, "between_utterances"),
        Say("La cosa più importante da ricordare è", complete=False),
        Silence(900, "between_utterances"),
        Say("La cosa più importante da ricordare è tenere ogni frase breve."),
        Silence(1500, "between_utterances"),
        Say("Grazie per la visione, e alla prossima."),
        Silence(TAIL_MS, "tail"),
    ),
    retake=(2, 3),
)

ACCENTED_NAME = "prova clip è.mov"


def run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.splitlines()[-20:])
        sys.exit(f"command failed: {args[0]} ... (exit {result.returncode})\n{tail}")


def ffmpeg(*args: str) -> None:
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args])


def samples_to_ms(samples: int) -> int:
    return round(samples * 1000 / SAMPLE_RATE)


def ms_to_samples(ms: int) -> int:
    return ms * SAMPLE_RATE // 1000


def silence(samples: int) -> array.array[int]:
    return array.array("h", [0]) * samples


def synthesise(text: str, voice: str, work: Path, index: int) -> array.array[int]:
    """Speak one line and return its 48 kHz mono samples, trimmed to the audible part."""
    raw = work / f"say_{index}.wav"
    run(
        [
            "say",
            "-v",
            voice,
            "-o",
            str(raw),
            "--file-format=WAVE",
            f"--data-format=LEI16@{SAMPLE_RATE}",
            text,
        ]
    )
    with wave.open(str(raw), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
            sys.exit(f"`say` wrote an unexpected format for {text!r}")
        pcm = array.array("h", w.readframes(w.getnframes()))
    loud = [i for i, s in enumerate(pcm) if abs(s) > TRIM_THRESHOLD]
    if not loud:
        sys.exit(f"`say` produced silence for {text!r}")
    pad = ms_to_samples(TRIM_PAD_MS)
    return pcm[max(0, loud[0] - pad) : min(len(pcm), loud[-1] + 1 + pad)]


def build_talking_audio(clip: TalkingClip, work: Path) -> tuple[Path, dict[str, Any]]:
    """Write the clip's WAV and return it with the ground truth of what was inserted."""
    pcm: array.array[int] = array.array("h")
    utterances: list[dict[str, Any]] = []
    fillers: list[dict[str, Any]] = []
    silences: list[dict[str, Any]] = []

    for index, item in enumerate(clip.script):
        start = len(pcm)
        if isinstance(item, Silence):
            pcm.extend(silence(ms_to_samples(item.ms)))
            silences.append(
                {
                    "start_ms": samples_to_ms(start),
                    "end_ms": samples_to_ms(len(pcm)),
                    "context": item.context,
                }
            )
            continue
        pcm.extend(synthesise(item.text, clip.voice, work, index))
        span = {"start_ms": samples_to_ms(start), "end_ms": samples_to_ms(len(pcm))}
        if item.kind == "line":
            utterances.append({"text": item.text, **span, "complete": item.complete})
            continue
        current = utterances[-1]
        current["end_ms"] = span["end_ms"]
        joiner = "," if item.kind == "filler" else ""
        current["text"] = f"{current['text']} {item.text}{joiner}"
        if item.kind == "filler":
            fillers.append({"text": item.text, "kind": "hard", **span})

    # Pad with silence to a whole frame so audio and video end together.
    frame = SAMPLE_RATE // FPS
    pcm.extend(silence(-len(pcm) % frame))
    silences[-1]["end_ms"] = samples_to_ms(len(pcm))

    wav = work / f"{clip.name}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())

    abandoned, winner = clip.retake
    truth: dict[str, Any] = {
        "schema_version": 1,
        "clip": f"{clip.name}.mov",
        "language": clip.language,
        "voice": clip.voice,
        "duration_ms": samples_to_ms(len(pcm)),
        "video": {"width": TALKING_SIZE[0], "height": TALKING_SIZE[1], "fps": FPS, "vfr": True},
        "utterances": utterances,
        "fillers": fillers,
        "silences": silences,
        "retake": {"abandoned": abandoned, "winner": winner},
    }
    return wav, truth


def presenter_video(seconds: float, still_from: float, out: Path, work: Path) -> None:
    """A real face that drifts over a static body until `still_from`, then holds still."""
    head = work / "head.png"
    ffmpeg("-i", str(FACE_PHOTO), "-vf", FACE_CROP, "-frames:v", "1", str(head))
    width, height = TALKING_SIZE
    t = f"min(t,{still_from:.3f})"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x2a4d69:s={width}x{height}:r={FPS}:d={seconds}",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(head),
        "-filter_complex",
        "[0]drawbox=x=190:y=1180:w=700:h=740:color=0x3b3b58:t=fill[bg];"
        f"[bg][1]overlay=x='180+60*sin(2*PI*{t}/4)':y='500+40*sin(2*PI*{t}/3)':shortest=1,"
        "format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-bf",
        "0",
        "-video_track_timescale",
        str(VIDEO_TIMESCALE),
        *BITEXACT,
        str(out),
    )


def make_talking_clip(clip: TalkingClip, media: Path, work: Path) -> dict[str, Any]:
    wav, truth = build_talking_audio(clip, work)
    seconds = truth["duration_ms"] / 1000
    cfr = work / f"{clip.name}_cfr.mov"
    presenter_video(seconds, truth["silences"][-1]["start_ms"] / 1000, cfr, work)
    # Remux: the video stream is copied and only its timestamps change.
    ffmpeg(
        "-i",
        str(cfr),
        "-i",
        str(wav),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-bsf:v",
        VFR_SETTS,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        *BITEXACT,
        str(media / f"{clip.name}.mov"),
    )
    return truth


def make_broll(media: Path) -> None:
    width, height = BROLL_SIZE
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={width}x{height}:r={FPS}:d={BROLL_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=c=pink:a=0.01:r={SAMPLE_RATE}:seed=7:d={BROLL_SECONDS}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "1",
        *BITEXACT,
        str(media / "broll.mp4"),
    )


def make_image(media: Path) -> None:
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "mandelbrot=s=1600x1200",
        "-frames:v",
        "1",
        *BITEXACT,
        str(media / "image.png"),
    )


def make_tiny(out: Path) -> None:
    width, height = TINY_SIZE
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s={width}x{height}:r={FPS}:d={TINY_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        f"sine=f=440:r={SAMPLE_RATE}:d={TINY_SECONDS}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        *BITEXACT,
        str(out),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic test fixtures.")
    parser.add_argument("--media-dir", type=Path, default=FIXTURES / "media")
    parser.add_argument("--ground-truth-dir", type=Path, default=FIXTURES / "ground_truth")
    parser.add_argument("--tiny", type=Path, default=FIXTURES / "tiny.mp4")
    args = parser.parse_args()

    for tool in ("say", "ffmpeg"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found: fixtures are generated on macOS with ffmpeg installed")

    media: Path = args.media_dir
    truth_dir: Path = args.ground_truth_dir
    if media.exists():
        shutil.rmtree(media)
    media.mkdir(parents=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    args.tiny.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for clip in (EN, IT):
            truth = make_talking_clip(clip, media, work)
            path = truth_dir / f"{clip.name}.json"
            path.write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
            print(path)
    shutil.copyfile(media / f"{EN.name}.mov", media / ACCENTED_NAME)
    make_broll(media)
    make_image(media)
    make_tiny(args.tiny)
    for path in sorted(media.iterdir()):
        print(path)
    print(args.tiny)


if __name__ == "__main__":
    main()
