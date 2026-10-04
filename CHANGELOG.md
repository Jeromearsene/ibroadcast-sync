# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- A small run-status file (`data/ibroadcast_sync_status.json`), written
  atomically at the end of every real sync (success, early abort on dead
  auth, or crash). Lets an external tool - in particular a menu bar
  companion app - show "last sync" information (timestamp, counts,
  success/error) without parsing the logs or re-running anything. See
  `ibroadcast_sync/status.py`.
- `.env` is now loaded automatically (via `python-dotenv`, in
  `config.py`) whenever the script runs - no more need to `source .env`
  or export variables by hand first. A real shell-exported variable (or
  one set in a launchd plist) still takes priority over the file.
- `.github/actions/setup-poetry/`: a composite action factoring out the
  install-Poetry / setup-Python-with-cache / `poetry install` sequence
  that was duplicated between the `lint` and `test` CI jobs.

### Changed

- `scripts/run.sh` simplified: no longer manually sources `.env` (now
  redundant since the script does that itself) - just `cd`s to the
  project root and runs `poetry run ibroadcast-sync`.

### Fixed (final review pass)

Found by re-reading every module end to end and mutation-testing each fix
(temporarily reverting it and confirming the new test actually fails):

- `oauth_client.py`: a token refresh response that omits `refresh_token`
  (some OAuth servers only return one when it changed) used to wipe out
  the still-valid one via a full replace of `self.token`; now merged
  instead, so the refresh token survives.
