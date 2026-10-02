"""Upload local audio files to iBroadcast.

Discovers which files to send (a given folder, or the Music.app library),
and uploads them in parallel with retries/backoff. MD5 caching lives in
:mod:`ibroadcast_sync.md5_cache`, the live progress bar in
:mod:`ibroadcast_sync.progress`.
"""

from __future__ import annotations

import glob
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TYPE_CHECKING

import requests

from .config import CLIENT_NAME, FAILURES_LOG_FILE, UPLOAD_URL
from .logging_utils import log
from .md5_cache import CacheEntry, get_md5_cached, load_state, save_state
from .musicapp import get_music_app_track_paths
from .oauth_client import ServerError
from .progress import ProgressDisplay, short_path

if TYPE_CHECKING:
    from .oauth_client import IBroadcastClient

# Result tuple returned by process_file(): (path, status, was_cached, error).
ProcessResult = tuple[str, str, bool, "str | None"]


def load_supported_extensions(client: IBroadcastClient) -> set[str]:
    data = client.api_call("status", {"supported_types": 1})
    # Lowercased so the comparisons in find_local_files()/do_upload() below
    # don't depend on whatever casing the API happens to use.
    return {ft["extension"].lower() for ft in data["supported"]}


def find_local_files(directory: str, supported_extensions: set[str]) -> list[str]:
    files: list[str] = []
    for full_filename in glob.glob(os.path.join(directory, "*")):
        filename = os.path.basename(full_filename)
        # glob's `*` already excludes dotfiles by default (same as shell
        # globbing), so this never actually triggers today - kept as an
        # explicit, robust guarantee in case the iteration method here
        # ever changes to something that doesn't have that built in.
        if filename.startswith("."):
            continue
        if os.path.isdir(full_filename):
            files.extend(find_local_files(full_filename, supported_extensions))
            continue
        _, ext = os.path.splitext(full_filename)
        # Case-insensitive: a file named "Track.MP3" or "Track.FLAC"
        # (common on older rips, or on files copied from a
        # case-insensitive filesystem) must still match a lowercase entry
        # in supported_extensions. This used to be a silent skip - no log
        # line, no failure count, the file just never made it into this
        # list.
        if ext.lower() in supported_extensions:
            files.append(full_filename)
    return files


def load_remote_md5s(client: IBroadcastClient) -> set[str]:
    response = requests.post(UPLOAD_URL, headers=client.auth_header())
    if not response.ok:
        raise ServerError(f"Invalid server status (md5): {response.status_code}")
    return set(response.json()["md5"])


def upload_file(client: IBroadcastClient, filepath: str) -> None:
    def _do_post() -> requests.Response:
        with open(filepath, "rb") as upload_fh:
            return requests.post(
                UPLOAD_URL,
                {"file_path": filepath, "method": CLIENT_NAME},
                files={"file": upload_fh},
                headers=client.auth_header(),
            )

    response = _do_post()
    if response.status_code in (401, 403):
        # 401 = invalid token, the normal case to refresh for. We also
        # treat 403 the same way, just in case: iBroadcast's docs don't say
        # whether they sometimes use it for a token issue rather than a
        # true 401 - attempting a refresh costs nothing if that's not the
        # real cause (the refresh is just a no-op if the token is already
        # valid).
        client.refresh_if_necessary()
        client.save_token()
        response = _do_post()
    if not response.ok:
        raise ServerError(f"Invalid server status (upload): {response.status_code}")
    if response.json().get("result") is False:
        raise ServerError(f"Upload failed for {filepath}")


def init_failures_log() -> None:
    """Resets the failures file at the start of each run (so failures from
    different runs don't get mixed together). Can be checked at any time
    while the script is running, without waiting for the end - unlike the
    final summary, which only appears once everything is done (or is lost
    entirely on a Ctrl+C)."""
    try:
        with open(FAILURES_LOG_FILE, "w") as f:
            f.write(f"# Failures for the run started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        log(f"Warning: could not initialize the failures log: {e}")


def append_failure_log(filepath: str, reason: str | None, failures_lock: threading.Lock) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {filepath} : {reason}\n"
    with failures_lock:
        try:
            with open(FAILURES_LOG_FILE, "a") as f:
                f.write(line)
        except Exception as e:
            log(f"Warning: could not write to the failures log: {e}")


def process_file(
    client: IBroadcastClient,
    filepath: str,
    md5_cache: dict[str, CacheEntry],
    uploaded_md5s: set[str],
    cache_lock: threading.Lock,
    remote_md5s: set[str],
    dry_run: bool,
    progress: ProgressDisplay,
    failures_lock: threading.Lock,
    max_retries: int = 3,
) -> ProcessResult:
    """Runs in a worker thread. Only touches shared state via the MD5 cache
    + local upload registry (both protected by cache_lock), the failures
    log file (protected by failures_lock), and the progress bar's
    "in-progress" tracking (protected by its own internal lock) - counters
    and history remain managed solely by the main thread as it collects
    results.

    Automatically retries on failure, with a backoff that grows
    substantially (10s, 30s, 90s) - real observed failures (403s /
    connections dropped in bursts, correlated with heavy concurrent load)
    show that a backoff of a few seconds isn't enough to let server-side
    load subside."""
    try:
        file_md5, was_cached = get_md5_cached(filepath, md5_cache, cache_lock)
    except OSError as e:
        # The file can vanish (deleted, external drive ejected, network
        # share hiccup, permissions changed) in the gap between being
        # listed and actually being processed here - possibly a long gap,
        # for a large library. Without this, the exception would propagate
        # out of the worker thread, surface when the main loop calls
        # future.result(), and crash the entire run over a single file.
        append_failure_log(filepath, f"could not read file: {e}", failures_lock)
        return filepath, "failure", False, str(e)

    with cache_lock:
        already_known = file_md5 in remote_md5s or file_md5 in uploaded_md5s

    if already_known:
        return filepath, "skip", was_cached, None

    if dry_run:
        return filepath, "dry", was_cached, None

    backoff_seconds = [10, 30, 90]

    progress.mark_upload_started(filepath)
    try:
        last_error: str | None = None
        for attempt in range(max_retries + 1):
            try:
                upload_file(client, filepath)
                with cache_lock:
                    uploaded_md5s.add(file_md5)
                return filepath, "upload", was_cached, None
            except Exception as e:
                last_error = str(e)
                # Once auth is known to be permanently dead, further
                # attempts on THIS file are just as doomed as the ones
                # do_upload() cancels for files that haven't started yet -
                # stop sleeping through a pointless backoff schedule
                # (up to 130s across 3 retries) instead of failing fast.
                if attempt < max_retries and not client.auth_dead.is_set():
                    time.sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])
                    continue
                break
        append_failure_log(filepath, last_error, failures_lock)
        return filepath, "failure", was_cached, last_error
    finally:
        progress.mark_upload_finished(filepath)


