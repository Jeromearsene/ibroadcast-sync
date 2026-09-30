"""Sync Music.app star ratings to iBroadcast."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from .logging_utils import log
from .matching import index_remote_ratings, index_remote_tracks, resolve_track_id
from .musicapp import get_music_app_ratings
from .progress import ProgressDisplay

if TYPE_CHECKING:
    from .oauth_client import IBroadcastClient


def itunes_rating_to_ibroadcast(rating_0_100: int) -> int:
    """Converts a Music.app rating (0-100, 20 points per star, allowing
    half-stars) to iBroadcast's scale (integer 0-5, same as for
    albums/artists - confirmed by the UI, which does show 5 stars for
    tracks despite ambiguous API docs that only mention values 0/1/5). The
    only loss: rounding the Music.app half-star to the nearest whole
    point, since the API only accepts an Int."""
    stars = rating_0_100 / 20.0
    rounded = math.floor(
        stars + 0.5
    )  # round-half-up (the built-in round() rounds .5 to the nearest even number)
    return max(0, min(5, rounded))


def sync_ratings(client: IBroadcastClient, dry_run: bool, verbose: bool = False) -> None:
    log("Reading Music.app ratings...")
    local_tracks = get_music_app_ratings(verbose=verbose)

    log("Fetching the iBroadcast library...")
    library = client.fetch_library()
    primary_index, by_title_album_index, by_title_artist_index, _ = index_remote_tracks(library)
    remote_ratings = index_remote_ratings(library)

    # Adaptive throttling: the server rejects requests with an explicit
    # message ("Too many requests too quickly") if ratetrack calls come in
    # too fast - no fixed delay is documented, so we start conservative and
    # increase the delay every time we get rate-limited.
    delay = 0.3
    max_delay = 8.0
    max_retries = 6

    updated, unmatched, unchanged, already_ok, failed = 0, 0, 0, 0, 0
    total_to_rate = sum(1 for t in local_tracks if t.get("rating"))
    failures: list[
        tuple[str, str]
    ] = []  # (label, reason) - failure details aren't logged live, to avoid breaking the progress bar

    progress = ProgressDisplay(total_to_rate, workers=1)
    progress.start_ticker()

    try:
        for t in local_tracks:
            if not t.get("rating"):
                # Never rated in Music.app: don't touch a rating that may
                # already be set directly on the iBroadcast side. Doesn't
                # count towards total_to_rate, so no progress bar update.
                unchanged += 1
                continue

            track_id, _ = resolve_track_id(
                t.get("title", ""),
                t.get("artist", ""),
                t.get("album", ""),
                primary_index,
                by_title_album_index,
                by_title_artist_index,
            )

            label = f"{t.get('title', '?')} - {t.get('artist', '?')}"

            if track_id is None:
                unmatched += 1
                progress.update(label, "notfound")
                continue

            ib_rating = itunes_rating_to_ibroadcast(t["rating"])

            if remote_ratings.get(track_id) == ib_rating:
                # Already the correct rating on the iBroadcast side (e.g. a
                # previous run was interrupted mid-way) - no need to call
                # the API again.
                already_ok += 1
                progress.update(label, "skip")
                continue

            if dry_run:
                log(
                    f"[dry-run] Would rate '{label}': {t['rating']}/100 -> {ib_rating} star(s)",
                    color="magenta",
                )
                updated += 1
                progress.update(label, "dry")
                continue

            progress.mark_upload_started(label)
            attempt = 0
            while True:
                time.sleep(delay)
                try:
                    client.api_call("ratetrack", {"track_id": track_id, "rating": ib_rating})
                    updated += 1
                    progress.update(label, "upload")
                    break
                except Exception as e:
                    msg = str(e)
                    if "too many requests" in msg.lower() and attempt < max_retries:
                        attempt += 1
                        delay = min(delay * 2, max_delay)
                        continue
                    failed += 1
                    failures.append((label, str(e)))
                    progress.update(label, "failure")
                    break
            progress.mark_upload_finished(label)
    finally:
        progress.finish()

    log(
        f"Ratings synced: {updated}, already correct: {already_ok}, failures: {failed}, "
        f"not found on iBroadcast: {unmatched}, no local rating: {unchanged}",
        color="green" if not failed else "yellow",
    )
    if failures:
        log("Rating failure details:", color="red")
        for label, reason in failures:
            log(f"  ❌ {label}: {reason}", color="red")
