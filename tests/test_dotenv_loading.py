"""Tests for automatic .env loading (config.py's load_dotenv() call).

Run via a subprocess (a fresh Python process, fresh import) rather than
importlib.reload() in-process: config.py resolves and loads .env at
import time, and ibroadcast_sync.config has almost certainly already been
imported by something else by the time these tests run - reloading it
in-process would leave other already-imported modules holding stale
values, the same risk test_config.py's own docstring flags for
IBROADCAST_DATA_DIR.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


@pytest.fixture
def temporary_env_file() -> Generator[Path]:
    """Writes a real .env at the actual project root - config.py resolves
    that exact path itself, so there's no way to redirect it for a test.
    Skips rather than clobbers if a real .env is already there (it would
    hold the user's actual local credentials)."""
    if _ENV_FILE.exists():
        pytest.skip("a real .env already exists at the project root - refusing to overwrite it for a test")
    _ENV_FILE.write_text("IBROADCAST_CLIENT_ID=from-dotenv-test-file\n")
    try:
        yield _ENV_FILE
    finally:
        _ENV_FILE.unlink(missing_ok=True)


def _client_id_in_fresh_process(env_overrides: dict[str, str] | None = None) -> str:
    """Spawns a brand new interpreter (same venv, via sys.executable) and
    reads back what it resolves CLIENT_ID to - the only way to observe
    config.py's import-time behavior without touching this process's own
    already-imported copy of the module."""
    env = os.environ.copy()
    env.pop("IBROADCAST_CLIENT_ID", None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", "from ibroadcast_sync.config import CLIENT_ID; print(CLIENT_ID)"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def test_dotenv_file_is_loaded_automatically(temporary_env_file: Path) -> None:
    assert _client_id_in_fresh_process() == "from-dotenv-test-file"


def test_a_real_environment_variable_still_wins_over_the_dotenv_file(temporary_env_file: Path) -> None:
    # load_dotenv()'s default (override=False) must not clobber a var the
    # user actually exported themselves (or set in a launchd plist).
    result = _client_id_in_fresh_process({"IBROADCAST_CLIENT_ID": "from-real-shell-export"})
    assert result == "from-real-shell-export"


def test_missing_dotenv_file_is_not_an_error() -> None:
    assert not _ENV_FILE.exists()  # sanity: no leftover from another test/run
    result = _client_id_in_fresh_process()
    assert result == "REPLACE_WITH_YOUR_CLIENT_ID"