- `oauth_client.py`: the local callback server handled exactly one
  request and trusted it blindly - a browser's automatic `GET
  /favicon.ico` (or any other stray request) arriving before the real
  OAuth redirect would be mistaken for it, falsely reporting "no code
  received". Now loops (within the overall timeout budget) until a
  request actually matches the configured callback path.
- `upload.py`: `process_file()` didn't catch `OSError` from hashing a
  file - one that vanished (deleted, drive ejected, network hiccup)
  between being listed and actually being processed would crash the
  entire run instead of being logged as a single failure among
  potentially thousands of files.
- `cli.py`: `--workers 0` (or negative) passed argparse validation and
  only failed later with a raw `ThreadPoolExecutor` `ValueError` -
  the interactive wizard already guarded against this, the direct flag
  didn't. Now rejected upfront with a clear error message.
- `cli.py`: `--dump-playlists` required `CLIENT_ID` to be configured even
  though it never touches the iBroadcast API - contradicting the
  README's own "Getting started" walkthrough, which has people try it
  *before* setting up credentials. Reordered.
- `playlists.py`: `if existing_id:` used truthiness instead of `is not
  None` in three places - a playlist with remote id `0` would be treated
  as "doesn't exist" and get a duplicate created instead of being
  updated.
- `logging_utils.py` / `progress.py`: `log()` (via Rich) and
  `ProgressDisplay`'s live redraw (raw ANSI writes) had no shared lock,
  so a log message during an active upload (e.g. "Refreshing token...")
  could interleave with an in-progress redraw and corrupt the terminal
  output. Now share a lock.
- `musicapp.py`: none of the five `subprocess.run()` calls to `osascript`
  had a timeout - a hung Music.app (most commonly waiting on a macOS
  Automation permission dialog the first time this runs) would hang the
  entire tool indefinitely with no explanation. Added a 10-minute
  timeout (generous enough for the documented loop-fallback case on a
  large library) with a clear error message pointing at the permission
  dialog; extracted into a small shared `_run_osascript()` helper.

### Added

- `docs/index.html`: a small static landing page (hardware/hi-fi themed),
  bilingual (EN/FR) with browser-language auto-detection, a manual toggle
  with flags, and localStorage-persisted preference. No build step, no
  framework - see the reasoning for that choice in the project history.
- `docs/GETTING_STARTED.md` / `.fr.md`: a zero-assumptions tutorial for
  non-developers (opening Terminal, installing Homebrew/Poetry, etc.).
- `ROADMAP.md`: design notes for two not-yet-built ideas (pruning remote
  tracks deleted locally, pushing local metadata edits to iBroadcast) -
  documentation only, nothing implemented.
- `CONTRIBUTING.md`, `SECURITY.md`.
- `.github/dependabot.yml` for monthly dependency update PRs.
- `tests/test_playlists.py`: `sync_playlists()` was previously untested
  (9% coverage) despite `ratings.py` and `oauth_client.py` already
  establishing a mocked-client test pattern; now covered the same way.
- `tests/test_docs_site.py`: structural checks on `docs/index.html` (tag
  balance, no duplicate ids, EN/FR content block counts match, internal
  anchors resolve) - not a browser test, but catches the exact class of
  copy/paste mistakes that's easy to make hand-editing paired-language
  content.
- `.editorconfig` for consistent indentation/whitespace across editors.
- CI: Poetry dependency caching (`cache: poetry`), and a `concurrency`
  group that cancels stale runs on new pushes to the same branch/PR.

### Changed

- Deduplicated the track-matching fallback chain (exact match → unambiguous
  title+album → unambiguous title+artist) that was implemented twice,
  nearly identically, in `playlists.py` and `ratings.py`. Extracted into
  `matching.resolve_track_id()`, now the single implementation both call.
- `requests` and `types-requests` now have an upper bound (`<3.0`),
  matching how `rich` was already pinned.

### Fixed

- `config.VERSION` (sent to the iBroadcast API as the client version) was
  hard-coded to `"0.2"`, out of sync with the actual package version. It
  now derives from `ibroadcast_sync.__version__` (single source of truth).
- `.gitignore` didn't cover `coverage.py` artifacts (`.coverage`,
  `htmlcov/`, `coverage.xml`), which `pytest-cov` writes to the project
  root on every test run.
- `docs/index.html`: the `--ink-faint` color (used for timestamps, badges,
  footer credit) failed WCAG AA contrast (2.83:1 against the lightest
  panel background actually used, needs 4.5:1) - removed in favor of the
  already-compliant `--ink-dim` (4.80:1+).
- `docs/index.html` i18n implementation, found via manual + scripted
  browser testing while building the French version: a bare
  `[data-lang="fr"]` CSS selector also matched the `<html>` element
  itself (which carries that same attribute to hold the current-language
  state), hiding the entire page; `display: revert` on show-French rules
  reset flex containers (`.eyebrow`, `.ctas`) to their block default
  instead of restoring `flex`; and the i18n rules' boosted specificity
  was accidentally overriding the unrelated `.hide-mobile` responsive
  rule, un-hiding a nav link on narrow viewports.

## [0.3.0] - 2026-08-24

### Added

- Test suite (`tests/`, pytest) covering the pure logic: matching,
  normalization, rating conversion, MD5 caching, file discovery, PKCE, and
  token refresh.
- Type hints across the whole codebase, checked with mypy in strict-ish
  mode (`disallow_untyped_defs`).
- CI now also runs mypy and the test suite (on a Python 3.9 / 3.12 matrix),
  in addition to Ruff.
- `CHANGELOG.md`, `.markdownlint.json`.

### Changed

- Split `upload.py` (previously 552 lines) into `upload.py`
  (orchestration), `md5_cache.py` (cache persistence), and `progress.py`
  (live terminal display) - `ratings.py` now imports `ProgressDisplay`
  from `progress.py` instead of reaching into `upload.py`.
- Colored logging (`logging_utils.py`) now uses
  [Rich](https://github.com/Textualize/rich) instead of a hand-rolled ANSI
  color table.
- All source comments, docstrings, identifiers, and CLI/log output
  translated to English.

### Fixed

- Markdown lint issues (MD031, MD040) in both READMEs.

## [0.2.0] - 2026-08-21

Initial public restructuring of the original POC script: Poetry packaging,
multi-module `src/ibroadcast_sync/` layout, OAuth PKCE flow (replacing the
device-code flow, to unlock the playlist/library scopes), bilingual
README, launchd example, Ruff.
