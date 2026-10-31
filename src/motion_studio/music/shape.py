"""The small-speaker chain every generated bed goes through; library tracks stay as licensed.

Laptop and phone speakers roll off under about 150 Hz, so a bed mixed for headphones keeps only
rumble there; the chain trims it and lifts presence and air.
"""

from pathlib import Path

from motion_studio.media.ffmpeg import run_ffmpeg

CHAIN = ",".join(
    [
        "highpass=f=35:p=2",
        "lowshelf=f=120:g=-4",
        "equalizer=f=3000:t=q:w=1:g=3",
        "highshelf=f=7000:g=3",
        "acompressor=threshold=-18dB:ratio=2:attack=20:release=250",
        # The boosts can push peaks past full scale; the mix masters loudness later.
        "alimiter=limit=0.95:level=false:latency=true",
    ]
)


def shape_bed(source: Path, out: Path) -> Path:
    """Write `source` through the chain to `out`, a 48 kHz stereo 16-bit WAV."""
    run_ffmpeg(
        ["-y", "-v", "error", "-i", source, "-af", CHAIN,
         "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", out]
    )  # fmt: skip
    return out
