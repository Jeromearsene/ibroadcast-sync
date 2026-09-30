"""Tests for ibroadcast_sync.musicapp.

The three extraction functions themselves shell out to osascript/Music.app
and aren't covered here (macOS-only, no Music.app in CI - see the
README's "Development" section for the reasoning). `_run_osascript()`'s
timeout handling is pure logic on top of a mocked subprocess.run, though,
and worth covering: it's what turns a hung Music.app (most commonly
waiting on a permission dialog) into a clear error instead of an
indefinite hang.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ibroadcast_sync.musicapp import _run_osascript


def test_returns_the_completed_process_on_success() -> None:
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
    with patch("subprocess.run", return_value=fake_result) as mock_run:
        result = _run_osascript("function run() { return '[]'; }")

    assert result is fake_result
    # timeout must actually be passed through, not just documented
    assert mock_run.call_args.kwargs.get("timeout")


def test_timeout_raises_a_clear_runtime_error_not_the_raw_timeout_exception() -> None:
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=600)),
        pytest.raises(RuntimeError, match="did not respond"),
    ):
        _run_osascript("function run() { while(true){} }")


def test_timeout_error_mentions_the_permission_dialog() -> None:
    # The permission-dialog hint is the whole point of this error message
    # (it's the most common real-world cause) - worth pinning down
    # explicitly so a future refactor doesn't accidentally lose it.
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=600)),
        pytest.raises(RuntimeError, match="Automation"),
    ):
        _run_osascript("function run() {}")
