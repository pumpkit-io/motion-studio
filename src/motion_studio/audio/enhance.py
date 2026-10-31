"""Extract a clip's voice and clean it: DeepFilterNet (or ffmpeg `arnndn`), then a high-pass.

DeepFilterNet 3 runs as its official `deep-filter` release binary: the `deepfilternet` pip
package has no Python 3.12 wheel and pins numpy < 2. The binary is looked up in
`$MOTION_STUDIO_DEEP_FILTER`, then `<cache>/bin/deep-filter`, then PATH.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

import soundfile

from motion_studio import ENV_PREFIX
from motion_studio.errors import DependencyError
from motion_studio.media.ffmpeg import FFmpegCaps, run_ffmpeg
from motion_studio.paths import cache_dir

SAMPLE_RATE = 48_000
ASR_SAMPLE_RATE = 16_000
HIGHPASS_HZ = 80

DEEP_FILTER_ENV = f"{ENV_PREFIX}_DEEP_FILTER"
DEEP_FILTER_VERSION = "0.5.6"
DEEP_FILTER_URL = (
    "https://github.com/Rikorose/DeepFilterNet/releases/download/"
    f"v{DEEP_FILTER_VERSION}/deep-filter-{DEEP_FILTER_VERSION}-{{target}}"
)
# SHA-256 of each release binary, computed from the downloads on 2026-10-24.
DEEP_FILTER_TARGETS = {
    ("Darwin", "arm64"): (
        "aarch64-apple-darwin",
        "4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081",
    ),
    ("Darwin", "x86_64"): (
        "x86_64-apple-darwin",
        "d3be84003acb7c23e738ad7f70a158ec779a8d233a82e7fa3e717d112eb5b50f",
    ),
    ("Linux", "x86_64"): (
        "x86_64-unknown-linux-musl",
        "70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da",
    ),
    ("Linux", "aarch64"): (
        "aarch64-unknown-linux-gnu",
        "14e02a1c0028f3ca0bdf83b62b3336e56ba0556894ef295a95e8573f06557166",
    ),
}

Denoiser = Literal["deepfilternet", "arnndn", "none"]


@dataclass(frozen=True)
class Voice:
    wav: Path
    wav_16k: Path
    denoiser: Denoiser
    warning: str | None


def deep_filter_binary() -> Path | None:
    configured = os.environ.get(DEEP_FILTER_ENV)
    if configured:
        return Path(configured) if Path(configured).is_file() else None
    cached = cache_dir() / "bin" / "deep-filter"
    if cached.is_file():
        return cached
    found = shutil.which("deep-filter")
    return Path(found) if found else None


def install_deep_filter() -> Path:
    """Download the pinned `deep-filter` binary for this platform into the cache."""
    key = (platform.system(), platform.machine())
    if key not in DEEP_FILTER_TARGETS:
        raise DependencyError(f"no DeepFilterNet {DEEP_FILTER_VERSION} binary for {key}")
    target, sha256 = DEEP_FILTER_TARGETS[key]
    dest = cache_dir() / "bin" / "deep-filter"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(".deep-filter.download")
    with urllib.request.urlopen(DEEP_FILTER_URL.format(target=target), timeout=120) as response:
        tmp.write_bytes(response.read())
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if digest != sha256:
        tmp.unlink()
        raise DependencyError(f"deep-filter download has SHA-256 {digest}, expected {sha256}")
    tmp.chmod(0o755)
    tmp.replace(dest)
    return dest


def denoiser_available(caps: FFmpegCaps) -> Denoiser:
    if deep_filter_binary() is not None:
        return "deepfilternet"
    return "arnndn" if caps.has_filter("arnndn") else "none"


def extract_voice(source: Path, wav: Path, wav_16k: Path, *, caps: FFmpegCaps) -> Voice:
    """Write the cleaned voice as 48 kHz mono `wav` and a 16 kHz mono copy for ASR and VAD.

    Both have exactly the source audio's length, so times in either match the mezzanine.
    """
    denoiser = denoiser_available(caps)
    warning = None
    with tempfile.TemporaryDirectory(prefix=".ingest-", dir=wav.parent) as tmp_dir:
        tmp = Path(tmp_dir)
        raw = tmp / "voice.wav"
        run_ffmpeg(["-y", "-loglevel", "error", "-i", source, "-map", "0:a:0", "-vn", *_pcm(raw)])
        samples = soundfile.info(str(raw)).frames
        filters = [f"highpass=f={HIGHPASS_HZ}"]
        cleaned = raw
        if denoiser == "deepfilternet":
            try:
                cleaned = _deep_filter(raw, tmp / "out")
            except (OSError, subprocess.CalledProcessError) as exc:
                denoiser = "arnndn" if caps.has_filter("arnndn") else "none"
                warning = f"DeepFilterNet failed ({exc}); used {denoiser}"
        elif denoiser == "arnndn":
            warning = (
                "DeepFilterNet not found; denoised with ffmpeg arnndn "
                f"(install deep-filter {DEEP_FILTER_VERSION} for better quality)"
            )
        else:
            warning = (
                "no denoiser available (DeepFilterNet or ffmpeg arnndn); voice only high-passed"
            )
        with as_file(files("motion_studio.audio") / "models" / "sh.rnnn") as model:
            if denoiser == "arnndn":
                filters.insert(0, f"arnndn=m={filter_value(str(model))}")
            # deep-filter's delay compensation trims the tail; pad back to the source length.
            filters += [f"apad=whole_len={samples}", f"atrim=end_sample={samples}"]
            _write(cleaned, wav, ",".join(filters), SAMPLE_RATE)
        _write(wav, wav_16k, "anull", ASR_SAMPLE_RATE)
    return Voice(wav, wav_16k, denoiser, warning)


def _deep_filter(raw: Path, out_dir: Path) -> Path:
    binary = deep_filter_binary()
    assert binary is not None
    subprocess.run(
        [str(binary), "--compensate-delay", "-o", str(out_dir), str(raw)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=3600,
    )
    return out_dir / raw.name


def _write(source: Path, dest: Path, graph: str, rate: int) -> None:
    tmp = dest.with_name(f".{dest.name}")
    run_ffmpeg(["-y", "-loglevel", "error", "-i", source, "-af", graph, *_pcm(tmp, rate)])
    tmp.replace(dest)


def _pcm(dest: Path, rate: int = SAMPLE_RATE) -> list[str | Path]:
    return ["-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", dest]


def filter_value(value: str) -> str:
    """Escape `value` for an ffmpeg filter option, then for the filtergraph around it."""
    for char in "\\':":
        value = value.replace(char, "\\" + char)
    for char in "\\'[],;":
        value = value.replace(char, "\\" + char)
    return value
