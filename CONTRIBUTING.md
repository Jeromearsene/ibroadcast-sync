# Contributing

This is a personal utility that's open source, not a project actively
seeking contributors — but if you'd like to send a fix or improvement,
here's the workflow.

## Setup

```bash
git clone <your fork's URL>
cd ibroadcast-sync
poetry install
```

See the [README](README.md) for the full picture (what the project does,
how to get an iBroadcast client_id, etc.) — this file only covers the
dev/PR workflow.

## Before opening a PR

Run everything CI runs, locally, in this order:

```bash
poetry run ruff check .              # lint
poetry run ruff format .             # format (auto-fixes)
poetry run mypy src/ibroadcast_sync tests   # type check
poetry run pytest                    # tests (with coverage summary)
```

All four must pass. If `ruff format` changes files, commit those changes
too — CI checks formatting with `--check` and fails on any diff.

Optionally, install [pre-commit](https://pre-commit.com) so Ruff runs
automatically on every commit instead of remembering to run it by hand:

```bash
pip install pre-commit
pre-commit install
```

## Where things live

See the "Project structure" section of the [README](README.md#project-structure)
for the module layout. A few things worth knowing before editing:

- **Type hints are mandatory.** `mypy` runs with `disallow_untyped_defs`,
  so an untyped function signature fails CI, not just a style nit.
- **`docs/index.html` is hand-authored** (no build step, no framework —
  see the reasoning in the project's commit history / chat log if you're
  curious why). Every visible piece of text lives twice in the file, once
  wrapped `data-lang="en"` and once `data-lang="fr"` — if you edit one,
  edit the other. `tests/test_docs_site.py` will fail the build if the
  count of English vs. French content blocks doesn't match, which catches
  the most common way to forget.
- **Tests mock the network and macOS/Music.app calls** rather than hitting
  them for real — see `tests/test_oauth_client.py` or
  `tests/test_playlists.py` for the established pattern (a fake/subclassed
  client, `monkeypatch` for module-level functions like
  `get_music_app_playlists`).
- **`ROADMAP.md`** has a running list of known gaps and half-formed ideas
  (delete-on-remote-if-deleted-locally, metadata push-back, etc.) if
  you're looking for something to work on.

## Commit messages / PR description

No strict format required - just explain what changed and why, especially
for anything touching the matching/fallback logic in `matching.py`
(`resolve_track_id`), which is easy to get subtly wrong in ways tests
won't catch unless you add a case for it.
