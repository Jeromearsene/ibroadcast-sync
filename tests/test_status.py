"""Tests for ibroadcast_sync.status."""

from __future__ import annotations

from pathlib import Path

import pytest

from ibroadcast_sync import status


@pytest.fixture
def status_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirects STATUS_FILE to a throwaway path for the duration of a test."""
    path = tmp_path / "status.json"
    monkeypatch.setattr(status, "STATUS_FILE", path)
    return path


class TestWriteReadStatus:
    def test_round_trip(self, status_file: Path) -> None:
        status.write_status({"success": True, "dry_run": False, "uploaded": 3, "upload_failed": 0})

        loaded = status.read_status()

        assert loaded is not None
        assert loaded["success"] is True
        assert loaded["uploaded"] == 3
        assert loaded["upload_failed"] == 0
        # write_status() stamps its own timestamp - not something the
        # caller passes in.
        assert "timestamp" in loaded

    def test_read_missing_file_returns_none(self, status_file: Path) -> None:
        # status_file fixture points STATUS_FILE at a path that doesn't
        # exist yet (nothing has been written).
        assert status.read_status() is None

    def test_read_corrupted_file_returns_none(self, status_file: Path) -> None:
        status_file.write_text("{not valid json")
        assert status.read_status() is None

    def test_write_is_atomic_no_tmp_file_left_behind(self, status_file: Path) -> None:
        status.write_status({"success": True, "dry_run": False})
        tmp_path = status_file.with_name(status_file.name + ".tmp")
        assert status_file.exists()
        assert not tmp_path.exists()

    def test_write_never_raises_even_if_the_parent_directory_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Mirrors md5_cache.save_state()'s own try/except: a failure to
        # write the status file is a shame, not a reason to fail (or
        # crash) the whole sync run.
        monkeypatch.setattr(status, "STATUS_FILE", tmp_path / "missing-dir" / "status.json")
        status.write_status({"success": True, "dry_run": False})  # must not raise

    def test_write_overwrites_the_previous_status(self, status_file: Path) -> None:
        status.write_status({"success": False, "dry_run": False, "error": "boom"})
        status.write_status({"success": True, "dry_run": False})

        loaded = status.read_status()

        assert loaded is not None
        assert loaded["success"] is True
        assert "error" not in loaded
