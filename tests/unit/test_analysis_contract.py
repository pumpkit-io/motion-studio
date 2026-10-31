from motion_studio.analysis import ClipAnalysis

GUIDE_EXAMPLE = {
    "schema_version": 1,
    "clip": {
        "id": "c1",
        "role": "aroll",
        "source": "raw/IMG_0412.MOV",
        "mezzanine": "media/c1.mp4",
        "audio": "media/c1.wav",
        "duration_s": 312.4,
        "fps": 30,
        "width": 1080,
        "height": 1920,
        "input_hash": "abc",
    },
    "language": {"code": "it", "confidence": 0.97},
    "words": [
        {
            "id": "c1.w0",
            "text": "Allora",
            "start": 1.02,
            "end": 1.38,
            "conf": 0.91,
            "filler": "soft",
            "utt": "c1.s0",
        },
        {
            "id": "c1.w1",
            "text": "ehm",
            "start": 1.52,
            "end": 1.81,
            "conf": 0.66,
            "filler": "hard",
            "utt": "c1.s0",
        },
    ],
    "utterances": [
        {
            "id": "c1.s0",
            "start": 1.02,
            "end": 6.40,
            "first_word": "c1.w0",
            "last_word": "c1.w14",
            "text": "Allora ehm oggi vi faccio vedere…",
            "complete": True,
        }
    ],
    "pauses": [{"start": 6.40, "end": 8.10, "dur": 1.70, "after_word": "c1.w14"}],
    "unaligned_voice": [{"start": 22.3, "end": 22.7}],
    "vad": [{"start": 1.0, "end": 6.42}],
    "shots": [{"start": 0.0, "end": 312.4}],
    "static": [{"start": 300.1, "end": 312.4}],
    "faces": {
        "sample_fps": 2,
        "samples": [{"t": 1.0, "cx": 0.51, "cy": 0.38, "w": 0.31, "h": 0.22, "score": 0.97}],
    },
}


def test_the_guide_example_round_trips_through_the_analysis_contract() -> None:
    analysis = ClipAnalysis.model_validate(GUIDE_EXAMPLE)

    screen_fields = {"markers_source": None, "markers": [], "cursor": []}
    assert analysis.model_dump(mode="json") == {**GUIDE_EXAMPLE, **screen_fields}
