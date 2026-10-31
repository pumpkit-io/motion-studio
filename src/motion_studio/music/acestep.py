"""The isolated ACE-Step 1.5 environment: installing it, and generating with it in a subprocess.

`setup --music` follows the official README (download the source, `uv sync`) into
`<cache>/envs/ace-step/src`, so ACE-Step's dependencies never touch motion-studio's own environment,
and downloads the pinned weights into `<cache>/envs/ace-step/src/checkpoints`, the directory
ACE-Step loads from. `install.json` is written last and records the licence the weights
declare; generation refuses to run without it.
"""

import io
import json
import os
import re
import selectors
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from pydantic import BaseModel, ConfigDict

from motion_studio import APP_NAME, ENV_PREFIX
from motion_studio.errors import DependencyError, InternalError, UserError
from motion_studio.paths import envs_dir
from motion_studio.state import heavy_model_lock

# Pinned on 2026-10-24: the source commit of ace-step/ACE-Step-1.5 and the weights revision.
SOURCE_REPO = "ace-step/ACE-Step-1.5"
SOURCE_COMMIT = "ca1e85fe9430179831e6bc6be790c332190a3866"
WEIGHTS_REPO = "ACE-Step/Ace-Step1.5"
WEIGHTS_REVISION = "19671f406d603126926c1b7e2adc169acbcade22"
DIT = "acestep-v15-turbo"
MODEL = f"{WEIGHTS_REPO}@{WEIGHTS_REVISION[:7]} ({DIT})"

# Replaces the worker command (the env's Python running acestep_worker.py) with an executable.
WORKER_ENV = f"{ENV_PREFIX}_MUSIC_WORKER"
TIMEOUT_ENV = f"{ENV_PREFIX}_MUSIC_TIMEOUT_S"
MIN_FREE_MEMORY_ENV = f"{ENV_PREFIX}_MIN_FREE_MEMORY_GB"
# The worker peaked at 1.8 GB on the build machine; this leaves room for the rest of the system.
MIN_FREE_MEMORY_GB = 2.0
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
    # Inherited from motion_studio's own venv, these would point uv at the wrong environment.
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


class LowMemory(UserError):
    """Too little free memory to start the next generation; those already made stand."""