def do_upload(client: IBroadcastClient, source_dir: str | None, dry_run: bool, workers: int = 4) -> None:
    supported = load_supported_extensions(client)

    if source_dir:
        log(f"Looking for audio files in {source_dir}...")
        local_files = find_local_files(source_dir, supported)
    else:
        local_files = get_music_app_track_paths(verbose=True)
        # Filter by supported extension, same as for a folder scan
        # (case-insensitively - see find_local_files()).
        local_files = [f for f in local_files if os.path.splitext(f)[1].lower() in supported]

    # A messy Music.app library can list the same underlying file under
    # more than one track entry - dedup (order-preserving) so it's never
    # hashed or uploaded twice in the same run.
    local_files = list(dict.fromkeys(local_files))

    total = len(local_files)
    log(f"{total} audio files to consider for upload ({workers} in parallel).")
    if dry_run:
        log("Dry run: no files will actually be uploaded.", color="magenta")

    remote_md5s = load_remote_md5s(client)
    md5_cache, uploaded_md5s = load_state()
    cache_lock = threading.Lock()
    failures_lock = threading.Lock()
    init_failures_log()
    if not dry_run:
        log(f"Failures can be watched live in: {FAILURES_LOG_FILE}", color="dim")

    save_every = 20  # nb of files actually hashed OR successfully uploaded, between two saves

    uploaded, skipped, failed = 0, 0, 0
    dirty_since_save = 0
    failures: list[
        tuple[str, str | None]
    ] = []  # summarized at the end, the rolling history may have scrolled off
    progress = ProgressDisplay(total, workers=workers)
    progress.start_ticker()

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_path = {
                executor.submit(
                    process_file,
                    client,
                    fp,
                    md5_cache,
                    uploaded_md5s,
                    cache_lock,
                    remote_md5s,
                    dry_run,
                    progress,
                    failures_lock,
                ): fp
                for fp in local_files
            }
            aborted_for_auth = False
            for future in as_completed(future_to_path):
                filepath, status, was_cached, error = future.result()

                # We save both after a new hash AND after a genuinely
                # confirmed upload - it's precisely that last case
                # (successful upload not yet persisted) that used to be
                # lost if the script was interrupted before the next
                # periodic save.
                if not was_cached or status == "upload":
                    dirty_since_save += 1
                    if dirty_since_save >= save_every:
                        with cache_lock:
                            save_state(md5_cache, uploaded_md5s)
                        dirty_since_save = 0

                if status == "skip":
                    skipped += 1
                elif status in ("dry", "upload"):
                    uploaded += 1
                elif status == "failure":
                    failed += 1
                    failures.append((filepath, error))

                progress.update(filepath, status)

                # If the token is permanently dead (invalid refresh_token),
                # there's no point letting the remaining tens of thousands
                # of files fail one by one over hours: cancel everything
                # that hasn't started yet and exit. Tasks already running
                # in a thread run to their natural completion (usually
                # fast, since they'll also fail immediately on the missing
                # token), but don't block the exit for long.
                if client.auth_dead.is_set() and not aborted_for_auth:
                    aborted_for_auth = True
                    cancelled = sum(1 for f in future_to_path if f.cancel())
                    log(
                        f"Unrecoverable authentication failure mid-run (invalid refresh token). "
                        f"Stopping - {cancelled} remaining files cancelled before they started. "
                        f"Re-run the script to re-authenticate (a browser tab will open).",
                        color=("bold", "red"),
                    )
                    # Exit immediately: continuing to iterate as_completed()
                    # would surface the futures we just cancelled, whose
                    # .result() raises CancelledError instead of returning
                    # a normal result.
                    break
    finally:
        progress.finish()
        # Final save (covers the remainder of fewer than save_every files
        # since the last periodic save), including if the run is
        # interrupted (Ctrl+C) or crashes mid-way.
        with cache_lock:
            save_state(md5_cache, uploaded_md5s)

    summary_verb = "Would upload" if dry_run else "Upload done. New"
    log(
        f"{summary_verb}: {uploaded}, already present: {skipped}, failures: {failed}.",
        color="green" if not failed else "yellow",
    )
    if failures:
        log("Failure details:", color="red")
        for filepath, reason in failures:
            log(f"  ❌ {short_path(filepath)}: {reason}", color="red")
