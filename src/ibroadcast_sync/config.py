"""Central configuration: OAuth credentials, API URLs, and the location of
data files (cache, token, dumps, logs).

All data files live in a single ``data/`` folder at the project root,
rather than scattered across hidden system directories (``~/.cache``,
``~/Library/Application Support``, ...): that's deliberate, so they stay
visible and easy to inspect directly (the MD5 cache in particular, which
you may want to open and read without hunting for where it ended up). The
folder is configurable via ``IBROADCAST_DATA_DIR`` if you'd rather use a
different location.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from . import __version__

# --------------------------------------------------------------------------
# Data location
# --------------------------------------------------------------------------

# Project root = two levels above src/ibroadcast_sync/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Loads `.env` (if present) into os.environ before anything below reads
# IBROADCAST_CLIENT_ID / IBROADCAST_REDIRECT_URI / IBROADCAST_DATA_DIR, so
# `poetry run ibroadcast-sync` picks it up with no extra step - no need to
# `source .env` or export vars by hand first. Pointed explicitly at the
# project root rather than relying on python-dotenv's upward-search
# default, for the same reason DATA_DIR below doesn't rely on cwd either.
# A missing .env is not an error: load_dotenv() just returns False, and
# vars already set in the real environment always take precedence (the
# default `override=False`) - a shell export still wins over the file.
load_dotenv(_PROJECT_ROOT / ".env")

DATA_DIR = Path(os.environ.get("IBROADCAST_DATA_DIR", _PROJECT_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_FILE = DATA_DIR / "ibroadcast_sync_token.json"
LIBRARY_DUMP_FILE = DATA_DIR / "ibroadcast_library_dump.json"
MD5_CACHE_FILE = DATA_DIR / "ibroadcast_md5_cache.json"
FAILURES_LOG_FILE = DATA_DIR / "ibroadcast_sync_failures.log"

# --------------------------------------------------------------------------
# iBroadcast OAuth / API
# --------------------------------------------------------------------------

# Create your own app on https://ibroadcast.com ("Developer" button at the
# bottom of the account page) to get a client_id with the right scopes.
# The client_id embedded in the official script (upload only) does NOT
# have the library:read/write scopes needed for playlists.
#
# IMPORTANT: no client_id is hard-coded here (a personal identifier should
# never be committed). Set your own via the IBROADCAST_CLIENT_ID
# environment variable (see .env.example).
CLIENT_ID = os.environ.get("IBROADCAST_CLIENT_ID", "REPLACE_WITH_YOUR_CLIENT_ID")

SCOPES = [
    "user.account:read",
    "user.upload",
    "user.library:read",
    "user.library:write",
]

# Must match EXACTLY (scheme, host, port, path) the "Redirect URI"
# configured for your app in the Developer section of ibroadcast.com.
REDIRECT_URI = os.environ.get("IBROADCAST_REDIRECT_URI", "http://localhost:8912/callback")

API_URL = "https://api.ibroadcast.com/s/JSON/"
UPLOAD_URL = "https://upload.ibroadcast.com"
LIBRARY_URL = "https://library.ibroadcast.com/"
OAUTH_AUTHORIZE_URL = "https://oauth.ibroadcast.com/authorize"
OAUTH_TOKEN_URL = "https://oauth.ibroadcast.com/token"

VERSION = __version__  # single source of truth: see ibroadcast_sync/__init__.py
CLIENT_NAME = "ibroadcast-sync"
DEVICE_NAME = "ibroadcast-sync"
USER_AGENT = f"ibroadcast-sync/{VERSION}"
