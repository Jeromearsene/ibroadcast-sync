"""Tests for ibroadcast_sync.logging_utils."""

from __future__ import annotations

import threading
import time

import pytest

from ibroadcast_sync import progress as progress_module
from ibroadcast_sync.logging_utils import log, stdout_lock


@pytest.mark.parametrize(
    "message",
    [
        "plain message",
        "message with [brackets] in it",
        "path with [Album Name]/track.mp3",
        "error: [Errno 2] No such file or directory",
    ],
)
def test_log_does_not_crash_on_bracket_content(message: str, capsys: pytest.CaptureFixture) -> None:
    """Regression test: log() builds output with rich.text.Text.append(),
    not Rich's "[style]...[/style]" markup syntax, specifically so that
    literal square brackets in a message (filenames, error messages) are
    never misinterpreted as markup tags."""
    log(message)  # must not raise
    log(message, color="red")
    log(message, color=("bold", "red"))
    captured = capsys.readouterr()
    assert message in captured.out


def test_progress_module_shares_the_same_lock_instance() -> None:
    # Regression test: progress.py's ProgressDisplay writes raw ANSI
    # escapes directly to stdout for its live redraw. If it used its own,
    # separate lock instead of importing this exact one, a log() call
    # could still interleave with an in-progress redraw and corrupt the
    # terminal output - the whole point only holds if it's the SAME lock
    # object, not just a same-purpose one.
    assert progress_module.stdout_lock is stdout_lock


def test_log_blocks_while_stdout_lock_is_held_elsewhere(capsys: pytest.CaptureFixture) -> None:
    # Demonstrates the lock is actually load-bearing: while some other
    # code (standing in for ProgressDisplay._draw()) holds stdout_lock,
    # a concurrent log() call must wait rather than writing immediately.
    log_started = threading.Event()
    log_finished = threading.Event()

    def call_log() -> None:
        log_started.set()
        log("should wait for the lock")
        log_finished.set()

    with stdout_lock:
        thread = threading.Thread(target=call_log)
        thread.start()
        log_started.wait(timeout=2)
        time.sleep(0.1)  # give it a chance to (wrongly) proceed if unlocked
        assert not log_finished.is_set(), "log() wrote while stdout_lock was held elsewhere"

    thread.join(timeout=2)
    assert log_finished.is_set()
    assert "should wait for the lock" in capsys.readouterr().out
