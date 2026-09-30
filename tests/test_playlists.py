"""Tests for ibroadcast_sync.playlists.

Same approach as test_oauth_client.py: a fake client with a mocked
api_call, and get_music_app_playlists() monkeypatched so nothing here
ever shells out to osascript/Music.app.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ibroadcast_sync import playlists as playlists_module
from ibroadcast_sync.oauth_client import IBroadcastClient
from ibroadcast_sync.playlists import sync_playlists


class FakeClient(IBroadcastClient):
    """Stand-in for IBroadcastClient: serves a fixed library and records
    api_call() invocations without making any network request. Subclasses
    the real client (rather than a bare duck-typed class) so it satisfies
    sync_playlists()'s IBroadcastClient type hint directly, no cast needed.

    `mock_api_call` is kept as a separately, properly-typed attribute for
    assertions (`client.mock_api_call.assert_called_once_with(...)`) -
    `client.api_call` itself (what sync_playlists() actually calls) keeps
    the inherited method's static type as far as mypy is concerned, so it
    doesn't expose Mock-specific attributes like `.assert_called_once_with`
    even though it's the same object at runtime."""

    def __init__(self, library: dict) -> None:
        super().__init__()
        self._library = library
        self.mock_api_call = MagicMock()
        self.api_call = self.mock_api_call  # type: ignore[method-assign]

    def fetch_library(self) -> dict:
        return self._library


def _local_playlist(name: str, tracks: list[dict]) -> dict:
    return {"name": name, "tracks": tracks}


def _fake_music_app(monkeypatch: pytest.MonkeyPatch, local_playlists: list[dict]) -> None:
    monkeypatch.setattr(playlists_module, "get_music_app_playlists", lambda verbose=False: local_playlists)


class TestSyncPlaylists:
    def test_creates_new_playlist_on_exact_match(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        local = [
            _local_playlist(
                "Brand New Playlist", [{"title": "Song A", "artist": "Artist One", "album": "Album X"}]
            )
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_called_once_with(
            "createplaylist", {"name": "Brand New Playlist", "tracks": [101]}
        )

    def test_updates_existing_playlist_by_normalized_name(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        # sample_library already has a remote playlist "My Playlist" (id 500).
        local = [
            _local_playlist(
                "my   PLAYLIST", [{"title": "Song A", "artist": "Artist One", "album": "Album X"}]
            )
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_called_once_with("updateplaylist", {"playlist": 500, "tracks": [101]})

    def test_updates_existing_playlist_with_id_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Regression test: `if existing_id:` (truthiness) would treat a
        # playlist whose remote id is 0 as "doesn't exist" and create a
        # duplicate instead of updating it. Needs its own tiny library
        # rather than the shared fixture, which uses id 500.
        library = {
            "library": {
                "tracks": {
                    "map": {"title": 0, "artist_id": 1, "album_id": 2, "rating": 3},
                    "101": ["Song A", "1", "10", 0],
                },
                "artists": {"map": {"name": 0}, "1": ["Artist One"]},
                "albums": {"map": {"name": 0}, "10": ["Album X"]},
                "playlists": {"map": {"name": 0}, "0": ["My Playlist"]},
            }
        }
        local = [
            _local_playlist("My Playlist", [{"title": "Song A", "artist": "Artist One", "album": "Album X"}])
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_called_once_with("updateplaylist", {"playlist": 0, "tracks": [101]})

    def test_dry_run_never_calls_the_api(self, monkeypatch: pytest.MonkeyPatch, sample_library: dict) -> None:
        local = [
            _local_playlist("My Playlist", [{"title": "Song A", "artist": "Artist One", "album": "Album X"}])
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=True)

        client.mock_api_call.assert_not_called()

    def test_playlist_with_no_matched_tracks_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        local = [
            _local_playlist(
                "Nothing Matches", [{"title": "Nonexistent", "artist": "Nobody", "album": "Nowhere"}]
            )
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_not_called()

    def test_uses_fallback_matching_for_playlist_tracks(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        # "Same Title" / "Album Z" (track 103) only exists under "Artist
        # Three" - a different local artist string should still resolve
        # via the title+album fallback.
        local = [
            _local_playlist(
                "Fallback Playlist",
                [{"title": "Same Title", "artist": "A Totally Different Artist", "album": "Album Z"}],
            )
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_called_once_with(
            "createplaylist", {"name": "Fallback Playlist", "tracks": [103]}
        )

    def test_partial_match_still_creates_playlist_with_matched_tracks_only(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        local = [
            _local_playlist(
                "Mixed Playlist",
                [
                    {"title": "Song A", "artist": "Artist One", "album": "Album X"},
                    {"title": "Nonexistent", "artist": "Nobody", "album": "Nowhere"},
                ],
            )
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        client.mock_api_call.assert_called_once_with(
            "createplaylist", {"name": "Mixed Playlist", "tracks": [101]}
        )

    def test_multiple_playlists_each_get_their_own_call(
        self, monkeypatch: pytest.MonkeyPatch, sample_library: dict
    ) -> None:
        local = [
            _local_playlist(
                "Playlist One", [{"title": "Song A", "artist": "Artist One", "album": "Album X"}]
            ),
            _local_playlist(
                "Playlist Two", [{"title": "Song B", "artist": "Artist Two", "album": "Album Y"}]
            ),
        ]
        _fake_music_app(monkeypatch, local)
        client = FakeClient(sample_library)

        sync_playlists(client, dry_run=False)

        assert client.mock_api_call.call_count == 2
