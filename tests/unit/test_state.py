import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from motion_studio.errors import DependencyError, UserError
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.state import (
    ensure_free_disk,
    heavy_model_lock,
    load_state,
    mark_done,
    project_lock,
    record_warning,
    stage_is_fresh,
)


@pytest.fixture
def project(tmp_path: Path) -> ProjectPaths:
    paths = project_paths(tmp_path, "demo")
    paths.raw.mkdir(parents=True)
    paths.media.mkdir()
    paths.project_toml.write_text("", encoding="utf-8")
    return paths


def bump(path: Path, text: str) -> None:
    """Rewrite a file and move its mtime forward so a stat-based fingerprint must notice."""
    path.write_text(text, encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))


def test_stage_never_run_is_not_fresh(project: ProjectPaths) -> None:
    assert not stage_is_fresh(project, "ingest", [project.raw])


def test_stage_is_fresh_after_mark_done_with_same_inputs(project: ProjectPaths) -> None:
    (project.raw / "a.mov").write_text("take", encoding="utf-8")
    out = project.media / "c1.mp4"
    out.write_text("mezz", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[out])
    assert stage_is_fresh(project, "ingest", [project.raw])

    record = load_state(project).stages["ingest"]
    assert record.status == "done"
    assert record.outputs == ["media/c1.mp4"]
    assert record.finished_at is not None


def test_changed_input_makes_stage_stale(project: ProjectPaths) -> None:
    clip = project.raw / "a.mov"
    clip.write_text("take", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[])
    bump(clip, "take two")
    assert not stage_is_fresh(project, "ingest", [project.raw])


def test_a_changed_input_of_the_same_size_makes_stage_stale(project: ProjectPaths) -> None:
    clip = project.raw / "a.mov"
    clip.write_text("take one", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[])
    bump(clip, "take two")
    assert not stage_is_fresh(project, "ingest", [project.raw])


def test_touching_an_input_without_changing_it_keeps_the_stage_fresh(
    project: ProjectPaths,
) -> None:
    clip = project.raw / "a.mov"
    clip.write_text("take", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[])
    bump(clip, "take")
    assert stage_is_fresh(project, "ingest", [project.raw])


def test_an_unchanged_size_and_mtime_reuse_the_recorded_content_hash(
    project: ProjectPaths,
) -> None:
    # The fast path: a file whose size and mtime hold is not read again, so `status` stays fast.
    clip = project.raw / "a.mov"
    clip.write_text("take one", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[])
    stat = clip.stat()
    clip.write_text("take two", encoding="utf-8")
    os.utime(clip, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert stage_is_fresh(project, "ingest", [project.raw])


def test_added_file_in_an_input_directory_makes_stage_stale(project: ProjectPaths) -> None:
    (project.raw / "a.mov").write_text("take", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[])
    (project.raw / "b.mov").write_text("another", encoding="utf-8")
    assert not stage_is_fresh(project, "ingest", [project.raw])


def test_changed_parameters_make_stage_stale(project: ProjectPaths) -> None:
    mark_done(project, "analyze", [project.raw], outputs=[], params={"language": "en"})
    assert stage_is_fresh(project, "analyze", [project.raw], params={"language": "en"})
    assert not stage_is_fresh(project, "analyze", [project.raw], params={"language": "it"})


def test_missing_output_makes_stage_stale(project: ProjectPaths) -> None:
    out = project.media / "c1.mp4"
    out.write_text("mezz", encoding="utf-8")
    mark_done(project, "ingest", [project.raw], outputs=[out])
    out.unlink()
    assert not stage_is_fresh(project, "ingest", [project.raw])


def test_fallback_warnings_are_recorded(project: ProjectPaths) -> None:
    record_warning(project, "ingest", "arnndn used instead of DeepFilterNet")
    mark_done(project, "ingest", [project.raw], outputs=[])
    assert load_state(project).stages["ingest"].warnings == ["arnndn used instead of DeepFilterNet"]


def test_state_file_is_versioned_json(project: ProjectPaths) -> None:
    mark_done(project, "ingest", [project.raw], outputs=[])
    assert '"schema_version": 1' in project.state.read_text(encoding="utf-8")


def test_project_lock_refuses_a_second_holder(project: ProjectPaths) -> None:
    with project_lock(project), pytest.raises(UserError, match="another"), project_lock(project):
        pass
    with project_lock(project):
        pass


HOLDER = textwrap.dedent(
    """
    import sys, time
    from motion_studio.state import heavy_model_lock
    with heavy_model_lock("asr"):
        print("held", flush=True)
        time.sleep(float(sys.argv[1]))
    """
)


def test_heavy_model_lock_makes_a_second_holder_wait(isolated_cache: Path) -> None:
    hold_s = 1.5
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(hold_s)],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "MOTION_STUDIO_CACHE_DIR": str(isolated_cache)},
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        waited_for: list[str] = []
        start = time.monotonic()
        with heavy_model_lock("faces", on_wait=waited_for.append):
            waited = time.monotonic() - start
        assert waited >= hold_s * 0.6
        assert waited_for and "asr" in waited_for[0]
    finally:
        holder.wait(timeout=10)


def test_heavy_model_lock_times_out(isolated_cache: Path) -> None:
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, "3"],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "MOTION_STUDIO_CACHE_DIR": str(isolated_cache)},
    )
    try:
        assert holder.stdout is not None
        holder.stdout.readline()
        with (
            pytest.raises(DependencyError, match="heavy-model lock"),
            heavy_model_lock("faces", timeout_s=0.3),
        ):
            pass
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_heavy_model_lock_is_free_again_after_release() -> None:
    with heavy_model_lock("asr"):
        pass
    with heavy_model_lock("faces", timeout_s=0.1):
        pass


def test_free_disk_guard_raises_below_threshold(tmp_path: Path) -> None:
    with pytest.raises(DependencyError, match="free") as excinfo:
        ensure_free_disk(tmp_path, threshold_gb=10**9)
    assert excinfo.value.exit_code == 2
    assert ensure_free_disk(tmp_path, threshold_gb=0) >= 0
