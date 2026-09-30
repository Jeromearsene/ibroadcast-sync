"""Local <-> remote matching (Music.app to iBroadcast).

ACTUAL format of the iBroadcast library (confirmed via ``--dump-library``,
different from what one might assume up front): each category
(tracks/artists/albums/playlists) is a dict ``{id: [value0, value1, ...]}``
plus a separate ``"map"`` key that gives, for each field name, its index in
the array. E.g. ``tracks["map"]["title"] == 2`` means a track's title is at
``tracks[<id>][2]``. Each field is therefore resolved through that index
(see :func:`get_field`).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Raw structures as returned by the iBroadcast API - typed loosely (Any
# values) since they're untyped JSON on the wire; get_field() is the single
# choke point that pulls typed-enough values back out of them.
Library = dict[str, Any]
FieldMap = dict[str, int]
TrackId = int

PrimaryIndex = dict[tuple[str, str, str], TrackId]
ByTitleAlbumIndex = dict[tuple[str, str], list[tuple[str, TrackId]]]
ByTitleArtistIndex = dict[tuple[str, str], list[tuple[str, TrackId]]]
ByTitleIndex = dict[str, list[tuple[str, str, TrackId]]]

# "Smart" typographic characters that often differ between Music.app's
# metadata and what iBroadcast indexed at upload time. Without this table,
# a naive normalize() (NFKD + ascii encode with 'ignore') would silently
# drop them instead of converting them - "You've" and "You'..." with a
# typographic apostrophe would end up NOT matching identically depending on
# which side used which character.
_PUNCT_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u02bc": "'",
        "`": "'",
        "\u00b4": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u00ab": '"',
        "\u00bb": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",  # non-breaking space -> regular space
    }
)


def normalize(s: str | None) -> str:
    if not s:
        return ""
    s = s.translate(_PUNCT_TRANSLATION)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s)  # multiple spaces/tabs -> a single space
    return s.strip().casefold()


def get_field(record: Any, field_map: FieldMap, key: str, default: Any = None) -> Any:
    """Reads a field from a positional iBroadcast record via the index
    given by its 'map' dictionary."""
    idx = field_map.get(key)
    if idx is None or not isinstance(record, list) or idx >= len(record):
        return default
    return record[idx]


def index_remote_tracks(
    library: Library,
) -> tuple[PrimaryIndex, ByTitleAlbumIndex, ByTitleArtistIndex, ByTitleIndex]:
    """Builds the indexes used to match a local track to an iBroadcast
    track_id, with fallbacks for non-exact matches:
      - primary: (title, artist, album) exact -> track_id
      - by_title_album: (title, album) -> list of (artist, track_id).
        Used as a fallback when the artist doesn't match exactly (e.g.
        Music.app concatenates "Artist A & Artist B" into a single field
        while iBroadcast keeps a primary artist separate from additional
        artists) - only used when the fallback is unambiguous (a single
        candidate track for that title/album pair).
      - by_title_artist: (title, artist) -> list of (album, track_id).
        Used as a fallback when the ALBUM doesn't match (typically:
        Music.app leaves the album tag empty while iBroadcast indexes that
        as the literal string "Unknown Album" - two different ways of
        saying "no album" that don't match as-is) - same principle, only
        used when unambiguous.
      - by_title: title -> list of (artist, album, track_id). Diagnostics
        only, never used for an automatic match (too much risk of false
        positives between different songs sharing the same title).
    """
    lib = library.get("library", library)
    tracks = lib.get("tracks", {})
    artists = lib.get("artists", {})
    albums = lib.get("albums", {})

    tracks_map = tracks.get("map", {})
    artists_map = artists.get("map", {})
    albums_map = albums.get("map", {})

    primary: PrimaryIndex = {}
    by_title_album: ByTitleAlbumIndex = {}
    by_title_artist: ByTitleArtistIndex = {}
    by_title: ByTitleIndex = {}

    for track_id, track in tracks.items():
        if track_id == "map":
            continue
        title = get_field(track, tracks_map, "title", "")
        artist_id = str(get_field(track, tracks_map, "artist_id", ""))
        album_id = str(get_field(track, tracks_map, "album_id", ""))

        artist_name = get_field(artists.get(artist_id), artists_map, "name", "")
        album_name = get_field(albums.get(album_id), albums_map, "name", "")

        norm_title = normalize(title)
        norm_artist = normalize(artist_name)
        norm_album = normalize(album_name)
        tid = int(track_id)

        primary[(norm_title, norm_artist, norm_album)] = tid
        by_title_album.setdefault((norm_title, norm_album), []).append((norm_artist, tid))
        by_title_artist.setdefault((norm_title, norm_artist), []).append((norm_album, tid))
        by_title.setdefault(norm_title, []).append((norm_artist, norm_album, tid))

    return primary, by_title_album, by_title_artist, by_title


def index_remote_ratings(library: Library) -> dict[TrackId, int]:
    """track_id (int) -> current rating on the iBroadcast side (0-5). Lets
    us skip tracks that are already correctly rated (useful if a previous
    run was interrupted - no point re-sending the same ratetrack calls,
    especially since each one costs time due to rate limiting)."""
    lib = library.get("library", library)
    tracks = lib.get("tracks", {})
    tracks_map = tracks.get("map", {})
    ratings: dict[TrackId, int] = {}
    for track_id, track in tracks.items():
        if track_id == "map":
            continue
        ratings[int(track_id)] = get_field(track, tracks_map, "rating", 0) or 0
    return ratings


def index_remote_playlists(library: Library) -> dict[str, int]:
    lib = library.get("library", library)
    playlists = lib.get("playlists", {})
    playlists_map = playlists.get("map", {})

    index: dict[str, int] = {}
    for playlist_id, playlist in playlists.items():
        if playlist_id == "map":
            continue
        name = get_field(playlist, playlists_map, "name", "")
        index[normalize(name)] = int(playlist_id)
    return index


def resolve_track_id(
    title: str,
    artist: str,
    album: str,
    primary_index: PrimaryIndex,
    by_title_album_index: ByTitleAlbumIndex,
    by_title_artist_index: ByTitleArtistIndex,
) -> tuple[TrackId | None, str | None]:
    """Resolves a local (title, artist, album) triple to an iBroadcast
    track_id: exact match first, then the two unambiguous fallbacks
    documented in :func:`index_remote_tracks`.

    Shared by ``playlists.py`` and ``ratings.py``, which both need the
    exact same resolution chain applied to different kinds of local
    tracks (Music.app playlist entries vs. rated tracks).

    Returns ``(track_id, fallback_used)`` where ``fallback_used`` is
    ``None`` for an exact match (or no match at all), or ``"title_album"``
    / ``"title_artist"`` to name which fallback fired - callers that
    report fallback usage (like ``sync_playlists``) can use this; callers
    that don't care (like ``sync_ratings``) can ignore the second value.
    """
    norm_title = normalize(title)
    norm_artist = normalize(artist)
    norm_album = normalize(album)

    track_id = primary_index.get((norm_title, norm_artist, norm_album))
    if track_id is not None:
        return track_id, None

    # Fallback 1: same title + same album, different artist (e.g.
    # Music.app concatenates several artists into one field). Only used
    # when it's UNAMBIGUOUS (a single candidate), otherwise the risk of a
    # wrong match outweighs the benefit.
    album_candidates = by_title_album_index.get((norm_title, norm_album))
    if album_candidates and len(album_candidates) == 1:
        return album_candidates[0][1], "title_album"

    # Fallback 2: same title + same artist, different album (e.g. an
    # empty local album tag vs. "Unknown Album" indexed as such on the
    # iBroadcast side - very common for sketches/audio with no album tag).
    artist_candidates = by_title_artist_index.get((norm_title, norm_artist))
    if artist_candidates and len(artist_candidates) == 1:
        return artist_candidates[0][1], "title_artist"

    return None, None
