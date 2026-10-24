"""The isolated ACE-Step 1.5 environment: installing it, and generating with it in a subprocess.

`setup --music` follows the official README (download the source, `uv sync`) into
`<cache>/envs/ace-step/src`, so ACE-Step's dependencies never touch reelcut's own environment,
and downloads the pinned weights into `<cache>/envs/ace-step/src/checkpoints`, the directory
ACE-Step loads from. `install.json` is written last and records the licence the weights
declare; generation refuses to run without it.
"""

import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reelcut import APP_NAME
from reelcut.errors import DependencyError, InternalError, UserError
from reelcut.paths import envs_dir
from reelcut.state import heavy_model_lock

# Pinned on 2026-10-24: the source commit of ace-step/ACE-Step-1.5 and the weights revision.
SOURCE_REPO = "ace-step/ACE-Step-1.5"
SOURCE_COMMIT = "ca1e85fe9430179831e6bc6be790c332190a3866"
WEIGHTS_REPO = "ACE-Step/Ace-Step1.5"
WEIGHTS_REVISION = "19671f406d603126926c1b7e2adc169acbcade22"
DIT = "acestep-v15-turbo"
MODEL = f"{WEIGHTS_REPO}@{WEIGHTS_REVISION[:7]} ({DIT})"

# Replaces the worker command (the env's Python running acestep_worker.py) with an executable.
WORKER_ENV = f"{APP_NAME.upper()}_MUSIC_WORKER"
TIMEOUT_ENV = f"{APP_NAME.upper()}_MUSIC_TIMEOUT_S"
STDERR_TAIL = 20


class Install(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    weights: str
    dit: str
    licence: str | None
    licence_source: str | None


@dataclass(frozen=True)
class Generated:
    wav: Path
    seed: int
    elapsed_s: float
    load_s: float
    generate_s: float
    peak_rss_mb: float


def env_root() -> Path:
    return envs_dir() / "ace-step"


def source_dir() -> Path:
    return env_root() / "src"


def checkpoints_dir() -> Path:
    return source_dir() / "checkpoints"


def env_python() -> Path:
    return source_dir() / ".venv" / "bin" / "python"


def install_record_path() -> Path:
    return env_root() / "install.json"


def worker_script() -> Path:
    return Path(__file__).with_name("acestep_worker.py")


def installed() -> Install | None:
    """What `setup --music` installed, or None when it has not completed."""
    path = install_record_path()
    if not path.is_file():
        return None
    try:
        return Install.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def install(step: Callable[[str], None]) -> tuple[Install, bool]:
    """Install the environment and weights; returns the record and whether anything was fetched.

    Raises DependencyError (exit 2) when uv is missing or a step fails.
    """
    current = installed()
    if current is not None and current.weights == f"{WEIGHTS_REPO}@{WEIGHTS_REVISION}":
        return current, False
    uv = shutil.which("uv")
    if uv is None:
        raise DependencyError(
            "uv is needed to create the ACE-Step environment",
            hint="install it: https://docs.astral.sh/uv/getting-started/installation/",
        )
    if not (source_dir() / "pyproject.toml").is_file():
        step(f"downloading ACE-Step 1.5 source {SOURCE_COMMIT[:7]}")
        _download_source()
    step("creating the ACE-Step environment with `uv sync` (several GB)")
    _run([uv, "sync", "--frozen"], cwd=source_dir(), what="uv sync")
    step(f"downloading weights {WEIGHTS_REPO}@{WEIGHTS_REVISION[:7]} (about 10 GB)")
    out = _run(
        [
            str(env_python()),
            "-I",
            str(worker_script()),
            "download",
            WEIGHTS_REPO,
            WEIGHTS_REVISION,
            str(checkpoints_dir()),
        ],
        cwd=source_dir(),
        what="weights download",
    )
    found = json.loads(out.strip().splitlines()[-1])
    record = Install(
        source=f"{SOURCE_REPO}@{SOURCE_COMMIT}",
        weights=f"{WEIGHTS_REPO}@{WEIGHTS_REVISION}",
        dit=DIT,
        licence=found.get("licence"),
        licence_source=found.get("source"),
    )
    install_record_path().write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return record, True


def _download_source() -> None:
    url = f"https://codeload.{'git'}hub.com/{SOURCE_REPO}/tar.gz/{SOURCE_COMMIT}"
    env_root().mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as response:
        data = response.read()
    with tempfile.TemporaryDirectory(dir=env_root()) as tmp:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(tmp, filter="data")
        (top,) = Path(tmp).iterdir()
        if source_dir().exists():
            shutil.rmtree(source_dir())
        top.rename(source_dir())


def _run(command: list[str], *, cwd: Path, what: str) -> str:
    # Inherited from reelcut's own venv, these would point uv at the wrong environment.
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    }
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-STDERR_TAIL:])
        raise DependencyError(f"ACE-Step {what} failed:\n{tail}", hint="check the network, retry")
    return proc.stdout


