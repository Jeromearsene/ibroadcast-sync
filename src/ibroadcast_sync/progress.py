"""Live terminal progress display, used by both the upload step and the
rating sync step.

Split out of ``upload.py`` on purpose: rendering a live progress bar is a
terminal/UI concern, unrelated to what's actually being uploaded or rated.
Keeping it separate also removes the odd situation where ``ratings.py`` had
to import a display class from ``upload.py``.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from collections import deque
from typing import Literal

from .logging_utils import log, stdout_lock

# Status labels shared by upload.py (skip/dry/upload/failure) and
# ratings.py (which also uses "notfound" for unmatched local tracks).
Status = Literal["skip", "dry", "upload", "failure", "notfound"]

_STATUS_MARKERS: dict[str, str] = {
    "skip": "⏭️",
    "upload": "✅",
    "dry": "🔍",
    "failure": "❌",
    "notfound": "❓",
}


def short_path(filepath: str) -> str:
    """Shortens a path for display: only keeps what follows the last
    'Music/' segment (typical of an iTunes/Music.app library), to avoid
    reprinting the full disk path for every file. If 'Music/' doesn't
    appear in the path, returns the full path."""
    idx = filepath.rfind("Music/")
    if idx == -1:
        return filepath
    return filepath[idx + len("Music/") :]


def format_duration(seconds: float) -> str:
    """Formats a duration in seconds as a short, readable string (e.g.
    '45s', '3m12s', '1h05m')."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def human_size(num_bytes: int | None) -> str:
    """Formats a size in bytes as a short, readable string (e.g. '3.2 MB')."""
    if num_bytes is None:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "?"  # unreachable, satisfies type checkers expecting a str on every path


def get_file_size(filepath: str) -> int | None:
    try:
        return os.path.getsize(filepath)
    except OSError:
        return None