@dataclass
class Session:
    """Generations in one worker process, so the model loads once, under the heavy-model lock.

    The worker starts at the first `generate`; a session that generates nothing never takes the
    lock. Before each generation the free memory is checked against `min_free_memory_gb()`.
    """

    on_wait: Callable[[str], None] | None = None
    timeout_s: float | None = None
    loads: int = 0
    _stack: ExitStack | None = None
    _proc: subprocess.Popen[str] | None = None
    _stderr: IO[str] | None = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def check_memory(self, what: str) -> None:
        """Raise LowMemory naming `what` when free memory is under the threshold."""
        need = min_free_memory_gb()
        if need <= 0:
            return
        free = free_memory_gb()
        if free is not None and free < need:
            raise LowMemory(
                f"only {free:.1f} GB of memory free before {what}; ACE-Step needs {need:g} GB",
                hint=f"close memory-hungry apps and run it again, or set {MIN_FREE_MEMORY_ENV}",
            )

    def generate(
        self, *, prompt: str, duration_s: float, bpm: int | None, seed: int, out: Path
    ) -> Generated:
        """One generation. Raises DependencyError (exit 2) when `setup --music` has not run,
        InternalError (exit 3) when the worker crashes or exceeds the timeout."""
        proc = self._start()
        job = {
            "prompt": prompt,
            "duration": round(duration_s, 3),
            "bpm": bpm,
            "seed": seed,
            "out": str(out),
            "project_root": str(source_dir()),
            "dit": DIT,
        }
        limit = self.timeout_s if self.timeout_s is not None else default_timeout_s(duration_s)
        started = time.monotonic()
        assert proc.stdin is not None and proc.stdout is not None
        # A worker that died already shows up below as an exit, with its stderr.
        with suppress(BrokenPipeError):
            proc.stdin.write(json.dumps(job) + "\n")
            proc.stdin.flush()
        line = _read_line(proc, limit)
        elapsed = time.monotonic() - started
        if line is None:
            proc.kill()
            proc.wait()
            raise InternalError(
                f"music generation took longer than {limit:.0f} s and was stopped",
                hint=f"raise {TIMEOUT_ENV}, or close memory-hungry apps and retry",
            )
        if not line:
            self._raise_exit(proc)
        try:
            result = json.loads(line)
            wav = Path(result["wav"])
        except (ValueError, KeyError) as exc:
            raise InternalError(f"music worker printed invalid output: {line[-500:]}") from exc
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

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.stdin is not None:
                with suppress(BrokenPipeError):
                    proc.stdin.close()
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._stderr = None
        stack, self._stack = self._stack, None
        if stack is not None:
            stack.close()

    def _start(self) -> subprocess.Popen[str]:
        if self._proc is not None:
            return self._proc
        command = _worker_command()
        stack = ExitStack()
        stack.enter_context(heavy_model_lock("music", on_wait=self.on_wait))
        self._stack = stack
        # A file, not a pipe: the model's chatter could fill a pipe and block the worker.
        log = tempfile.TemporaryFile("w+", encoding="utf-8")  # noqa: SIM115, the stack closes it
        self._stderr = stack.enter_context(log)
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            cwd=source_dir() if source_dir().is_dir() else None,
        )
        self.loads += 1
        return self._proc

    def _raise_exit(self, proc: subprocess.Popen[str]) -> None:
        code = proc.wait()
        tail = ""
        if self._stderr is not None:
            self._stderr.seek(0)
            tail = "\n".join(self._stderr.read().strip().splitlines()[-STDERR_TAIL:])
        self._proc = None
        if code == DependencyError.exit_code:
            raise DependencyError(f"music worker: {tail}", hint=f"run `{APP_NAME} setup --music`")
        raise InternalError(f"music worker exited {code}:\n{tail}")


def _worker_command() -> list[str]:
    override = os.environ.get(WORKER_ENV)
    if override:
        return [override]
    if installed() is None or not env_python().is_file():
        raise DependencyError(
            f"the ACE-Step environment is not installed in {env_root()}",
            hint=f'run `{APP_NAME} setup --music` once while online, or set "mode": "library"',
        )
    # -I keeps the script's directory off sys.path: this module would shadow `acestep`.
    return [str(env_python()), "-I", str(worker_script()), "generate"]


def _read_line(proc: subprocess.Popen[str], timeout_s: float) -> str | None:
    """The worker's next stdout line, "" when it exited, or None after `timeout_s`."""
    assert proc.stdout is not None
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        if not selector.select(timeout_s):
            return None
    return proc.stdout.readline().strip()


def min_free_memory_gb() -> float:
    """The free-memory threshold in GB: the env override if set, else MIN_FREE_MEMORY_GB."""
    value = os.environ.get(MIN_FREE_MEMORY_ENV)
    try:
        return float(value) if value else MIN_FREE_MEMORY_GB
    except ValueError as exc:
        raise UserError(f"{MIN_FREE_MEMORY_ENV}={value!r} is not a number") from exc


def free_memory_gb() -> float | None:
    """Memory the system can hand out without swapping, or None when it cannot be read."""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        found = re.search(r"^MemAvailable:\s+(\d+) kB", meminfo.read_text(), re.M)
        return int(found.group(1)) / 1e6 if found else None
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    page = re.search(r"page size of (\d+) bytes", out)
    if page is None:
        return None
    # macOS reclaims inactive, speculative and purgeable pages before it swaps.
    kinds = ("free", "inactive", "speculative", "purgeable")
    pages = 0
    for kind in kinds:
        found = re.search(rf"^Pages {kind}:\s+(\d+)\.", out, re.M)
        pages += int(found.group(1)) if found else 0
    return pages * int(page.group(1)) / 1e9
