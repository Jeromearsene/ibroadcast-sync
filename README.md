# ibroadcast-sync

🇫🇷 [Lire en français](README.fr.md)

[![CI](https://github.com/Jeromearsene/ibroadcast-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeromearsene/ibroadcast-sync/actions/workflows/ci.yml)

> Badge points at `Jeromearsene/ibroadcast-sync` - update the URL above if you push under a different GitHub username or repo name.

Sync your local music library (via **Music.app** on macOS, or a plain
folder) with [iBroadcast](https://ibroadcast.com):

1. **Upload** new tracks (server-side MD5 dedup, same as the official iBroadcast script).
2. **Playlists**: creates/updates iBroadcast playlists from your Music.app playlists.
3. **Ratings** (`--sync-ratings`): converts Music.app star ratings (0-100) to iBroadcast's scale (0-5).

Built to run unattended (cron/launchd) once configured.

> **New to the command line?** Follow the
> [step-by-step beginner's guide](docs/GETTING_STARTED.md) instead — it
> assumes zero prior experience.

## Contents

- [What's verified vs. what isn't](#whats-verified-vs-what-isnt)
- [Installation](#installation)
- [Configuration (create your own iBroadcast app)](#configuration-create-your-own-ibroadcast-app)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Project structure](#project-structure)
- [Development: tests, type checking, linting](#development-tests-type-checking-linting)
- [Automation (launchd)](#automation-launchd)
- [Project website](#project-website)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)

## What's verified vs. what isn't

- **The OAuth flow + upload**: taken almost as-is from the official
  [`iBroadcastMediaServices/ibroadcast-uploaders`](https://github.com/iBroadcastMediaServices/ibroadcast-uploaders)
  script (MIT). Endpoints, request format, MD5 dedup: identical to what
  already works.
- **Library reading and playlist endpoints** (`createplaylist`,
  `updateplaylist`): based on the public docs at
  `help.ibroadcast.com/en/developer/api`. Track matching (title/artist/album)
  assumes a particular JSON structure — **verify with `--dump-library`
  before trusting the sync.**
- **Music.app playlist/rating extraction** (JXA via `osascript`): written
  from Music.app's scripting docs. **Verify with `--dump-playlists` first.**

In short: the "upload" part is solid (adapted from a working official
script), the "playlists/ratings" part deserves a check on your end before
running it unsupervised.

## Installation

Requirements: Python 3.9+, [Poetry](https://python-poetry.org/docs/#installation).

```bash
git clone <your-repo-url>
cd ibroadcast-sync
poetry install
```

## Configuration (create your own iBroadcast app)

The client_id embedded in the official script only has the `account:read` +
`upload` scopes (not enough to manage playlists), and it's only enabled for
the "device code" flow (the QR code). Apps you create yourself via
"Developer" use the **Authorization Code + PKCE** flow instead — that's what
this project uses (opens a browser tab + a temporary local HTTP server to
catch the redirect, instead of the QR code).

1. Go to [ibroadcast.com](https://ibroadcast.com), sign in, click
   **Developer** at the bottom of the account page.
2. Create a new app.
3. Set a **Redirect URI**. Use exactly:

   ```text
   http://localhost:8912/callback
   ```

   (must match character-for-character what the script sends — scheme,
   port, and path included. For a different port/path, see
   `IBROADCAST_REDIRECT_URI` below.)
4. Copy `.env.example` to `.env` and fill in the `client_id` you got:

   ```bash
   cp .env.example .env
   # then edit .env
   ```

   `.env` is picked up automatically the next time you run the script —
   no need to `source` it or export anything by hand.

## Getting started

### 1. Check playlist extraction (macOS, Music.app installed)

```bash
poetry run ibroadcast-sync --dump-playlists
```

Check that you get your playlists back with title/artist/album for each track.

### 2. First authentication + library check

```bash
poetry run ibroadcast-sync --dump-library
```

The first time, a browser tab opens automatically (if not, the link is also
printed in the terminal). Authorize the app; the script picks back up on its
own (it briefly listens on `localhost:8912`). The token is cached in
`data/ibroadcast_sync_token.json` (chmod 600) — no need to go through the
browser again on subsequent runs, as long as the refresh token stays valid.

This writes the full library to `data/ibroadcast_library_dump.json`. Open it
and check the structure of a track: is there a plain `title` field, and
`artist`/`album` directly, or rather `artist_id`/`album_id` pointing into
`library['artists']` / `library['albums']`? The code handles both cases in
`index_remote_tracks()` (`src/ibroadcast_sync/matching.py`), but if the key
names differ from what's assumed, that's where to adjust.

### 3. Dry run

```bash
poetry run ibroadcast-sync --dry-run
```

Shows what would be uploaded and which playlists would be created/updated,
without sending anything. Check in particular the tracks listed as "not
found" for a playlist — if everyone is "not found", the title/artist/album
matching isn't working and you need to look at the library dump.

### 4. For real

```bash
poetry run ibroadcast-sync
```

With no arguments at all, an **interactive wizard** walks you through it
(file source, upload yes/no, playlists yes/no, dry-run, parallelism). As
soon as any argument is present, this is skipped and the flags are used
as-is (handy for cron/launchd).

## Usage

```text
poetry run ibroadcast-sync [options]

--source-dir PATH     Force scanning this folder instead of asking Music.app
                       for file locations
--no-upload           Don't upload new files
--no-playlists        Don't sync playlists
--workers N           Files processed (hash + upload) in parallel (default 4)
--dry-run             Simulate without sending anything
--sync-ratings        Sync Music.app ratings -> iBroadcast (0-5 stars)
--dump-library        Write the iBroadcast library to a JSON file, then exit
--dump-playlists      Extract Music.app playlists, print them, then exit
```

Useful combos:

- `--no-playlists`: upload only (handy for a frequent nightly cron job).
- `--no-upload`: playlists only.
- `--source-dir /other/folder`: by default, the script asks Music.app
  directly for each track's location (works regardless of which disk —
  internal, external, network).

A shell launcher is also provided to avoid retyping `poetry run` (and to
give cron/launchd one fixed path to call regardless of working
directory):

```bash
./scripts/run.sh --dry-run
```

## Project structure

```text
ibroadcast-sync/
├── pyproject.toml              # dependencies, `ibroadcast-sync` script, Ruff/mypy/pytest config (Poetry)
├── .env.example                # environment variables to copy to .env
├── .python-version             # pyenv pin so `poetry install` finds a working interpreter
├── .markdownlint.json          # markdown lint config (used by editors/CI that check docs)
├── .pre-commit-config.yaml     # optional: run Ruff automatically on commit
├── .github/workflows/ci.yml    # lint + type check + test matrix on push/PR
├── .github/actions/setup-poetry/ # composite action shared by both CI jobs
├── src/ibroadcast_sync/
│   ├── cli.py                  # argparse, interactive wizard, orchestration
│   ├── config.py               # constants, API URLs, data location
│   ├── logging_utils.py        # timestamped log(), built on Rich
│   ├── oauth_client.py         # OAuth PKCE flow + iBroadcast API client
│   ├── md5_cache.py            # on-disk MD5 cache (load/save/hash)
│   ├── progress.py             # live terminal progress bar (upload + ratings)
│   ├── upload.py               # file discovery + parallel upload orchestration
│   ├── musicapp.py             # JXA bridge to Music.app (tracks/playlists/ratings)
│   ├── matching.py             # text normalization + remote library indexing
│   ├── playlists.py            # playlist sync
│   └── ratings.py              # rating sync
├── tests/                      # pytest suite (pure logic, network/macOS calls mocked)
├── data/                       # MD5 cache, OAuth token, dumps, logs (git-ignored)
├── scripts/run.sh              # launcher (cds to the project root, then `poetry run`)
└── docs/
    └── com.example.ibroadcast-sync.plist.example
```

**The `data/` folder** stays at the project root instead of a hidden system
folder (`~/.cache`, etc.) — on purpose, to stay easy to open and inspect
(the MD5 cache in particular). It's excluded from git via `.gitignore` (it
holds an OAuth token and details of your local library). Its location is
configurable via `IBROADCAST_DATA_DIR` if you'd rather use somewhere else.

## Development: tests, type checking, linting

```bash
poetry run pytest              # run the test suite (with coverage summary)
poetry run mypy src tests      # type check (strict: disallow_untyped_defs)
poetry run ruff check .        # lint
poetry run ruff format .       # format
```

**Tests** (`tests/`, via [pytest](https://docs.pytest.org)) cover the pure
logic: text normalization and library matching, playlist sync, the rating
conversion, MD5 caching, file discovery, PKCE generation, and token
refresh (mocked, no real network calls) — plus a few structural sanity
checks on `docs/index.html` itself (tag balance, no duplicate ids, and
that every English content block has a French counterpart). Deliberately
not covered: the actual HTTP calls and the macOS/JXA bridge to Music.app —
mocking those thoroughly would cost more than it'd catch bugs, for a
personal utility. Coverage sits around 45-50% as a result; that's an
intentional trade-off, not a gap to close for its own sake.

**Type checking**: the whole codebase is annotated and checked with
[mypy](https://mypy.readthedocs.io) in strict-ish mode
(`disallow_untyped_defs = true` — see `[tool.mypy]` in `pyproject.toml`).

**Linting/formatting**: [Ruff](https://docs.astral.sh/ruff/) handles both,
with pycodestyle, pyflakes, isort, bugbear, pyupgrade, simplify,
comprehensions, and pep8-naming enabled (see `[tool.ruff]` /
`[tool.ruff.lint]`).

Optionally, install [pre-commit](https://pre-commit.com) to run Ruff
automatically before every commit:

```bash
pip install pre-commit
pre-commit install
```

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs ruff, mypy, and
the test suite (on Python 3.9 and 3.12) on every push and pull request.

## Automation (launchd)

Once `--dry-run` convinces you the matching works correctly, you can
schedule the upload alone every night, and the playlist sync less often (it
does a full library fetch, so it's a bit heavier).

A ready-to-use example is provided in
[`docs/com.example.ibroadcast-sync.plist.example`](docs/com.example.ibroadcast-sync.plist.example).
Adjust the paths and your `client_id`, copy it to
`~/Library/LaunchAgents/`, then:

```bash
launchctl load ~/Library/LaunchAgents/com.example.ibroadcast-sync.plist
```

Authentication is only interactive on the very first run (the one you launch
yourself in a terminal, not via launchd). Once the token is cached in
`data/`, the scheduled job runs unattended — it refreshes itself via the
refresh token, without going through the browser again.

## Project website

A small landing page lives at [`docs/index.html`](docs/index.html) —
useful to link people to instead of the raw README. To publish it for
free via GitHub Pages: repo **Settings → Pages → Build and deployment →
Deploy from a branch**, pick the `main` branch and the **/docs** folder,
save. It'll be live at `https://<your-username>.github.io/ibroadcast-sync/`
within a minute or two.

The page's Open Graph / Twitter Card meta tags (for link previews on
Slack, Discord, etc.) hard-code that same URL as `og:url` — update it in
`docs/index.html` if your username or repo name differs from
`Jeromearsene/ibroadcast-sync`.

## Known limitations

- Playlist/rating matching is exact (title/artist/album normalized,
  case- and accent-insensitive), with two non-ambiguous fallbacks
  (title+album, title+artist) — a featuring written very differently
  between Music.app and iBroadcast (e.g. "feat." vs "ft.") may still not
  match. Worth watching on the first runs (see the "not found" log lines).
- Text normalization strips accents/diacritics via Unicode NFKD, which
  works well for Latin-script titles but can reduce a title in a
  non-Latin script (Japanese, Cyrillic, ...) to a near-empty string. This
  doesn't cause incorrect matches (the full title+artist+album combination
  is still used), but it can make the verbose "similar track" diagnostic
  hint noisy for libraries with a lot of non-Latin-script titles.
- `updateplaylist` replaces the playlist's full content on every run — if
  you edit a playlist directly on iBroadcast between two syncs, those
  changes get overwritten by the local version on the next run.
- Converting a Music.app rating (0-100, half-stars) to iBroadcast's scale
  (integer 0-5) loses the half-star (rounded to the nearest whole star).
- `--sync-ratings` waits at least ~0.3s before every single API call
  (growing further if the server rate-limits), even on the very first
  request — an empirically-tuned precaution against iBroadcast's
  rate-limiter, not a bug, but it means rating a library with many
  thousands of tracks for the first time can take a while (a few thousand
  tracks: roughly 15-20 minutes at minimum).
- `get_music_app_playlists()` has no per-track loop fallback the way track
  locations and ratings do (see `musicapp.py`) — if the batch JXA access
  ever fails outright rather than degrading per-field, playlist sync fails
  for the whole run rather than falling back to a slower method.

## Troubleshooting

**`poetry install` / `poetry run` fails with `Command [...python...] returned
non-zero exit status 127` and/or a message like "Python poetry project
detected. Run mkvenv to setup autoswitching"**

This is unrelated to this project — `pyproject.toml` only requires Python
3.9+, nothing unusual. It comes from a broken `pyenv` setup on your machine,
and the "mkvenv" message is a shell prompt plugin (in your dotfiles)
reacting to the presence of a `pyproject.toml`, not something Poetry itself
prints.

The most common cause: your pyenv **global** version is set to `system`,
and on macOS the system Python only ships a `python3` binary — no plain
`python`. The `pyenv/shims/python` shim has nothing to run and fails with
exit code 127. Diagnose with:

```bash
pyenv versions   # what's actually installed (look for the `*`)
pyenv version    # what pyenv resolves to *here*, and why
```

If `pyenv version` shows `system`, or a version that doesn't appear in
`pyenv versions`, that confirms it. Fix it for this project only (doesn't
touch your global setting) — this repo already ships a `.python-version`
file, but if you need to pick a different installed version:

```bash
pyenv local 3.10.8   # any 3.9+ version from `pyenv versions`
poetry install
```

Or sidestep pyenv entirely and point Poetry at your system Python:

```bash
poetry env use $(which python3)
poetry install
```

## License

MIT — see [`LICENSE`](LICENSE) (includes attribution for the upload code
adapted from the official iBroadcast script).