class ProgressDisplay:
    """A fixed progress bar (X/total - pct%) followed by an "in progress"
    section (uploads currently in flight) then the last 10 processed
    files, all redrawn in place without scrolling the terminal.
    Automatically falls back to plain periodic logs if stdout isn't a real
    terminal (e.g. redirected to a log file by cron/launchd), to avoid
    polluting the log with ANSI escape sequences.
    """

    HISTORY_SIZE = 10
    RATE_WINDOW = 100  # nb of recent completions used to estimate throughput
    MIN_DRAW_INTERVAL = 0.1  # seconds between two real redraws (~10/s max)
    MAX_IN_PROGRESS_ROWS = 8  # display cap, independent of --workers

    def __init__(self, total: int, workers: int = 4) -> None:
        self.total = total
        self.current = 0
        self.history: deque[str] = deque(maxlen=self.HISTORY_SIZE)
        self.interactive = sys.stdout.isatty()
        self._drawn_once = False
        self.start_time = time.monotonic()
        self._recent_times: deque[float] = deque(maxlen=self.RATE_WINDOW)
        self._last_draw_time = 0.0
        self._draw_lock = threading.Lock()

        self.in_progress_rows = min(max(workers, 1), self.MAX_IN_PROGRESS_ROWS)
        self._in_progress: dict[str, tuple[float, int | None]] = {}  # path -> (start time, size)
        self._in_progress_lock = threading.Lock()
        self._stop_ticker = threading.Event()
        self._ticker_thread: threading.Thread | None = None

    # --- Tracking of in-flight uploads (callable from worker threads) ---

    def mark_upload_started(self, filepath: str) -> None:
        size = get_file_size(filepath)
        with self._in_progress_lock:
            self._in_progress[filepath] = (time.monotonic(), size)

    def mark_upload_finished(self, filepath: str) -> None:
        with self._in_progress_lock:
            self._in_progress.pop(filepath, None)

    # --- Periodic refresh independent of completions, so the "in
    # progress" section actually moves live even if no file finishes for
    # several seconds (large files) ---

    def start_ticker(self) -> None:
        if not self.interactive:
            return

        def tick() -> None:
            while not self._stop_ticker.wait(self.MIN_DRAW_INTERVAL):
                self._maybe_draw()

        self._ticker_thread = threading.Thread(target=tick, daemon=True)
        self._ticker_thread.start()

    def stop_ticker(self) -> None:
        self._stop_ticker.set()
        if self._ticker_thread:
            self._ticker_thread.join(timeout=1)

    def record_completion(self) -> None:
        """Call once per processed file, independently of redraw
        throttling - this is what feeds the throughput calculation for the
        ETA. If it were only called at draw time (capped at ~10/s), the
        measured throughput would be artificially capped instead of
        reflecting the real processing speed."""
        self._recent_times.append(time.monotonic())

    def _eta_str(self) -> str | None:
        if self.current <= 0 or self.current >= self.total:
            return None

        rate: float | None
        if len(self._recent_times) >= 2:
            # Recent throughput (more reactive if speed changes mid-run:
            # cache hits at first vs real uploads afterwards, for example).
            span = self._recent_times[-1] - self._recent_times[0]
            n = len(self._recent_times) - 1
            rate = n / span if span > 0 else None
        else:
            rate = None

        if not rate:
            elapsed = time.monotonic() - self.start_time
            rate = self.current / elapsed if elapsed > 0 else None

        if not rate:
            return None

        remaining_seconds = (self.total - self.current) / rate
        return format_duration(remaining_seconds)

    def update(self, filepath: str, status: Status | str) -> None:
        self.current += 1
        self.record_completion()
        marker = _STATUS_MARKERS.get(status, "•")
        self.history.append(f"  {marker} {short_path(filepath)} - {human_size(get_file_size(filepath))}")

        if self.interactive:
            self._maybe_draw(force=(self.current == self.total))
        elif self.current % 500 == 0 or self.current == self.total:
            pct = (self.current / self.total * 100) if self.total else 100
            eta = self._eta_str()
            eta_part = f" - ETA {eta}" if eta else ""
            log(f"  Progress: {self.current}/{self.total} - {pct:.0f}%{eta_part}")

    def _maybe_draw(self, force: bool = False) -> None:
        """Single entry point for draw throttling (~10/s max), used both by
        update() (main thread, on completion) and by the ticker (dedicated
        thread, on a fixed interval) - the lock prevents the two from
        stepping on each other and drawing twice for nothing."""
        with self._draw_lock:
            now = time.monotonic()
            if force or (now - self._last_draw_time) >= self.MIN_DRAW_INTERVAL:
                self._last_draw_time = now
                self._draw()

    def _draw(self) -> None:
        width = shutil.get_terminal_size((100, 20)).columns
        pct = (self.current / self.total * 100) if self.total else 100

        bar_width = min(50, max(10, width - 10))
        filled = int((pct / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        eta = self._eta_str()
        eta_part = f" - ETA {eta}" if eta else ""

        with self._in_progress_lock:
            in_progress_snapshot = sorted(self._in_progress.items(), key=lambda kv: kv[1][0])
        now = time.monotonic()
        in_progress_lines = [
            f"  📤 {short_path(fp)} - {human_size(size)} ({now - started:.1f}s)"
            for fp, (started, size) in in_progress_snapshot[: self.in_progress_rows]
        ]

        lines = [f"{self.current}/{self.total} - {pct:.0f}%{eta_part}", bar, ""]
        lines.append(f"In progress ({len(in_progress_snapshot)}/{self.in_progress_rows}):")
        lines.extend(in_progress_lines)
        while len(lines) < 4 + self.in_progress_rows:
            lines.append("")
        lines.append("")
        lines.append("Last processed:")
        lines.extend(self.history)
        while len(lines) < 6 + self.in_progress_rows + self.HISTORY_SIZE:
            lines.append("")

        with stdout_lock:
            if self._drawn_once:
                sys.stdout.write(f"\033[{len(lines)}A")
            for line in lines:
                sys.stdout.write("\033[K" + line[:width] + "\n")
            sys.stdout.flush()
        self._drawn_once = True

    def finish(self) -> None:
        self.stop_ticker()
        if self.interactive and self._drawn_once:
            with stdout_lock:
                sys.stdout.write("\n")
                sys.stdout.flush()
