"""Command-line entry point: interactive wizard, argparse, and orchestration
of the individual steps (upload / playlists / ratings / diagnostic dumps).
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import CLIENT_ID, LIBRARY_DUMP_FILE
from .logging_utils import log
from .musicapp import get_music_app_playlists
from .oauth_client import IBroadcastClient
from .playlists import sync_playlists
from .ratings import sync_ratings
from .upload import do_upload

# --------------------------------------------------------------------------
# Interactive wizard - only used when the script is launched with no
# arguments at all (ibroadcast-sync, no flags). As soon as a single
# argument is present, we go through argparse normally (useful for
# cron/launchd, where interactivity doesn't make sense since no one is
# there to answer the prompts).
# --------------------------------------------------------------------------


def ask(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer if answer else (default or "")


def ask_yes_no(question: str, default: bool = True) -> bool:
    default_label = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{question} [{default_label}]: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer 'y' or 'n'.")


def interactive_wizard() -> argparse.Namespace:
    print("=== ibroadcast-sync - interactive wizard ===")
    print("(launch with arguments, e.g. --dry-run, to skip this wizard - see --help)\n")

    source_dir = None
    if ask_yes_no("Fetch track locations directly from Music.app (recommended)", default=True):
        source_dir = None
    else:
        source_dir = ask("Path to your music root folder") or None

    do_upload_flag = ask_yes_no("Upload new tracks to iBroadcast", default=True)
    do_playlists_flag = ask_yes_no("Sync Music.app playlists", default=True)
    do_ratings_flag = ask_yes_no("Sync Music.app ratings to iBroadcast (0-5 stars)", default=False)
    dry_run = ask_yes_no("Simulation mode (dry-run: nothing gets sent, just a preview)", default=False)

    workers_str = ask("Number of files processed in parallel", default="4")
    try:
        workers = max(1, int(workers_str))
    except ValueError:
        print(f"  Invalid value ('{workers_str}'), keeping 4.")
        workers = 4

    print()
    print("Summary:")
    print(f"  - Source        : {'Music.app (automatic)' if source_dir is None else source_dir}")
    print(f"  - Upload        : {'yes' if do_upload_flag else 'no'}")
    print(f"  - Playlists     : {'yes' if do_playlists_flag else 'no'}")
    print(f"  - Ratings       : {'yes' if do_ratings_flag else 'no'}")
    print(f"  - Dry-run       : {'yes' if dry_run else 'no'}")
    print(f"  - Parallelism   : {workers}")
    print()
    if not ask_yes_no("Go ahead", default=True):
        print("Cancelled.")
        sys.exit(0)
    print()

    return argparse.Namespace(
        source_dir=source_dir,
        no_upload=not do_upload_flag,
        no_playlists=not do_playlists_flag,
        workers=workers,
        dry_run=dry_run,
        sync_ratings=do_ratings_flag,
        dump_library=False,
        dump_playlists=False,
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def positive_int(value: str) -> int:
    """argparse `type=` validator: rejects zero/negative values with a
    clean argparse-level error instead of letting them reach
    ThreadPoolExecutor(max_workers=...), which raises a raw ValueError for
    anything less than 1."""
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ibroadcast-sync",
        description="iBroadcast sync (upload + Music.app playlists + ratings)",
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Force scanning this folder instead of asking Music.app for file locations",
    )
    parser.add_argument("--no-upload", action="store_true", help="Don't upload new files")
    parser.add_argument("--no-playlists", action="store_true", help="Don't sync playlists")
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=4,
        help="Number of files processed (hash + upload) in parallel (default: 4). "
        "Set to 1 to fall back to sequential behavior.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate without sending anything")
    parser.add_argument(
        "--sync-ratings",
        action="store_true",
        help="Sync Music.app ratings to iBroadcast (0-5 stars, rounded to the nearest point)",
    )
    parser.add_argument(
        "--dump-library",
        action="store_true",
        help="Fetch the library and write it to a JSON file for inspection, then exit",
    )
    parser.add_argument(
        "--dump-playlists",
        action="store_true",
        help="Extract Music.app playlists, print them, then exit",
    )
    return parser


def main() -> None:
    parser = build_parser()

    # No arguments at all -> interactive wizard. As soon as a single
    # argument is present (even just --dry-run), we assume a
    # scripted/cron usage and go through argparse normally.
    args = interactive_wizard() if len(sys.argv) == 1 else parser.parse_args()

    # --dump-playlists never touches the iBroadcast API (it only shells
    # out to Music.app), so it must not require CLIENT_ID to be configured
    # - the README's "Getting started" walkthrough deliberately has people
    # try this one first, before setting up credentials in the next step.
    if args.dump_playlists:
        playlists = get_music_app_playlists(verbose=True)
        print(json.dumps(playlists, indent=2, ensure_ascii=False))
        return

    if CLIENT_ID == "REPLACE_WITH_YOUR_CLIENT_ID":
        log(
            "CLIENT_ID is not configured. Create an app on https://ibroadcast.com "
            "(Developer section) then set IBROADCAST_CLIENT_ID (environment "
            "variable, see .env.example)."
        )
        sys.exit(1)

    client = IBroadcastClient()
    if not client.login():
        log("Authentication failed.")
        sys.exit(1)

    if args.dump_library:
        library = client.fetch_library()
        with open(LIBRARY_DUMP_FILE, "w") as f:
            json.dump(library, f, indent=2, ensure_ascii=False)
        log(f"Library written to {LIBRARY_DUMP_FILE}. Check its structure before running a real sync.")
        return

    if not args.no_upload:
        do_upload(client, args.source_dir, args.dry_run, workers=args.workers)

    if not args.no_playlists:
        sync_playlists(client, args.dry_run, verbose=True)

    if args.sync_ratings:
        sync_ratings(client, args.dry_run, verbose=True)
