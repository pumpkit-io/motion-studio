"""The ACE-Step worker, run with the isolated ACE-Step environment's Python, never reelcut's.

It imports only the standard library and ACE-Step, so it must not import reelcut.

    python acestep_worker.py generate   < job JSON on stdin, result JSON on stdout
    python acestep_worker.py download <repo> <revision> <dir>   (used by `setup --music`)

Exit 2 means a missing dependency or weights; anything else non-zero is a bug.
"""

import json
import os
import re
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# The text encoder and DiT must come from the local checkpoints; edit time is offline.
OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
MISSING = 2


def weights_licence(checkpoints: Path) -> dict[str, str | None]:
    """The licence the weights declare: a LICENSE file if any, else the model card's metadata."""
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        path = checkpoints / name
        if path.is_file():
            first = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            return {"licence": first[0] if first else None, "source": name}
    card = checkpoints / "README.md"
    if card.is_file():
        text = card.read_text(encoding="utf-8", errors="replace")
        front = re.match(r"---\n(.*?)\n---", text, re.S)
        if front:
            found = re.search(r"^license:\s*(\S+)\s*$", front.group(1), re.M)
            if found:
                return {"licence": found.group(1), "source": "README.md front matter"}
    return {"licence": None, "source": None}


def download(repo: str, revision: str, dest: Path) -> dict[str, object]:
    from huggingface_hub import snapshot_download  # pyright: ignore[reportMissingImports]

    snapshot_download(repo, revision=revision, local_dir=str(dest))
    return {"repo": repo, "revision": revision, "path": str(dest), **weights_licence(dest)}


def generate(job: dict[str, Any]) -> dict[str, object]:
    os.environ.update(OFFLINE_ENV)
    from acestep.handler import AceStepHandler  # pyright: ignore[reportMissingImports]
    from acestep.inference import (  # pyright: ignore[reportMissingImports]
        GenerationConfig,
        GenerationParams,
        generate_music,
    )

    started = time.monotonic()
    handler = AceStepHandler()
    status, ok = handler.initialize_service(
        project_root=str(job["project_root"]),
        config_path=str(job["dit"]),
        device="auto",
        offload_to_cpu=False,
    )
    if not ok:
        raise RuntimeError(f"ACE-Step failed to load: {status}")
    loaded = time.monotonic()
    seed = int(job["seed"])
    params = GenerationParams(
        task_type="text2music",
        caption=str(job["prompt"]),
        # ACE-Step has no hard instrumental switch without its LM; this tag is the convention
        # its training data uses for tracks without vocals.
        lyrics="[Instrumental]",
        instrumental=True,
        bpm=int(job["bpm"]) if job.get("bpm") else None,
        duration=float(job["duration"]),
        thinking=False,
        seed=seed,
    )
    config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[seed], audio_format="wav")
    with tempfile.TemporaryDirectory() as tmp:
        result = generate_music(handler, None, params, config, save_dir=tmp)
        if not result.success or not result.audios:
            raise RuntimeError(
                f"ACE-Step generation failed: {result.error or result.status_message}"
            )
        audio = result.audios[0]
        out = Path(str(job["out"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(audio["path"], out)
    return {
        "wav": str(out),
        "seed": seed,
        "sample_rate": int(audio.get("sample_rate", 48000)),
        "device": str(getattr(handler, "device", "unknown")),
        "load_s": round(loaded - started, 1),
        "generate_s": round(time.monotonic() - loaded, 1),
        "pid": os.getpid(),
        "peak_rss_mb": _peak_rss_mb(),
    }


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    return round(peak / 1e6 if sys.platform == "darwin" else peak / 1e3, 1)


def main(argv: list[str]) -> int:
    # Model libraries print progress; only the result JSON may reach the parent's stdout.
    out, sys.stdout = sys.stdout, sys.stderr
    try:
        if argv[:1] == ["download"] and len(argv) == 4:
            result = download(argv[1], argv[2], Path(argv[3]))
        elif argv == ["generate"]:
            result = generate(json.loads(sys.stdin.read()))
        else:
            print(__doc__, file=sys.stderr)
            return 1
    except ImportError as exc:
        print(f"ACE-Step environment is incomplete: {exc}", file=sys.stderr)
        return MISSING
    out.write(json.dumps(result) + "\n")
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
