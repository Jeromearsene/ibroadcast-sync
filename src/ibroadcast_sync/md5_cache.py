"""On-disk MD5 cache (``data/ibroadcast_md5_cache.json``), so the whole
library doesn't get re-hashed on every run.

Split out of ``upload.py``: hashing and caching file checksums is a
distinct concern from the actual HTTP upload, and testable on its own
without any network or iBroadcast client involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import TypedDict

from .config import MD5_CACHE_FILE
from .logging_utils import log


class CacheEntry(TypedDict):
    mtime: float
    size: int
    md5: str


def load_state() -> tuple[dict[str, CacheEntry], set[str]]:
    """Returns (files_cache, uploaded_md5s). Compatible with the old cache
    format (a plain dict path -> {mtime,size,md5}, with no upload registry)
    - in that case uploaded_md5s starts empty instead of crashing, and gets
    rebuilt as confirmed uploads come in on subsequent runs."""
    try:
        with open(MD5_CACHE_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, set()  # expected on a first run - nothing to warn about
    except Exception as e:
        # Unlike a missing file, this means something's actually wrong
        # (corrupted JSON, a permissions issue, ...) - falling back to an
        # empty cache is still the right recovery (a full re-hash beats
        # crashing the whole run), but silently discarding a previously
        # working cache deserves a warning instead of vanishing without a
        # trace, which would otherwise look like "why is this suddenly
        # re-hashing my entire library?" with no clue why.
        log(f"Warning: could not read the MD5 cache, starting fresh: {e}", color="yellow")
        return {}, set()

    if isinstance(data, dict) and "files" in data and "uploaded_md5s" in data:
        return data["files"], set(data["uploaded_md5s"])

    # Old format (before the local upload registry was added): the whole
    # file is directly the path -> entry dict.
    return data, set()


def save_state(files_cache: dict[str, CacheEntry], uploaded_md5s: set[str]) -> None:
    """Atomic write: write to a temp file, then rename it over the final
    file. os.replace() is atomic on POSIX systems (macOS included) - so no
    corrupted JSON even if the process is killed mid-save."""
    tmp_path = MD5_CACHE_FILE.with_name(MD5_CACHE_FILE.name + ".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump({"files": files_cache, "uploaded_md5s": sorted(uploaded_md5s)}, f)
        os.replace(tmp_path, MD5_CACHE_FILE)
    except Exception as e:
        log(f"Warning: could not save the cache: {e}")


def calc_md5(filepath: str) -> str:
    m = hashlib.md5()
    with open(filepath, "rb") as fh:
        while True:
            # 1 MiB chunks: audio files run tens of MB (FLACs easily
            # 20-80MB+), and the default 8KB textbook buffer size means
            # thousands of extra read() syscalls per file for no benefit -
            # a bigger buffer cuts Python-loop and syscall overhead
            # without meaningfully raising peak memory (a handful of MB
            # even with several worker threads hashing in parallel).
            data = fh.read(1_048_576)
            if not data:
                break
            m.update(data)
    return m.hexdigest()


def get_md5_cached(
    filepath: str,
    cache: dict[str, CacheEntry],
    cache_lock: threading.Lock,
) -> tuple[str, bool]:
    """Returns (md5, was_cached). The lock only protects reads/writes of
    the shared dict - the actual MD5 computation (the expensive part)
    happens outside the lock, so multiple threads can really hash in
    parallel."""
    try:
        stat = os.stat(filepath)
    except OSError:
        return calc_md5(filepath), False

    with cache_lock:
        entry = cache.get(filepath)
        if entry and entry.get("mtime") == stat.st_mtime and entry.get("size") == stat.st_size:
            return entry["md5"], True

    md5 = calc_md5(filepath)  # outside the lock: can be parallelized

    with cache_lock:
        cache[filepath] = {"mtime": stat.st_mtime, "size": stat.st_size, "md5": md5}
    return md5, False
