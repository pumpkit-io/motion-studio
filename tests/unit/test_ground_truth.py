"""The committed fixture ground truth, which CI tests read without the generated media."""

import itertools
import json
from pathlib import Path

import pytest

GROUND_TRUTH = Path(__file__).resolve().parents[1] / "fixtures" / "ground_truth"


@pytest.mark.parametrize("name", ["en_talking", "it_talking"])
def test_utterances_and_pauses_between_them_tile_the_whole_clip(name: str) -> None:
    truth = json.loads((GROUND_TRUTH / f"{name}.json").read_text())
    outer = [s for s in truth["silences"] if s["context"] != "around_filler"]
    spans = sorted(
        [(s["start_ms"], s["end_ms"]) for s in [*outer, *truth["utterances"]]],
    )
    assert spans[0][0] == 0
    assert spans[-1][1] == truth["duration_ms"]
    assert all(a[1] == b[0] for a, b in itertools.pairwise(spans))


@pytest.mark.parametrize("name", ["en_talking", "it_talking"])
def test_fillers_and_their_pauses_sit_inside_an_utterance(name: str) -> None:
    truth = json.loads((GROUND_TRUTH / f"{name}.json").read_text())
    inner = [s for s in truth["silences"] if s["context"] == "around_filler"]
    for span in [*truth["fillers"], *inner]:
        assert any(
            u["start_ms"] < span["start_ms"] and span["end_ms"] < u["end_ms"]
            for u in truth["utterances"]
        )
