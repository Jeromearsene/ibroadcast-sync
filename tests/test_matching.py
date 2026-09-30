"""Tests for ibroadcast_sync.matching."""

from __future__ import annotations

from ibroadcast_sync.matching import (
    get_field,
    index_remote_playlists,
    index_remote_ratings,
    index_remote_tracks,
    normalize,
    resolve_track_id,
)


class TestNormalize:
    def test_lowercases_and_strips(self) -> None:
        assert normalize("  Hello World  ") == "hello world"

    def test_strips_accents(self) -> None:
        assert normalize("Café") == "cafe"
        assert normalize("Björk") == "bjork"

    def test_converts_typographic_apostrophe(self) -> None:
        # A "smart" right single quote (U+2019) must normalize identically
        # to a plain ASCII apostrophe, since Music.app and iBroadcast don't
        # always agree on which one they use.
        assert normalize("You\u2019ve Got It") == normalize("You've Got It")

    def test_converts_typographic_dashes(self) -> None:
        assert normalize("Rock\u2013n\u2013Roll") == normalize("Rock-n-Roll")

    def test_collapses_whitespace(self) -> None:
        assert normalize("Too   Many\tSpaces") == "too many spaces"

    def test_empty_and_none(self) -> None:
        assert normalize("") == ""
        assert normalize(None) == ""

    def test_non_breaking_space(self) -> None:
        assert normalize("A\u00a0B") == "a b"


class TestGetField:
    def test_reads_field_by_map_index(self) -> None:
        record = ["Title Value", "42"]
        field_map = {"title": 0, "artist_id": 1}
        assert get_field(record, field_map, "title") == "Title Value"
        assert get_field(record, field_map, "artist_id") == "42"

    def test_missing_key_returns_default(self) -> None:
        assert get_field(["a"], {"title": 0}, "missing", "fallback") == "fallback"
        assert get_field(["a"], {"title": 0}, "missing") is None

    def test_index_out_of_range_returns_default(self) -> None:
        assert get_field(["a"], {"title": 5}, "title", "fallback") == "fallback"

    def test_non_list_record_returns_default(self) -> None:
        assert get_field(None, {"title": 0}, "title", "fallback") == "fallback"


class TestIndexRemoteTracks:
    def test_primary_exact_match(self, sample_library: dict) -> None:
        primary, *_ = index_remote_tracks(sample_library)
        assert primary[("song a", "artist one", "album x")] == 101

    def test_by_title_album_fallback_groups_by_artist(self, sample_library: dict) -> None:
        _, by_title_album, _, _ = index_remote_tracks(sample_library)
        # "Same Title" tracks 103/104 have different albums, so neither
        # collides in the by_title_album index for their own album.
        assert by_title_album[("same title", "album z")] == [("artist three", 103)]
        assert by_title_album[("same title", "album w")] == [("artist four", 104)]

    def test_by_title_artist_fallback(self, sample_library: dict) -> None:
        _, _, by_title_artist, _ = index_remote_tracks(sample_library)
        assert by_title_artist[("same title", "artist three")] == [("album z", 103)]

    def test_by_title_diagnostic_index_collects_both(self, sample_library: dict) -> None:
        *_, by_title = index_remote_tracks(sample_library)
        candidates = by_title["same title"]
        assert len(candidates) == 2
        track_ids = {c[2] for c in candidates}
        assert track_ids == {103, 104}

    def test_unknown_title_absent(self, sample_library: dict) -> None:
        primary, *_ = index_remote_tracks(sample_library)
        assert ("nonexistent", "nobody", "nowhere") not in primary


class TestIndexRemoteRatings:
    def test_maps_track_id_to_rating(self, sample_library: dict) -> None:
        ratings = index_remote_ratings(sample_library)
        assert ratings[101] == 5
        assert ratings[102] == 0
        assert ratings[103] == 3


class TestIndexRemotePlaylists:
    def test_maps_normalized_name_to_id(self, sample_library: dict) -> None:
        index = index_remote_playlists(sample_library)
        assert index["my playlist"] == 500
        assert index[normalize("My Playlist")] == 500


class TestResolveTrackId:
    def test_exact_match_has_no_fallback(self, sample_library: dict) -> None:
        primary, by_title_album, by_title_artist, _ = index_remote_tracks(sample_library)
        track_id, fallback = resolve_track_id(
            "Song A", "Artist One", "Album X", primary, by_title_album, by_title_artist
        )
        assert track_id == 101
        assert fallback is None

    def test_title_album_fallback_when_artist_differs(self, sample_library: dict) -> None:
        primary, by_title_album, by_title_artist, _ = index_remote_tracks(sample_library)
        # "Same Title" / "Album Z" only exists with "Artist Three" (103) -
        # a different artist string should still resolve via the fallback.
        track_id, fallback = resolve_track_id(
            "Same Title", "Some Other Artist", "Album Z", primary, by_title_album, by_title_artist
        )
        assert track_id == 103
        assert fallback == "title_album"

    def test_title_artist_fallback_when_album_differs(self, sample_library: dict) -> None:
        primary, by_title_album, by_title_artist, _ = index_remote_tracks(sample_library)
        track_id, fallback = resolve_track_id(
            "Same Title", "Artist Three", "Some Other Album", primary, by_title_album, by_title_artist
        )
        assert track_id == 103
        assert fallback == "title_artist"

    def test_no_match_returns_none(self, sample_library: dict) -> None:
        primary, by_title_album, by_title_artist, _ = index_remote_tracks(sample_library)
        track_id, fallback = resolve_track_id(
            "Nonexistent", "Nobody", "Nowhere", primary, by_title_album, by_title_artist
        )
        assert track_id is None
        assert fallback is None

    def test_ambiguous_fallback_is_not_used(self, sample_library: dict) -> None:
        # "Same Title" alone (no album/artist match) is ambiguous between
        # tracks 103 and 104 - resolve_track_id must not guess.
        primary, by_title_album, by_title_artist, _ = index_remote_tracks(sample_library)
        track_id, fallback = resolve_track_id(
            "Same Title", "Nobody Known", "Unknown Album Entirely", primary, by_title_album, by_title_artist
        )
        assert track_id is None
        assert fallback is None