def default_timeout_s(duration_s: float) -> float:
    """Model load plus generation, with room for a slow machine; the env var overrides it."""
    value = os.environ.get(TIMEOUT_ENV)
    if value:
        try:
            return float(value)
        except ValueError as exc:
            raise UserError(f"{TIMEOUT_ENV}={value!r} is not a number") from exc
    return 600 + 10 * duration_s


def generate(
    *,
    prompt: str,
    duration_s: float,
    bpm: int | None,
    seed: int,
    out: Path,
    timeout_s: float | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> Generated:
    """One generation in a worker subprocess, under the heavy-model lock.

    Raises DependencyError (exit 2) when `setup --music` has not run, InternalError (exit 3)
    when the worker crashes or exceeds the timeout.
    """
    override = os.environ.get(WORKER_ENV)
    if override:
        command = [override]
    else:
        if installed() is None or not env_python().is_file():
            raise DependencyError(
                f"the ACE-Step environment is not installed in {env_root()}",
                hint=f'run `{APP_NAME} setup --music` once while online, or set "mode": "library"',
            )
        # -I keeps the script's directory off sys.path: this module would shadow `acestep`.
        command = [str(env_python()), "-I", str(worker_script()), "generate"]
    job = {
        "prompt": prompt,
        "duration": round(duration_s, 3),
        "bpm": bpm,
        "seed": seed,
        "out": str(out),
        "project_root": str(source_dir()),
        "dit": DIT,
    }
    limit = timeout_s if timeout_s is not None else default_timeout_s(duration_s)
    with heavy_model_lock("music", on_wait=on_wait):
        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                input=json.dumps(job),
                capture_output=True,
                text=True,
                check=False,
                timeout=limit,
                cwd=source_dir() if source_dir().is_dir() else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise InternalError(
                f"music generation took longer than {limit:.0f} s and was stopped",
                hint=f"raise {TIMEOUT_ENV}, or close memory-hungry apps and retry",
            ) from exc
        elapsed = time.monotonic() - started
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-STDERR_TAIL:])
        if proc.returncode == DependencyError.exit_code:
            raise DependencyError(f"music worker: {tail}", hint=f"run `{APP_NAME} setup --music`")
        raise InternalError(f"music worker exited {proc.returncode}:\n{tail}")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        wav = Path(result["wav"])
    except (ValueError, IndexError, KeyError) as exc:
        raise InternalError(f"music worker printed invalid output: {proc.stdout[-500:]}") from exc
    if not wav.is_file():
        raise InternalError(f"music worker reported {wav}, which does not exist")
    return Generated(
        wav=wav,
        seed=int(result.get("seed", seed)),
        elapsed_s=round(elapsed, 1),
        load_s=float(result.get("load_s", 0.0)),
        generate_s=float(result.get("generate_s", 0.0)),
        peak_rss_mb=float(result.get("peak_rss_mb", 0.0)),
    )
