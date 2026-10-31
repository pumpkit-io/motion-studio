"""The whole pipeline on the EN and IT fixtures, driven only through the `motion-studio` CLI.

Each step runs the installed `motion-studio` executable in a subprocess, as an editing agent would,
and the only file the test writes into the workspace is edl.json. Uses the real cache: run
`motion-studio setup --music` and `just fixtures` first. Per-stage wall times, stills and check
reports land in MOTION_STUDIO_E2E_OUT (default build/e2e/ in the repo).
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pytest

from motion_studio.asr import DEFAULT_MODELS, model_path, resolve_backend
from motion_studio.asr.vad import vad_model_path
from motion_studio.audio.enhance import deep_filter_binary
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe
from motion_studio.paths import envs_dir
from motion_studio.render.renderer import find_renderer
from motion_studio.text import normalise_token

pytestmark = [
    pytest.mark.slow,
    pytest.mark.mac,
    pytest.mark.models,
    pytest.mark.renderer,
    pytest.mark.music,
]

REPO = Path(__file__).resolve().parents[2]
MEDIA = REPO / "tests" / "fixtures" / "media"
TRUTH = REPO / "tests" / "fixtures" / "ground_truth"
MOTION_STUDIO = Path(sys.executable).with_name("motion-studio")
FORMATS = {"9x16": (540, 960), "16x9": (960, 540)}
TOLERANCE_S = 0.15
LUFS_TARGET = -14.0


def out_dir() -> Path:
    return Path(os.environ.get("MOTION_STUDIO_E2E_OUT") or REPO / "build" / "e2e")


@dataclass
class Run:
    language: str
    workspace: Path
    timings: list[tuple[str, float]] = field(default_factory=list[tuple[str, float]])
    results: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def project(self) -> Path:
        return self.workspace / "projects" / "demo"

    def motion_studio(self, stage: str, *args: str, ok_codes: tuple[int, ...] = (0,)) -> Any:
        started = time.monotonic()
        proc = subprocess.run(
            [str(MOTION_STUDIO), *args, "--json"],
            cwd=self.workspace if self.workspace.exists() else self.workspace.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        self.timings.append((stage, time.monotonic() - started))
        assert proc.returncode in ok_codes, (
            f"motion-studio {' '.join(args)}\n{proc.stdout}{proc.stderr}"
        )
        body = json.loads(proc.stdout)
        self.results[stage] = body
        return body

    def json(self, relative: str) -> Any:
        return json.loads((self.project / relative).read_text(encoding="utf-8"))


def require_setup() -> None:
    if not (MEDIA / "en_talking.mov").exists():
        pytest.skip("fixtures not generated; run `just fixtures`")
    if not MOTION_STUDIO.exists():
        pytest.skip(f"no motion-studio executable next to {sys.executable}")
    backend = resolve_backend("auto")
    if not vad_model_path().is_file() or model_path(DEFAULT_MODELS[backend]) is None:  # type: ignore[index]
        pytest.skip("speech models not in the cache; run `motion-studio setup`")
    if not (envs_dir() / "ace-step" / "install.json").is_file():
        pytest.skip("ACE-Step not installed; run `motion-studio setup --music`")
    find_renderer()


def kept_ids(segment: dict[str, Any]) -> list[str]:
    clip, first = segment["from"].split(".w")
    last = segment["to"].split(".w")[1]
    return [f"{clip}.w{n}" for n in range(int(first), int(last) + 1)]


def add_edits(run: Run) -> None:
    """What an agent adds to the draft: a title, a zoom, an image card and a B-roll PiP."""
    edl = run.json("edl.json")
    hook, body, retake, outro = (kept_ids(s) for s in edl["segments"])
    edl["formats"] = list(FORMATS)
    edl["events"] = [
        {"type": "title", "text": "End to end", "start": hook[0], "end": hook[2]},
        {"type": "image", "asset": "i1", "start": body[-4], "end": body[-1]},
        {"type": "zoom", "at": retake[3], "hold_until": retake[7], "scale": 1.25},
        {"type": "broll", "asset": "b1", "start": outro[0], "end": outro[-2], "mode": "pip"},
    ]
    (run.project / "edl.json").write_text(json.dumps(edl, indent=2), encoding="utf-8")


@pytest.fixture(scope="module", params=["en", "it"])
def pipeline(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Run]:
    require_setup()
    language: str = request.param
    with pytest.MonkeyPatch.context() as monkeypatch:
        deep_filter = deep_filter_binary()
        if deep_filter:
            monkeypatch.setenv("MOTION_STUDIO_DEEP_FILTER", str(deep_filter))
        run = Run(language, tmp_path_factory.mktemp(language) / "reels")
        sources = [MEDIA / f"{language}_talking.mov", MEDIA / "broll.mp4", MEDIA / "image.png"]
        run.motion_studio("init", "init", str(run.workspace))
        run.motion_studio("new", "new", "demo", "--from", *map(str, sources))
        run.motion_studio("ingest", "ingest", "demo")
        run.motion_studio("analyze", "analyze", "demo")
        run.motion_studio("look-asset", "look-asset", "demo", "b1")
        run.motion_studio("plan draft", "plan", "draft", "demo")
        add_edits(run)
        run.motion_studio("plan validate", "plan", "validate", "demo")
        run.motion_studio("music", "music", "demo")
        run.motion_studio("plan validate (beats)", "plan", "validate", "demo")
        run.motion_studio("render preview", "render", "demo", "--preview")
        run.motion_studio("check", "check", "demo", "--preview", ok_codes=(0, 1))
        record(run)
        yield run


def record(run: Run) -> None:
    """Write per-stage timings, the check report and stills for the visual acceptance pass."""
    target = out_dir() / run.language
    target.mkdir(parents=True, exist_ok=True)
    timings = {stage: round(seconds, 1) for stage, seconds in run.timings}
    timings["total"] = round(sum(s for _, s in run.timings), 1)
    (target / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"\n{run.language} stage timings (s): {json.dumps(timings)}")
    for name in ("report.md", "cuts.png"):
        source = run.project / "check" / name
        if source.exists():
            (target / name).write_bytes(source.read_bytes())
    timeline = run.json("build/timeline.json")
    fps = timeline["fps"]
    moments = {"start": 0.5, "cut1": run.results["render preview"]["cuts_s"][0] + 0.1}
    for event in timeline["events"]:
        moments.setdefault(event["type"], (event["start"] + event["end"]) / 2 / fps)
    for output in run.results["render preview"]["outputs"]:
        for name, t in moments.items():
            png = target / f"{output['format']}_{name}.png"
            run_ffmpeg(["-y", "-ss", f"{t:.3f}", "-i", output["path"], "-frames:v", "1", png])


def truth(language: str) -> dict[str, Any]:
    return json.loads((TRUTH / f"{language}_talking.json").read_text(encoding="utf-8"))


def gaps(analysis: dict[str, Any]) -> list[tuple[float, float]]:
    edges = [0.0]
    for region in analysis["vad"]:
        edges += [region["start"], region["end"]]
    edges.append(analysis["clip"]["duration_s"])
    return [(a, b) for a, b in zip(edges[::2], edges[1::2], strict=True) if b > a]


def probe(path: str) -> tuple[int, int, float]:
    out = run_ffprobe(["-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return int(video["width"]), int(video["height"]), float(video["duration"])


def test_analyze_detects_the_fixture_language(pipeline: Run) -> None:
    clips = {c["id"]: c for c in pipeline.results["analyze"]["clips"]}
    assert clips["c1"]["language"] == pipeline.language
    assert pipeline.results["analyze"]["language"] == pipeline.language
    assert (clips["c1"]["role"], clips["b1"]["role"], clips["i1"]["role"]) == (
        "aroll",
        "broll",
        "image",
    )


def test_at_least_90_percent_of_the_known_silences_are_found_within_150_ms(pipeline: Run) -> None:
    found = gaps(pipeline.json("analysis/c1.json"))
    silences = truth(pipeline.language)["silences"]

    def near(s: dict[str, Any], a: float, b: float) -> bool:
        return (
            abs(a - s["start_ms"] / 1000) <= TOLERANCE_S
            and abs(b - s["end_ms"] / 1000) <= TOLERANCE_S
        )

    hits = [s for s in silences if any(near(s, a, b) for a, b in found)]
    assert len(hits) / len(silences) >= 0.9, f"found {found}, expected {silences}"


def test_the_known_filler_is_tagged_hard_within_150_ms(pipeline: Run) -> None:
    (filler,) = truth(pipeline.language)["fillers"]
    hard = [w for w in pipeline.json("analysis/c1.json")["words"] if w["filler"] == "hard"]
    assert any(abs(w["start"] - filler["start_ms"] / 1000) <= TOLERANCE_S for w in hard), hard


def test_the_retake_pair_is_clustered_with_the_complete_take_winning(pipeline: Run) -> None:
    pair = truth(pipeline.language)["retake"]
    (cluster,) = pipeline.json("analysis/retakes.json")["clusters"]
    utterances = {u["id"]: u for u in pipeline.json("analysis/c1.json")["utterances"]}
    winner, loser = utterances[cluster["winner"]], utterances[cluster["members"][1]]
    utt = truth(pipeline.language)["utterances"]
    assert abs(winner["start"] - utt[pair["winner"]]["start_ms"] / 1000) <= TOLERANCE_S
    assert abs(loser["start"] - utt[pair["abandoned"]]["start_ms"] / 1000) <= TOLERANCE_S
    assert winner["complete"] and not loser["complete"]


def test_the_timeline_keeps_the_script_without_the_filler_or_the_abandoned_take(
    pipeline: Run,
) -> None:
    gt = truth(pipeline.language)
    expected = [
        normalise_token(word)
        for i, u in enumerate(gt["utterances"])
        if i != gt["retake"]["abandoned"]
        for word in u["text"].split()
        if normalise_token(word) != normalise_token(gt["fillers"][0]["text"])
    ]
    heard = [normalise_token(w["text"]) for w in pipeline.json("build/timeline.json")["words"]]
    assert normalise_token(gt["fillers"][0]["text"]) not in heard
    assert SequenceMatcher(a=expected, b=heard).ratio() >= 0.95, (expected, heard)


def test_music_is_generated_without_vocals_and_its_beats_reach_the_timeline(pipeline: Run) -> None:
    music = pipeline.results["music"]
    info = pipeline.json("build/music.json")
    assert info["mode"] == "generate"
    assert info["beats"]
    assert any(a["accepted"] for a in info["attempts"]), music
    assert pipeline.json("build/timeline.json")["music_path"] == "build/music.wav"


def test_both_previews_have_the_format_size_and_the_timeline_duration(pipeline: Run) -> None:
    timeline = pipeline.json("build/timeline.json")
    expected_s = timeline["duration_frames"] / timeline["fps"]
    outputs = {o["format"]: o for o in pipeline.results["render preview"]["outputs"]}
    assert set(outputs) == set(FORMATS)
    for fmt, size in FORMATS.items():
        width, height, duration = probe(outputs[fmt]["path"])
        assert (width, height) == size
        assert abs(duration - expected_s) <= 1 / timeline["fps"] + 1e-3, (fmt, duration)


def test_check_passes_with_loudness_on_target(pipeline: Run) -> None:
    body = pipeline.results["check"]
    blocking = [i for i in body["issues"] if i["severity"] == "blocking"]
    assert body["verdict"] == "pass", blocking
    assert set(body["formats"]) == set(FORMATS)
    for fmt, loudness in body["metrics"]["loudness"].items():
        assert abs(loudness["integrated_lufs"] - LUFS_TARGET) <= 1, (fmt, loudness)
        assert loudness["true_peak_db"] <= -1, (fmt, loudness)
    words = body["metrics"]["words"]
    assert words["matched"] >= 0.9 * words["expected"], words
