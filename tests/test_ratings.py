"""Tests for ibroadcast_sync.ratings."""

from __future__ import annotations

from typing import Any

import pytest

from ibroadcast_sync import ratings as ratings_module
from ibroadcast_sync.oauth_client import IBroadcastClient, ServerError
from ibroadcast_sync.ratings import decayed_delay, itunes_rating_to_ibroadcast, next_retry_delay


@pytest.mark.parametrize(
    ("rating_0_100", "expected_stars"),
    [
        (0, 0),
        (10, 1),  # 0.5 stars rounds up (round-half-up, not banker's rounding)
        (20, 1),
        (30, 2),  # 1.5 stars rounds up to 2
        (40, 2),
        (50, 3),  # 2.5 stars rounds up to 3
        (60, 3),
        (80, 4),
        (90, 5),  # 4.5 stars rounds up to 5
        (100, 5),
    ],
)
def test_itunes_rating_to_ibroadcast(rating_0_100: int, expected_stars: int) -> None:
    assert itunes_rating_to_ibroadcast(rating_0_100) == expected_stars


def test_result_is_always_clamped_to_0_5() -> None:
    for rating in range(0, 101):
        assert 0 <= itunes_rating_to_ibroadcast(rating) <= 5


class TestNextRetryDelay:
    def test_doubles_the_delay(self) -> None:
        assert next_retry_delay(0.3, max_delay=8.0) == pytest.approx(0.6)

    def test_caps_at_max_delay(self) -> None:
        assert next_retry_delay(6.0, max_delay=8.0) == 8.0
        assert next_retry_delay(8.0, max_delay=8.0) == 8.0


class TestDecayedDelay:
    # Regression tests: the adaptive delay used to only ever grow (on a
    # rate-limit) and never shrink back down - a single early throttling
    # spike would keep every remaining track in the run throttled at
    # max_delay, turning the README's ~15-20 min estimate for a large
    # library into several hours.

    def test_no_change_before_the_streak_completes(self) -> None:
        delay, streak = decayed_delay(2.0, consecutive_successes=5, min_delay=0.3, decay_after=20)
        assert delay == 2.0
        assert streak == 5

    def test_halves_the_delay_once_the_streak_completes(self) -> None:
        delay, streak = decayed_delay(2.0, consecutive_successes=20, min_delay=0.3, decay_after=20)
        assert delay == 1.0
        assert streak == 0

    def test_never_drops_below_min_delay(self) -> None:
        delay, streak = decayed_delay(0.4, consecutive_successes=20, min_delay=0.3, decay_after=20)
        assert delay == 0.3
        assert streak == 0


class _DeadAuthClient(IBroadcastClient):
    def __init__(self, library: dict) -> None:
        super().__init__()
        self.library = library
        self.rated_calls = 0

    def fetch_library(self, retry: bool = True) -> dict:
        return self.library

    def api_call(self, mode: str, extra: dict[str, Any] | None = None, retry: bool = True) -> Any:
        self.rated_calls += 1
        self.auth_dead.set()
        raise ServerError("authentication is no longer valid")


class TestDeadAuthStopsRatingSync:
    def test_stops_after_authentication_dies(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        local_tracks = [
            {"title": "Song A", "artist": "Artist One", "album": "Album X", "rating": 80},
            {"title": "Song B", "artist": "Artist Two", "album": "Album Y", "rating": 20},
        ]
        monkeypatch.setattr(ratings_module, "get_music_app_ratings", lambda verbose=False: local_tracks)
        monkeypatch.setattr(ratings_module.time, "sleep", lambda _delay: None)
        client = _DeadAuthClient(sample_library)

        ratings_module.sync_ratings(client, dry_run=False)

        assert client.rated_calls == 1
