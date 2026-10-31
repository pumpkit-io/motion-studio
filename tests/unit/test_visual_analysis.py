"""Visual analysers: static stretches and role finalisation, from constructed measurements."""

from motion_studio.analysis import (
    ClipAnalysis,
    ClipInfo,
    Faces,
    FaceSample,
    Span,
    finalise_role,
    find_static,
)

FPS = 2.0


def motion(*runs: tuple[float, float]) -> list[float]:
    """Frame differences at 2 fps: each run is (seconds, difference)."""
    diffs: list[float] = []
    for seconds, value in runs:
        diffs += [value] * round(seconds * FPS)
    return diffs


def test_a_still_stretch_without_speech_is_static() -> None:
    diffs = motion((4.0, 12.0), (3.0, 0.2))

    assert find_static(diffs, FPS, vad=[Span(start=0.5, end=3.8)], duration_s=7.0) == [
        Span(start=4.0, end=7.0)
    ]


def test_speech_inside_a_still_stretch_splits_it_and_short_pieces_are_dropped() -> None:
    diffs = motion((7.0, 0.1))

    static = find_static(diffs, FPS, vad=[Span(start=1.5, end=4.2)], duration_s=7.0)

    assert static == [Span(start=4.2, end=7.0)]


def test_still_stretches_shorter_than_two_seconds_are_not_static() -> None:
    diffs = motion((2.0, 9.0), (1.5, 0.1), (2.0, 9.0))

    assert find_static(diffs, FPS, vad=[], duration_s=5.5) == []


def test_moving_footage_is_never_static() -> None:
    assert find_static(motion((10.0, 6.0)), FPS, vad=[], duration_s=10.0) == []


def test_the_last_stretch_is_clamped_to_the_clip_duration() -> None:
    diffs = motion((3.0, 0.1))

    assert find_static(diffs, FPS, vad=[], duration_s=2.8) == [Span(start=0.0, end=2.8)]


def clip(
    role: str = "aroll",
    *,
    duration_s: float = 10.0,
    speech_s: float = 0.0,
    face_samples: int = 0,
) -> ClipAnalysis:
    info = ClipInfo(id="c1", role=role, source="raw/a.mov", duration_s=duration_s)  # pyright: ignore[reportArgumentType]
    samples = [
        FaceSample(t=i / FPS, cx=0.5, cy=0.4, w=0.3, h=0.2, score=0.9) for i in range(face_samples)
    ]
    vad = [Span(start=0.0, end=speech_s)] if speech_s else []
    return ClipAnalysis(clip=info, vad=vad, faces=Faces(sample_fps=FPS, samples=samples))


def test_speech_and_a_face_in_most_frames_make_a_roll() -> None:
    assert finalise_role(clip(speech_s=6.0, face_samples=15), kind="video") == "aroll"


def test_speech_without_a_face_is_b_roll() -> None:
    assert finalise_role(clip(speech_s=6.0, face_samples=4), kind="video") == "broll"


def test_a_face_without_enough_speech_is_b_roll() -> None:
    assert finalise_role(clip(speech_s=2.5, face_samples=20), kind="video") == "broll"


def test_an_image_stays_an_image_even_with_a_face() -> None:
    assert finalise_role(clip("image", duration_s=0.0, face_samples=1), kind="image") == "image"


def test_a_still_ending_lasts_to_the_clip_end_after_the_last_sampled_frame() -> None:
    diffs = motion((2.5, 0.1))

    assert find_static(diffs, FPS, vad=[], duration_s=3.0) == [Span(start=0.0, end=3.0)]
