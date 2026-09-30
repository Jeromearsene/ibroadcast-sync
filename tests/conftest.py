"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_library() -> dict:
    """A minimal but structurally accurate fake iBroadcast library, in the
    real positional-array format (see matching.py's module docstring):
    each category is {id: [field0, field1, ...]} plus a "map" giving each
    field's index.
    """
    return {
        "library": {
            "tracks": {
                "map": {"title": 0, "artist_id": 1, "album_id": 2, "rating": 3},
                "101": ["Song A", "1", "10", 5],
                "102": ["Song B", "2", "11", 0],
                # Two tracks sharing a title, to exercise the by_title/
                # by_title_album/by_title_artist fallback indexes.
                "103": ["Same Title", "3", "12", 3],
                "104": ["Same Title", "4", "13", 0],
            },
            "artists": {
                "map": {"name": 0},
                "1": ["Artist One"],
                "2": ["Artist Two"],
                "3": ["Artist Three"],
                "4": ["Artist Four"],
            },
            "albums": {
                "map": {"name": 0},
                "10": ["Album X"],
                "11": ["Album Y"],
                "12": ["Album Z"],
                "13": ["Album W"],
            },
            "playlists": {
                "map": {"name": 0},
                "500": ["My Playlist"],
            },
        }
    }
