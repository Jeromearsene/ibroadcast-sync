"""Tests for ibroadcast_sync.ratings."""

from __future__ import annotations

import pytest

from ibroadcast_sync.ratings import itunes_rating_to_ibroadcast


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
