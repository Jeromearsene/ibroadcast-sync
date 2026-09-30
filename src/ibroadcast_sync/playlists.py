"""Sync Music.app playlists to iBroadcast."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .logging_utils import log
from .matching import index_remote_playlists, index_remote_tracks, normalize, resolve_track_id
from .musicapp import get_music_app_playlists

if TYPE_CHECKING:
    from .oauth_client import IBroadcastClient


def sync_playlists(client: IBroadcastClient, dry_run: bool, verbose: bool = False) -> None:
    log("Reading Music.app playlists...")
    local_playlists = get_music_app_playlists(verbose=verbose)
    log(f"{len(local_playlists)} playlists found locally.")

    log("Fetching the iBroadcast library...")
    library = client.fetch_library()

    primary_index, by_title_album_index, by_title_artist_index, by_title_index = index_remote_tracks(library)
    playlist_index = index_remote_playlists(library)

    total_fallback_album_used = 0
    total_fallback_artist_used = 0

    for pl in local_playlists:
        name = pl["name"]
        track_ids: list[int] = []
        unmatched: list[tuple[str, str, str]] = []  # (title, artist, album) not found, for diagnostics
        fallback_album_used = 0
        fallback_artist_used = 0

        for t in pl["tracks"]:
            track_id, fallback = resolve_track_id(
                t.get("title", ""),
                t.get("artist", ""),
                t.get("album", ""),
                primary_index,
                by_title_album_index,
                by_title_artist_index,
            )

            if track_id is None:
                unmatched.append((t.get("title", "?"), t.get("artist", "?"), t.get("album", "?")))
            else:
                track_ids.append(track_id)
                if fallback == "title_album":
                    fallback_album_used += 1
                elif fallback == "title_artist":
                    fallback_artist_used += 1

        total_fallback_album_used += fallback_album_used
        total_fallback_artist_used += fallback_artist_used

        if unmatched:
            titles_preview = ", ".join(u[0] for u in unmatched[:5])
            log(
                f"Playlist '{name}': {len(unmatched)} track(s) not found "
                f"on iBroadcast (not uploaded yet?): {titles_preview}"
                + (" ..." if len(unmatched) > 5 else ""),
                color="yellow",
            )
            if verbose:
                # Diagnostics on a small sample: does a track with the same
                # title exist but with a different artist/album? Helps
                # distinguish "really not uploaded" from "a metadata issue
                # preventing the match".
                for title, artist, album in unmatched[:3]:
                    similar = by_title_index.get(normalize(title))
                    if similar:
                        examples = "; ".join(f"'{a}' / '{al}'" for a, al, _ in similar[:2])
                        log(
                            f"  Hint for '{title}': track(s) with the same title "
                            f"found on iBroadcast with a different artist/album - {examples} "
                            f"(local: '{artist}' / '{album}')",
                            color="dim",
                        )

        if (fallback_album_used or fallback_artist_used) and verbose:
            parts = []
            if fallback_album_used:
                parts.append(f"{fallback_album_used} via title+album (different artist)")
            if fallback_artist_used:
                parts.append(f"{fallback_artist_used} via title+artist (different album)")
            log(f"Playlist '{name}': {' and '.join(parts)}.", color="cyan")

        if not track_ids:
            log(f"Playlist '{name}': no tracks matched, skipping.", color="yellow")
            continue

        # `is not None`, not truthiness: playlist id 0 is a legitimate id
        # on some backends, and `if existing_id:` would silently treat it
        # as "doesn't exist" and create a duplicate instead of updating.
        existing_id = playlist_index.get(normalize(name))

        if dry_run:
            action = "would update" if existing_id is not None else "would create"
            log(f"[dry-run] Playlist '{name}': {action} with {len(track_ids)} track(s).", color="magenta")
            continue

        if existing_id is not None:
            log(f"Playlist '{name}': updating ({len(track_ids)} tracks).", color="green")
            client.api_call("updateplaylist", {"playlist": existing_id, "tracks": track_ids})
        else:
            log(f"Playlist '{name}': creating ({len(track_ids)} tracks).", color="green")
            client.api_call("createplaylist", {"name": name, "tracks": track_ids})

    if total_fallback_album_used:
        log(
            f"In total, {total_fallback_album_used} track(s) matched via the title+album fallback "
            f"(different artist between Music.app and iBroadcast - often featurings "
            f"formatted differently).",
            color="cyan",
        )
    if total_fallback_artist_used:
        log(
            f"In total, {total_fallback_artist_used} track(s) matched via the title+artist fallback "
            f"(different album - often an empty local album tag vs. 'Unknown Album' on iBroadcast's side).",
            color="cyan",
        )
