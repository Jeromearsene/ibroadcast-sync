"""Tests for ibroadcast_sync.upload (file-discovery logic, plus
process_file()'s error handling - the actual HTTP upload/retry path needs
a real/mocked iBroadcast client and is covered via test_playlists.py's
FakeClient pattern where relevant).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ibroadcast_sync.oauth_client import IBroadcastClient, ServerError
from ibroadcast_sync.progress import ProgressDisplay
from ibroadcast_sync.upload import find_local_files, load_remote_md5s, process_file, upload_file


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

    def test_matches_extension_case_insensitively(self, tmp_path: Path) -> None:
        # Regression test: an extension like ".MP3" or ".FLAC" (common on
        # older rips, or files copied from a case-insensitive filesystem)
        # used to be compared as-is against the lowercase entries in
        # supported_extensions and silently dropped - no log line, no
        # failure count, it just never made it into the result.
        (tmp_path / "Track.MP3").write_bytes(b"")
        (tmp_path / "other.FLAC").write_bytes(b"")

        found = find_local_files(str(tmp_path), {".mp3", ".flac"})

        assert set(found) == {str(tmp_path / "Track.MP3"), str(tmp_path / "other.FLAC")}


class TestDeadTokenHandling:
    def test_load_remote_md5s_refreshes_once_after_401(self) -> None:
        client = IBroadcastClient()
        client.token = {
            "expires_at": time.time() - 1,
            "access_token": "old",
            "token_type": "Bearer",
        }
        first_response = MagicMock(status_code=401, ok=False)
        second_response = MagicMock(status_code=200, ok=True)
        second_response.json.return_value = {"md5": ["abc123"]}

        def fake_refresh() -> None:
            client.token = {
                "expires_at": time.time() + 3600,
                "access_token": "new",
                "token_type": "Bearer",
            }

        with (
            patch(
                "ibroadcast_sync.upload.requests.post",
                side_effect=[first_response, second_response],
            ) as mock_post,
            patch.object(client, "refresh_if_necessary", side_effect=fake_refresh),
            patch.object(client, "save_token"),
        ):
            assert load_remote_md5s(client) == {"abc123"}

        assert mock_post.call_count == 2

    def test_load_remote_md5s_does_not_save_a_dead_token(self) -> None:
        client = IBroadcastClient()
        client.token = {
            "expires_at": time.time() - 1,
            "access_token": "old",
            "token_type": "Bearer",
        }
        response = MagicMock(status_code=401, ok=False)

        with (
            patch("ibroadcast_sync.upload.requests.post", return_value=response),
            patch.object(client, "refresh_if_necessary", side_effect=lambda: setattr(client, "token", None)),
            patch.object(client, "save_token") as mock_save,
            pytest.raises(ServerError, match="no longer valid"),
        ):
            load_remote_md5s(client)

        mock_save.assert_not_called()

    def test_upload_does_not_save_or_retry_with_a_dead_token(self, tmp_path: Path) -> None:
        client = IBroadcastClient()
        client.token = {
            "expires_at": time.time() - 1,
            "access_token": "old",
            "token_type": "Bearer",
        }
        audio_file = tmp_path / "track.mp3"
        audio_file.write_bytes(b"audio")
        response = MagicMock(status_code=401, ok=False)

        with (
            patch("ibroadcast_sync.upload.requests.post", return_value=response) as mock_post,
            patch.object(client, "refresh_if_necessary", side_effect=lambda: setattr(client, "token", None)),
            patch.object(client, "save_token") as mock_save,
            pytest.raises(ServerError, match="no longer valid"),
        ):
            upload_file(client, str(audio_file))

        assert mock_post.call_count == 1
        mock_save.assert_not_called()


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
