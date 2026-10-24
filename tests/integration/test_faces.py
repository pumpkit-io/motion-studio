"""Face detection with the real models on the public-domain face photo.

Uses the real cache and its heavy-model lock; run `reelcut setup` first.
"""

import shutil
from pathlib import Path

import pytest

from reelcut.vision import FaceJob, detect_faces, mediapipe_model_path, yunet_model_path

pytestmark = [pytest.mark.models]

PHOTO = Path(__file__).resolve().parents[1] / "fixtures" / "faces" / "neil_armstrong_960.jpg"
# The face in the 960x1200 photo (centre and width, normalised), checked by eye on the image.
FACE_CX, FACE_CY, FACE_W = 0.62, 0.27, 0.17
TOLERANCE = 0.06


def require_models() -> None:
    if not mediapipe_model_path().is_file() or not yunet_model_path().is_file():
        pytest.skip("face models not in the cache; run `reelcut setup`")


def photo_job() -> FaceJob:
    return FaceJob(id="i1", path=PHOTO, kind="image", duration_s=0.0, width=960, height=1200)


def assert_finds_the_face(samples: list) -> None:  # pyright: ignore[reportMissingTypeArgument]
    assert len(samples) == 1
    face = samples[0]
    assert face.t == 0.0
    assert abs(face.cx - FACE_CX) < TOLERANCE
    assert abs(face.cy - FACE_CY) < TOLERANCE
    assert abs(face.w - FACE_W) < TOLERANCE
    assert face.score > 0.5


def test_mediapipe_finds_the_face_in_the_photo() -> None:
    require_models()

    run = detect_faces([photo_job()])

    assert run.detector == "mediapipe"
    assert run.fallback_reason is None
    assert_finds_the_face(run.results[0].samples)


def test_without_the_mediapipe_model_yunet_finds_the_face_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_models()
    yunet = yunet_model_path()
    monkeypatch.setenv("REELCUT_CACHE_DIR", str(tmp_path / "cache"))
    yunet_model_path().parent.mkdir(parents=True)
    shutil.copy(yunet, yunet_model_path())

    run = detect_faces([photo_job()])

    assert run.detector == "yunet"
    assert run.fallback_reason is not None and "MediaPipe" in run.fallback_reason
    assert_finds_the_face(run.results[0].samples)
