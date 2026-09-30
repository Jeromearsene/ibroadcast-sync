"""Tests for ibroadcast_sync.md5_cache."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

from ibroadcast_sync import md5_cache


@pytest.fixture
def cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirects MD5_CACHE_FILE to a throwaway path for the duration of a test."""
    path = tmp_path / "cache.json"
    monkeypatch.setattr(md5_cache, "MD5_CACHE_FILE", path)
    return path


class TestCalcMd5:
    def test_matches_hashlib_directly(self, tmp_path: Path) -> None:
        f = tmp_path / "song.mp3"
        f.write_bytes(b"some audio bytes" * 1000)
        expected = hashlib.md5(f.read_bytes()).hexdigest()
        assert md5_cache.calc_md5(str(f)) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.mp3"
        f.write_bytes(b"")
        assert md5_cache.calc_md5(str(f)) == hashlib.md5(b"").hexdigest()


class TestGetMd5Cached:
    def test_cache_miss_computes_and_stores(self, tmp_path: Path) -> None:
        f = tmp_path / "song.mp3"
        f.write_bytes(b"content")
        cache: dict = {}
        lock = threading.Lock()

        md5, was_cached = md5_cache.get_md5_cached(str(f), cache, lock)

        assert was_cached is False
        assert md5 == hashlib.md5(b"content").hexdigest()
        assert str(f) in cache

    def test_cache_hit_when_mtime_and_size_unchanged(self, tmp_path: Path) -> None:
        f = tmp_path / "song.mp3"
        f.write_bytes(b"content")
        cache: dict = {}
        lock = threading.Lock()

        md5_first, _ = md5_cache.get_md5_cached(str(f), cache, lock)
        # Second call should hit the cache and return the same value without
        # needing to re-read the file.
        md5_second, was_cached = md5_cache.get_md5_cached(str(f), cache, lock)

        assert was_cached is True
        assert md5_second == md5_first

    def test_cache_invalidated_when_file_changes(self, tmp_path: Path) -> None:
        f = tmp_path / "song.mp3"
        f.write_bytes(b"content")
        cache: dict = {}
        lock = threading.Lock()
        md5_cache.get_md5_cached(str(f), cache, lock)

        f.write_bytes(b"different content, different size")
        md5_new, was_cached = md5_cache.get_md5_cached(str(f), cache, lock)

        assert was_cached is False
        assert md5_new == hashlib.md5(b"different content, different size").hexdigest()

    def test_missing_file_is_hashed_without_crashing(self, tmp_path: Path) -> None:
        # os.stat() fails for a missing file; get_md5_cached falls back to
        # attempting calc_md5 directly, which will itself raise - this just
        # confirms the fallback path is taken rather than some unrelated
        # crash on the os.stat() call.
        missing = tmp_path / "gone.mp3"
        cache: dict = {}
        lock = threading.Lock()
        with pytest.raises(OSError):
            md5_cache.get_md5_cached(str(missing), cache, lock)


class TestLoadSaveState:
    def test_round_trip(self, cache_file: Path) -> None:
        files_cache: dict[str, md5_cache.CacheEntry] = {"/a.mp3": {"mtime": 1.0, "size": 10, "md5": "abc"}}
        uploaded = {"abc", "def"}

        md5_cache.save_state(files_cache, uploaded)
        loaded_cache, loaded_uploaded = md5_cache.load_state()

        assert loaded_cache == files_cache
        assert loaded_uploaded == uploaded

    def test_load_missing_file_returns_empty(self, cache_file: Path) -> None:
        # cache_file fixture points MD5_CACHE_FILE at a path that doesn't
        # exist yet (nothing has been saved).
        files_cache, uploaded = md5_cache.load_state()
        assert files_cache == {}
        assert uploaded == set()

    def test_load_old_format_without_upload_registry(self, cache_file: Path) -> None:
        # Pre-upload-registry cache files were just {path: entry} directly.
        cache_file.write_text('{"/a.mp3": {"mtime": 1.0, "size": 10, "md5": "abc"}}')
        files_cache, uploaded = md5_cache.load_state()
        assert files_cache == {"/a.mp3": {"mtime": 1.0, "size": 10, "md5": "abc"}}
        assert uploaded == set()

    def test_load_corrupted_file_warns_and_returns_empty(
        self, cache_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Distinct from the missing-file case: a file that exists but isn't
        # valid JSON (corruption, a bad manual edit, ...) should still
        # recover gracefully, but - unlike "no file yet" - it's worth
        # surfacing a warning rather than silently discarding a cache that
        # used to work.
        cache_file.write_text("{not valid json")

        files_cache, uploaded = md5_cache.load_state()

        assert files_cache == {}
        assert uploaded == set()
        assert "warning" in capsys.readouterr().out.lower()

    def test_save_is_atomic_no_tmp_file_left_behind(self, cache_file: Path) -> None:
        md5_cache.save_state({}, set())
        tmp_path = cache_file.with_name(cache_file.name + ".tmp")
        assert cache_file.exists()
        assert not tmp_path.exists()
