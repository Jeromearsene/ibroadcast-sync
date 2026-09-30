"""Small timestamped logging helper, built on `Rich <https://github.com/Textualize/rich>`_
rather than a hand-rolled ANSI color table: Rich already handles color
support detection (auto-disables styling when stdout isn't a real
terminal, e.g. a cron/launchd log file), a much wider set of named styles,
and Windows terminals - all things the previous custom implementation had
to (partially) reinvent.
"""

from __future__ import annotations

import threading
from datetime import datetime

from rich.console import Console
from rich.text import Text

console = Console()

# Shared with progress.py's ProgressDisplay, which writes raw ANSI escape
# sequences directly to stdout for its live-redrawn bar. Without a shared
# lock, a log() call (e.g. "Refreshing token...", which can happen from a
# worker thread mid-upload) and an in-flight progress redraw could
# interleave their writes and corrupt the terminal display.
stdout_lock = threading.Lock()


def log(msg: object, color: str | tuple[str, ...] | list[str] | None = None) -> None:
    """Prints a timestamped line to the console.

    `color` is a Rich style name (e.g. "green", "yellow", "dim") or a
    tuple/list of style names combined together (e.g. ("bold", "red")).
    Built with `Text.append(..., style=...)` rather than Rich's markup
    string syntax (e.g. "[red]...[/red]") so that message content
    containing literal square brackets (a filename, an error message, ...)
    is never misparsed as markup.
    """
    line = Text()
    line.append(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ", style="dim")
    style = " ".join(color) if isinstance(color, (tuple, list)) else color
    line.append(str(msg), style=style)
    with stdout_lock:
        console.print(line)
