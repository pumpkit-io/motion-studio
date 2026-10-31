"""The beat grid product scenes are laid on: the music's beats, or a steady tempo before music."""

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_BPM = 120
DEFAULT_BEATS_PER_BAR = 4


@dataclass(frozen=True)
class BeatGrid:
    """Beat times in output seconds. Position k is beat k; fractions interpolate.

    Before the first beat and after the last, the grid goes on at the nearest beat's spacing,
    so a video longer than the bed still has a grid.
    """

    beats: tuple[float, ...]
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    from_music: bool = False

    @classmethod
    def steady(
        cls, bpm: float = DEFAULT_BPM, beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    ) -> "BeatGrid":
        return cls((0.0, 60 / bpm), beats_per_bar)

    @classmethod
    def of(
        cls, beats: Sequence[float] | None, beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    ) -> "BeatGrid":
        """The music's grid, or the steady default when there are fewer than two beats."""
        times = tuple(sorted(beats or ()))
        if len(times) < 2:
            return cls.steady(beats_per_bar=beats_per_bar)
        return cls(times, beats_per_bar, from_music=True)

    @property
    def bpm(self) -> float:
        """The mean tempo of the grid."""
        return 60 * (len(self.beats) - 1) / (self.beats[-1] - self.beats[0])

    def time_at(self, position: float) -> float:
        k = min(max(math.floor(position), 0), len(self.beats) - 2)
        a, b = self.beats[k], self.beats[k + 1]
        return a + (position - k) * (b - a)

    def position_at(self, t: float) -> float:
        k = min(max(bisect_right(self.beats, t) - 1, 0), len(self.beats) - 2)
        a, b = self.beats[k], self.beats[k + 1]
        return k + (t - a) / (b - a)

    def beat_s_at(self, t: float) -> float:
        """The length of the beat that holds `t`."""
        return self.time_at(math.floor(self.position_at(t)) + 1) - self.time_at(
            math.floor(self.position_at(t))
        )

    def after_beats(self, t: float, beats: float) -> float:
        """The time `beats` after `t`. A whole number of beats ends on the nearest beat."""
        start = self.position_at(t)
        end = start + beats
        if beats == int(beats):
            end = max(round(end), math.floor(start + 1e-9) + 1)
        return self.time_at(end)
