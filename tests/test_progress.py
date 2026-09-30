"""Tests for ibroadcast_sync.progress."""

from __future__ import annotations

from pathlib import Path

import pytest

from ibroadcast_sync.progress import format_duration, get_file_size, human_size, short_path


class TestShortPath:
    def test_keeps_only_what_follows_music_folder(self) -> None:
        assert short_path("/Users/jerome/Music/Artist/Album/Track.mp3") == "Artist/Album/Track.mp3"

    def test_returns_full_path_when_no_music_segment(self) -> None:
        assert short_path("/data/audio/Track.mp3") == "/data/audio/Track.mp3"

    def test_uses_the_last_music_occurrence(self) -> None:
        # Edge case: a "Music" folder name appearing earlier in the path too.
        assert short_path("/Volumes/Music Backup/Music/Track.mp3") == "Track.mp3"


class TestFormatDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0s"),
            (45, "45s"),
            (60, "1m00s"),
            (192, "3m12s"),
            (3600, "1h00m"),
            (3900, "1h05m"),
            (-5, "0s"),  # negative durations clamp to 0
        ],
    )
    def test_formats_readable_duration(self, seconds: float, expected: str) -> None:
        assert format_duration(seconds) == expected


class TestHumanSize:
    def test_none_is_unknown(self) -> None:
        assert human_size(None) == "?"

    def test_bytes(self) -> None:
        assert human_size(500) == "500 B"

    def test_kilobytes(self) -> None:
        assert human_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert human_size(3 * 1024 * 1024) == "3.0 MB"


class TestGetFileSize:
    def test_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "track.mp3"
        f.write_bytes(b"x" * 1234)
        assert get_file_size(str(f)) == 1234

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert get_file_size(str(tmp_path / "does-not-exist.mp3")) is None
