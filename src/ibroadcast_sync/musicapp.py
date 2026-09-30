"""Bridge to Music.app (macOS) via JXA (``osascript -l JavaScript``).

Three extractions, each preferring a "batch" access (a single request for
one property across all tracks at once) over a loop with one Music.app
round-trip per track - that's what lets a library of several tens of
thousands of tracks be processed in seconds rather than minutes. If the
batch access fails (unmaterialized specifier, depending on the property),
each function automatically falls back to a per-track loop, slower but
more robust.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TypedDict

from .logging_utils import log

# Generous on purpose: the loop fallback can legitimately take minutes on
# a large library (see module docstring), and this is meant to catch a
# genuinely hung osascript process - most commonly Music.app silently
# waiting on a macOS Automation/Accessibility permission dialog the first
# time this runs - rather than a slow-but-progressing extraction.
_OSASCRIPT_TIMEOUT_SECONDS = 600


def _run_osascript(script: str) -> subprocess.CompletedProcess[str]:
    """Runs a JXA snippet via osascript, with a timeout so a hung
    Music.app fails with a clear, actionable error instead of hanging the
    whole tool indefinitely and unexplained."""
    try:
        return subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=_OSASCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Music.app did not respond within {_OSASCRIPT_TIMEOUT_SECONDS}s. If this is "
            "the first time running this, check for a macOS permission dialog asking to "
            "let Terminal (or osascript) control Music.app - System Settings -> Privacy "
            "& Security -> Automation - approve it, then try again."
        ) from e


class TrackRef(TypedDict):
    title: str
    artist: str
    album: str


class Playlist(TypedDict):
    name: str
    tracks: list[TrackRef]


class RatedTrack(TypedDict):
    title: str
    artist: str
    album: str
    rating: int


# --------------------------------------------------------------------------
# File locations (used by upload.py when no --source-dir is given: we ask
# Music.app itself instead of guessing a folder - works regardless of the
# library's disk, internal/external/network.
# --------------------------------------------------------------------------

MUSIC_APP_LOCATIONS_JXA_BATCH = r"""
function run() {
  var music = Application('Music');
  var locations = music.tracks.location();
  var paths = [];
  for (var i = 0; i < locations.length; i++) {
    var loc = locations[i];
    paths.push(loc ? loc.toString() : null);
  }
  return JSON.stringify(paths);
}
"""

MUSIC_APP_LOCATIONS_JXA_LOOP = r"""
function run() {
  var music = Application('Music');
  var tracks = music.tracks();
  var paths = [];
  for (var i = 0; i < tracks.length; i++) {
    var loc = null;
    try { loc = tracks[i].location(); } catch (e) { loc = null; }
    paths.push(loc ? loc.toString() : null);
  }
  return JSON.stringify(paths);
}
"""


def get_music_app_track_paths(verbose: bool = False) -> list[str]:
    """Returns the list of existing file paths for every track in the
    Music.app library (tries the batch access, falls back to a loop if it
    fails)."""
    if verbose:
        log("Fetching file locations from Music.app (batch)...")
    result = _run_osascript(MUSIC_APP_LOCATIONS_JXA_BATCH)
    used_fallback = False
    if result.returncode != 0:
        used_fallback = True
        if verbose:
            log(f"  Batch access failed ({result.stderr.strip()}), falling back to a loop (slower)...")
        result = _run_osascript(MUSIC_APP_LOCATIONS_JXA_LOOP)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to fetch locations from Music.app (osascript): {result.stderr.strip()}"
            )

    raw_paths = json.loads(result.stdout)
    paths = [p for p in raw_paths if p]
    missing = len(raw_paths) - len(paths)

    existing = [p for p in paths if os.path.exists(p)]
    not_found = len(paths) - len(existing)

    if verbose:
        log(
            f"  {len(raw_paths)} tracks in Music.app, {missing} with no local location "
            f"(streaming/missing), {not_found} with a path that doesn't exist on disk "
            f"(external drive disconnected?), {len(existing)} usable files."
            + (" [method: loop]" if used_fallback else " [method: batch]")
        )

    return existing


# --------------------------------------------------------------------------
# Music.app playlists
#
# Playlist folders (class "folderPlaylist") are skipped: they're
# containers, not playlists to sync in their own right. The playlists they
# contain remain in the flat list returned by music.playlists() and are
# therefore still processed individually.
# --------------------------------------------------------------------------

MUSIC_APP_JXA = r"""
function run() {
  var music = Application('Music');
  var playlists = music.playlists();
  var result = [];

  for (var i = 0; i < playlists.length; i++) {
    var p = playlists[i];
    var name = p.name();

    var cls = null;
    try { cls = p.class(); } catch (e) { cls = null; }
    if (cls === 'folderPlaylist' || cls === 'folder playlist') {
      continue; // container, not an actual playlist
    }

    var kind = null;
    try { kind = p.specialKind(); } catch (e) { kind = null; }
    if (kind && kind !== 'none') continue; // system playlists (Music, Podcasts, ...)

    var titles = [], artists = [], albums = [];
    try { titles = p.tracks.name(); } catch (e) { titles = []; }
    try { artists = p.tracks.artist(); } catch (e) { artists = []; }
    try { albums = p.tracks.album(); } catch (e) { albums = []; }

    var items = [];
    for (var j = 0; j < titles.length; j++) {
      items.push({
        title: titles[j] || '',
        artist: artists[j] || '',
        album: albums[j] || ''
      });
    }
    result.push({ name: name, tracks: items });
  }

  return JSON.stringify(result);
}
"""


def get_music_app_playlists(verbose: bool = False) -> list[Playlist]:
    if verbose:
        log("Running extraction via osascript (may take a while on a large library)...")
    result = _run_osascript(MUSIC_APP_JXA)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to extract Music.app playlists (osascript): {result.stderr.strip()}")
    playlists = json.loads(result.stdout)
    if verbose:
        for pl in playlists:
            log(f"  Playlist '{pl['name']}': {len(pl['tracks'])} track(s)")
    return playlists


# --------------------------------------------------------------------------
# Music.app ratings (across the whole library, not just playlists). Same
# batch-access technique as for title/artist/album (unmaterialized
# specifier, cf. the 'location' issue above).
#
# The Music.app rating is on a 0-100 scale (20 points per star, allowing
# half-stars). iBroadcast only has a 3-state system for tracks (0/1/5, see
# ratings.py) - the conversion is necessarily approximate.
# --------------------------------------------------------------------------

MUSIC_APP_RATINGS_JXA_BATCH = r"""
function run() {
  var music = Application('Music');
  var titles = music.tracks.name();
  var artists = music.tracks.artist();
  var albums = music.tracks.album();
  var ratings = music.tracks.rating();
  var result = [];
  for (var i = 0; i < titles.length; i++) {
    result.push({
      title: titles[i] || '',
      artist: artists[i] || '',
      album: albums[i] || '',
      rating: ratings[i] || 0
    });
  }
  return JSON.stringify(result);
}
"""

MUSIC_APP_RATINGS_JXA_LOOP = r"""
function run() {
  var music = Application('Music');
  var tracks = music.tracks();
  var result = [];
  for (var i = 0; i < tracks.length; i++) {
    var t = tracks[i];
    var title = '', artist = '', album = '', rating = 0;
    try { title = t.name(); } catch (e) {}
    try { artist = t.artist(); } catch (e) {}
    try { album = t.album(); } catch (e) {}
    try { rating = t.rating(); } catch (e) {}
    result.push({ title: title, artist: artist, album: album, rating: rating });
  }
  return JSON.stringify(result);
}
"""


def get_music_app_ratings(verbose: bool = False) -> list[RatedTrack]:
    if verbose:
        log("Fetching Music.app ratings (batch)...")
    result = _run_osascript(MUSIC_APP_RATINGS_JXA_BATCH)
    if result.returncode != 0:
        if verbose:
            log(f"  Batch access failed ({result.stderr.strip()}), falling back to a loop (slower)...")
        result = _run_osascript(MUSIC_APP_RATINGS_JXA_LOOP)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to fetch Music.app ratings (osascript): {result.stderr.strip()}")
    tracks = json.loads(result.stdout)
    if verbose:
        rated = sum(1 for t in tracks if t.get("rating"))
        log(f"  {len(tracks)} tracks total, {rated} with a local rating.")
    return tracks
