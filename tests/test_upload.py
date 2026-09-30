"""Tests for ibroadcast_sync.upload (file-discovery logic, plus
process_file()'s error handling - the actual HTTP upload/retry path needs
a real/mocked iBroadcast client and is covered via test_playlists.py's
FakeClient pattern where relevant).
"""

from __future__ import annotations

import threading
from pathlib import Path

from ibroadcast_sync.progress import ProgressDisplay
from ibroadcast_sync.upload import find_local_files, process_file


class TestFindLocalFiles:
    def test_finds_files_with_supported_extension(self, tmp_path: Path) -> None:
        (tmp_path / "song.mp3").write_bytes(b"")
        (tmp_path / "notes.txt").write_bytes(b"")

        found = find_local_files(str(tmp_path), {".mp3", ".flac"})

        assert found == [str(tmp_path / "song.mp3")]

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "Artist" / "Album"
        sub.mkdir(parents=True)
        (sub / "track.flac").write_bytes(b"")

        found = find_local_files(str(tmp_path), {".flac"})

        assert found == [str(sub / "track.flac")]

    def test_skips_dotfiles(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden.mp3").write_bytes(b"")
        (tmp_path / "visible.mp3").write_bytes(b"")

        found = find_local_files(str(tmp_path), {".mp3"})

        assert found == [str(tmp_path / "visible.mp3")]

    def test_skips_dot_directories(self, tmp_path: Path) -> None:
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "track.mp3").write_bytes(b"")

        found = find_local_files(str(tmp_path), {".mp3"})

        assert found == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert find_local_files(str(tmp_path), {".mp3"}) == []

    def test_unsupported_extension_is_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "cover.jpg").write_bytes(b"")
        assert find_local_files(str(tmp_path), {".mp3"}) == []


class TestProcessFileMissingFile:
    def test_missing_file_is_reported_as_a_failure_not_raised(self, tmp_path: Path) -> None:
        # Regression test: a file that vanishes between being listed and
        # being processed (deleted, drive ejected, ...) used to raise an
        # uncaught OSError out of the worker thread, which would only
        # surface later via future.result() and crash the entire run
        # instead of being logged as one failed file among many.
        missing = tmp_path / "gone.mp3"
        progress = ProgressDisplay(total=1, workers=1)

        result = process_file(
            client=None,  # type: ignore[arg-type]  # never reached: fails before any client use
            filepath=str(missing),
            md5_cache={},
            uploaded_md5s=set(),
            cache_lock=threading.Lock(),
            remote_md5s=set(),
            dry_run=False,
            progress=progress,
            failures_lock=threading.Lock(),
        )

        _filepath, status, was_cached, error = result
        assert status == "failure"
        assert was_cached is False
        assert error is not None
