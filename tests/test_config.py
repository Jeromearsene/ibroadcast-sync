"""Tests for ibroadcast_sync.config.

Only checks structural invariants of the already-imported module (paths,
existence) - not the IBROADCAST_DATA_DIR env var override itself, since
config.py resolves it once at import time and reloading the module mid
test-suite would risk leaving other already-imported modules (which hold
their own references to these constants) pointing at a stale location.
"""

from __future__ import annotations

from ibroadcast_sync import config


def test_data_dir_exists() -> None:
    assert config.DATA_DIR.is_dir()


def test_data_files_live_under_data_dir() -> None:
    for path in (
        config.TOKEN_FILE,
        config.LIBRARY_DUMP_FILE,
        config.MD5_CACHE_FILE,
        config.FAILURES_LOG_FILE,
    ):
        assert path.parent == config.DATA_DIR


def test_redirect_uri_has_a_port() -> None:
    # wait_for_oauth_callback() in oauth_client.py relies on this.
    assert ":" in config.REDIRECT_URI.split("//", 1)[1]
