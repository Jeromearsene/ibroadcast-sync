#!/usr/bin/env bash
# Convenience launcher so you don't have to remember the exact poetry
# command, and so cron/launchd can call one fixed path regardless of your
# current directory. `.env` itself is loaded automatically by the script
# (see config.py) - this just makes sure `poetry run` executes from the
# project root, where `.env` and `pyproject.toml` actually live.
#
# Usage:
#   ./scripts/run.sh                 # interactive wizard
#   ./scripts/run.sh --dry-run       # simulation
#   ./scripts/run.sh --no-playlists  # upload only (cron/launchd)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

exec poetry run ibroadcast-sync "$@"
