"""Mix and master: duck the music, gain to target, true-peak limit, and copy the video stream."""

import json
from dataclasses import dataclass
from pathlib import Path

from motion_studio.config import Master, Music
from motion_studio.errors import InternalError
from motion_studio.media.ffmpeg import ffmpeg_caps, filter_graph_args, run_ffmpeg

SAMPLE_RATE = 48_000
MUSIC_FADE_S = 1.5
ATTACK_MS = 10
RELEASE_MS = 400
# The limiter runs at 4x the sample rate so it catches the peaks between samples (true peak).
OVERSAMPLE = 4
# Headroom under the ceiling for the inter-sample peaks resampling and AAC put back.
LIMITER_MARGIN_DB = 0.5
LIMITER_ATTACK_MS = 5
LIMITER_RELEASE_MS = 100
GAIN_CORRECTIONS = 2
GAIN_TOLERANCE_LU = 0.3


@dataclass(frozen=True)
class Loudness:
    """loudnorm's first-pass measurement, fed back into the second pass."""

    input_i: str
    input_tp: str
    input_lra: str
    input_thresh: str
    target_offset: str

    @property
    def usable(self) -> bool:
        """False for silence: loudnorm rejects a measured_I of -inf or below -99."""
        try:
            return float(self.input_i) >= -99 and float(self.input_tp) >= -99
        except ValueError:
            return False


def premaster_graph(duration_s: float, music: Music | None) -> str:
    """Voice from input 0, music from input 1 (looped by the caller) into `[premaster]`.

    The music is trimmed to the video, faded out over its last 1.5 s, set to `gain_db`, ducked
    by a sidechain keyed on the voice, then summed with the voice without amix's normalisation.
    """
    if music is None:
        return f"[0:a]aresample={SAMPLE_RATE}[premaster]"
    fade_at = max(0.0, duration_s - MUSIC_FADE_S)
    return ";".join(
        [
            f"[0:a]aresample={SAMPLE_RATE},asplit=2[voice][key]",
            f"[1:a]aresample={SAMPLE_RATE},atrim=end={duration_s:.4f},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={fade_at:.4f}:d={MUSIC_FADE_S},volume={music.gain_db}dB[bed]",
            f"[bed][key]sidechaincompress=threshold={music.duck_threshold}:ratio={music.duck_ratio}"
            f":attack={ATTACK_MS}:release={RELEASE_MS}[ducked]",
            "[voice][ducked]amix=inputs=2:duration=first:normalize=0[premaster]",
        ]
    )


def loudnorm(master: Master) -> str:
    """The first pass: loudnorm only measures, printing its JSON summary."""
    return (
        f"loudnorm=I={master.integrated_lufs}:TP={master.true_peak_db}:LRA={master.lra}"
        ":print_format=json"
    )


def mastering(master: Master, gain_db: float) -> str:
    """A fixed gain to the target loudness, then an oversampled true-peak limiter.

    Unlike linear loudnorm, which falls back to dynamic compression when the gain would push the
    peaks past the ceiling, this keeps the target loudness and lets the limiter take the peaks.
    """
    ceiling = 10 ** ((master.true_peak_db - LIMITER_MARGIN_DB) / 20)
    rate = SAMPLE_RATE * OVERSAMPLE
    return (
        f"volume={gain_db:.2f}dB,aresample={rate},"
        f"alimiter=limit={ceiling:.4f}:attack={LIMITER_ATTACK_MS}:release={LIMITER_RELEASE_MS}"
        f":level=false:latency=true,aresample={SAMPLE_RATE}"
    )


def mix(
    composed: Path,
    out: Path,
    voice_out: Path,
    *,
    duration_s: float,
    music_file: Path | None,
    music: Music,
    master: Master,
    scratch: Path,
) -> Path:
    """Write `out` with mastered audio and the composed video stream copied, and `voice_out`.

    `voice_out` is the rendered voice before any music, which `check` re-transcribes.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            composed,
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-y",
            voice_out,
        ]
    )

    inputs: list[str | Path] = ["-i", composed]
    if music_file is not None:
        inputs += ["-stream_loop", "-1", "-i", music_file]
    pre = premaster_graph(duration_s, music if music_file is not None else None)
    caps = ffmpeg_caps()

    def measure(chain: str, name: str) -> Loudness:
        graph = f"{pre};[premaster]{chain}{loudnorm(master)}[out]"
        lines = run_ffmpeg(
            [
                *inputs,
                *filter_graph_args(caps, graph, scratch / name),
                "-map",
                "[out]",
                "-f",
                "null",
                "-",
            ]
        )
        return parse_loudnorm(lines)

    measured = measure("", "mix1.filtergraph")
    gain = 0.0
    if measured.usable:
        gain = master.integrated_lufs - float(measured.input_i)
        # Limiting the peaks lowers the loudness, so measure the mastered mix and correct the gain.
        for _ in range(GAIN_CORRECTIONS):
            after = measure(f"{mastering(master, gain)},", "mix_gain.filtergraph")
            off = master.integrated_lufs - float(after.input_i)
            if not after.usable or abs(off) <= GAIN_TOLERANCE_LU:
                break
            gain += off
    final_pass = mastering(master, gain)

    second = f"{pre};[premaster]{final_pass}[out]"
    run_ffmpeg(
        [
            *inputs,
            *filter_graph_args(caps, second, scratch / "mix2.filtergraph"),
            "-map", "0:v:0", "-map", "[out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "320k", "-ar", str(SAMPLE_RATE),
            "-movflags", "+faststart", "-y", out,
        ]
    )  # fmt: skip
    return out


def parse_loudnorm(stderr: list[str]) -> Loudness:
    """The JSON block loudnorm prints at the end of its first pass."""
    text = "\n".join(stderr)
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end < start:
        raise InternalError("loudnorm printed no measurement")
    data = json.loads(text[start : end + 1])
    return Loudness(
        input_i=data["input_i"],
        input_tp=data["input_tp"],
        input_lra=data["input_lra"],
        input_thresh=data["input_thresh"],
        target_offset=data["target_offset"],
    )
