# Roadmap

A running list of what's done and what's still an idea — not a commitment,
just somewhere to keep track instead of losing these in a chat history.

## Done

- Upload with server-side MD5 dedup (parallel, retries with backoff).
- Playlist sync (Music.app -> iBroadcast), with fallback matching for
  artist/album metadata mismatches.
- Rating sync (Music.app 0-100 -> iBroadcast 0-5 stars).
- OAuth Authorization Code + PKCE flow (own app, not the limited
  device-code client_id from the official script).
- Poetry packaging, `src/` layout, typed codebase (mypy), Ruff lint/format,
  pytest suite, CI (lint + type check + tests on a Python version matrix).
- Bilingual documentation (EN/FR).

## Ideas (not implemented — design notes only)

### Delete remote tracks that no longer exist locally

Right now the sync is purely additive: a track removed locally (deleted
file, or excluded from the library) stays on iBroadcast forever. A
`--prune` (or similar) mode could:

1. Build the set of local MD5s actually present on this run (already
   computed for the upload step).
2. Diff against the remote MD5 set (`load_remote_md5s()` already fetches
   this).
3. For MD5s present remotely but absent locally, delete the corresponding
   iBroadcast track(s).

Open questions worth resolving before building this:

- **Blast-radius risk**: an unmounted external drive, a bad `--source-dir`,
  or a Music.app library that failed to enumerate fully would look
  identical to "these files were deleted" and could wipe an entire remote
  library. Needs a strong safety net — e.g. refuse to prune past some
  percentage of the remote library in one run (say >10-20%), and/or
  require an explicit `--confirm-prune` on top of `--prune`.
- **What "local" means for pruning**: should it consider only what
  `find_local_files`/`get_music_app_track_paths` sees this run, or a
  separate "tracked" set to avoid pruning tracks that were never covered by
  the current `--source-dir` (e.g. multi-drive setups run separately)?
- Does the iBroadcast API even expose a delete-track call? Not yet checked
  against the docs referenced in the README's "What's verified" section.

### Push local metadata changes (title, rating already covered, other tags) to iBroadcast

Ratings already sync one-way (Music.app -> iBroadcast). Extending that to
title/artist/album edits made locally after the initial upload:

- Needs a reliable way to detect "this track changed" without re-hashing
  the audio (which would look like a brand new file to the MD5-based dedup
  entirely, not a metadata edit) — likely means indexing by
  Music.app's persistent track ID, if scriptable, or a secondary
  title+artist+album fingerprint stored in the MD5 cache alongside the
  hash, compared on each run.
- Needs an iBroadcast API to update track metadata in place (not
  re-upload) — to be confirmed against the docs.
- Same "who wins" question as ratings: if the track was also edited
  directly on iBroadcast between two runs, a local sync would overwrite
  it (already true for playlists today - see the README's known
  limitations - but title edits are more surprising to clobber than
  playlist order).

### Other smaller ideas, unsorted

- `rich.progress.Progress` for the upload/rating progress bar
  (`progress.py`), replacing the hand-rolled ANSI cursor-movement code —
  mentioned once already, still not done.
- Two-way rating sync (iBroadcast -> Music.app), for ratings set directly
  on iBroadcast's web UI.
- A `--dry-run` diff summary that's more structured (e.g. JSON output) for
  scripting around it.
