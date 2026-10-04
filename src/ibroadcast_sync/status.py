"""Small on-disk status summary (``data/ibroadcast_sync_status.json``),
written after every run so other tools - in particular a menu bar
companion app - can show "last sync" information cheaply, without
re-reading the (potentially large) failures log or re-fetching the
library.

Same atomic write pattern as :mod:`md5_cache`: write to a temp file, then
rename it over the final file, so a reader never observes a partially
written (corrupted) JSON document.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from .config import STATUS_FILE


class SyncStatus(TypedDict, total=False):
    timestamp: str  # ISO 8601, UTC
    success: bool
    error: str | None
    dry_run: bool
    uploaded: int | None
    upload_failed: int | None
    playlists_created_or_updated: int | None
    playlists_unmatched_tracks: int | None
    ratings_updated: int | None
    ratings_failed: int | None


def write_status(status: SyncStatus) -> None:
    """Atomic write of the latest run's summary. Never raises: a failure
    to write the status file shouldn't fail the whole sync run (the same
    reasoning as md5_cache.save_state's own try/except)."""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **status,
    }
    tmp_path = STATUS_FILE.with_name(STATUS_FILE.name + ".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, STATUS_FILE)
    except Exception:
        pass


def read_status() -> SyncStatus | None:
    """Returns the last written status, or None if there isn't one yet
    (first run) or it can't be read (corrupted, concurrent write)."""
    try:
        with open(STATUS_FILE) as f:
            data: Any = json.load(f)
    except Exception:
        return None
    # A TypedDict isn't a real runtime class isinstance() can narrow into -
    # the isinstance check below is a genuine runtime guard (a corrupted or
    # unexpectedly-shaped file could load as a list, a string, ...), the
    # cast() just tells mypy what we already know: this file is only ever
    # written by write_status() above, so a dict loaded from it matches
    # SyncStatus's shape.
    return cast("SyncStatus | None", data if isinstance(data, dict) else None)
