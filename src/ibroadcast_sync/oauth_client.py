"""OAuth authentication (Authorization Code + PKCE) and iBroadcast API client.

The flow: open the browser on iBroadcast's authorization page, receive the
code via a small local HTTP server for the duration of the callback, then
exchange it for a token cached on disk (``data/ibroadcast_sync_token.json``).
Subsequent runs reuse that token (and silently refresh it once it expires),
so the browser step only comes up rarely.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import (
    API_URL,
    CLIENT_ID,
    CLIENT_NAME,
    DEVICE_NAME,
    LIBRARY_URL,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    REDIRECT_URI,
    SCOPES,
    TOKEN_FILE,
    USER_AGENT,
    VERSION,
)
from .logging_utils import log

Token = dict[str, Any]


class OAuthError(Exception):
    def __init__(self, code: str | None, message: str | None) -> None:
        super().__init__(message)
        self.code = code


class ServerError(Exception):
    pass


def generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


class _CallbackServer(HTTPServer):
    """Typed subclass so mypy knows about the attributes _CallbackHandler
    stashes on the server instance to hand the result back to the caller
    of handle_request()."""

    auth_code: str | None = None
    auth_state: str | None = None
    auth_error: str | None = None
    expected_path: str = "/"
    hit_expected_path: bool = False


class _CallbackHandler(BaseHTTPRequestHandler):
    """Receives the OAuth redirect (?code=...&state=...) on localhost.

    Browsers commonly fire an automatic, unrelated GET (most often
    /favicon.ico) at whatever origin they just navigated to - since the
    server only handles one request per handle_request() call, that stray
    request could otherwise be mistaken for the real callback and reported
    as "no code received" even though the actual redirect was about to
    arrive. Anything that doesn't match the configured callback path is
    answered with a plain 404 and ignored, so the caller's loop keeps
    waiting for the real one.
    """

    def do_GET(self) -> None:
        server = cast(_CallbackServer, self.server)
        request_path = urlparse(self.path).path

        if request_path != server.expected_path:
            self.send_response(404)
            self.end_headers()
            return

        server.hit_expected_path = True
        qs = parse_qs(urlparse(self.path).query)
        server.auth_code = qs.get("code", [None])[0]
        server.auth_state = qs.get("state", [None])[0]
        server.auth_error = qs.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if server.auth_error:
            self.wfile.write(
                b"<html><body>Authorization failed. You can close this tab "
                b"and check the terminal.</body></html>"
            )
        else:
            self.wfile.write(
                b"<html><body>Authorization received. You can close this tab "
                b"and go back to the terminal.</body></html>"
            )

    def log_message(self, format: str, *args: Any) -> None:
        pass  # silence the default HTTP logs on stderr


def wait_for_oauth_callback(
    redirect_uri: str, timeout: int = 180
) -> tuple[str | None, str | None, str | None]:
    parsed = urlparse(redirect_uri)
    port = parsed.port or 80
    server = _CallbackServer(("localhost", port), _CallbackHandler)
    server.expected_path = parsed.path or "/"

    # Loop rather than a single handle_request(): a stray browser request
    # (see _CallbackHandler's docstring) would otherwise be mistaken for
    # the real callback. Each iteration gets whatever's left of the
    # overall timeout budget, rather than the full timeout again, so a
    # burst of unrelated requests can't extend the wait indefinitely.
    deadline = time.monotonic() + timeout
    while not server.hit_expected_path:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        server.timeout = remaining
        server.handle_request()
    server.server_close()
    return server.auth_code, server.auth_state, server.auth_error


class IBroadcastClient:
    def __init__(self) -> None:
        self.token: Token | None = None
        # Guards refreshing (and writing) the token: if several threads are
        # uploading in parallel and all hit an expired token at once, only
        # one network refresh should happen (a race could otherwise
        # invalidate the refresh_token if the server rotates it on every
        # use), and only one disk write at a time, to avoid a corrupted
        # file.
        self._token_lock = threading.Lock()
        # Signals an unrecoverable authentication failure (invalid
        # refresh_token, not just expired) - lets the main thread detect
        # the situation and stop the run instead of silently grinding
        # through thousands of doomed files.
        self.auth_dead = threading.Event()

    def load_token(self) -> None:
        try:
            with open(TOKEN_FILE) as f:
                self.token = json.load(f)
        except Exception:
            self.token = None

    def _write_token_file(self) -> None:
        """Atomic write (temp file + rename) of the current token. Internal
        use only: assumes the caller already holds _token_lock if needed -
        don't call this from the outside, use save_token() instead."""
        tmp_path = TOKEN_FILE.with_name(TOKEN_FILE.name + ".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(self.token, f)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, TOKEN_FILE)
        except Exception as e:
            log(f"Warning: could not save the token: {e}")

    def save_token(self) -> None:
        """Public entry point, lock-protected - for external callers
        (login(), 401 retry, etc.)."""
        with self._token_lock:
            self._write_token_file()

    def oauth_exchange_code(self, code: str, code_verifier: str) -> Token:
        response = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            headers={"User-Agent": USER_AGENT},
        )
        data = response.json()
        if not response.ok:
            raise OAuthError(data.get("error"), data.get("error_description"))
        return data

    def refresh_token(self, refresh_token: str) -> Token:
        response = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"User-Agent": USER_AGENT},
        )
        data = response.json()
        if not response.ok:
            raise OAuthError(data.get("error"), data.get("error_description"))
        return data

    def refresh_if_necessary(self) -> None:
        with self._token_lock:
            if self.token is None:
                return
            if self.token.get("expires_at", 0) <= time.time():
                try:
                    log("Refreshing token...")
                    new_token_data = self.refresh_token(self.token["refresh_token"])
                    # Merge rather than replace: some OAuth servers only
                    # return a new access_token on refresh and omit
                    # refresh_token entirely when it hasn't changed. A full
                    # replace would then silently drop the still-valid
                    # refresh_token, breaking every subsequent refresh with
                    # a KeyError on the very next expiry.
                    self.token.update(new_token_data)
                    self.token["expires_at"] = time.time() + self.token["expires_in"]
                    self.auth_dead.clear()
                    # CRITICAL: persist immediately. If the server rotates
                    # the refresh_token on every use, the old one becomes
                    # invalid right here - not saving now would leave the
                    # stale token on disk if the process stops before some
                    # external save_token() call happens elsewhere (e.g. a
                    # run that only does this silent refresh at startup and
                    # never touches the token again afterwards).
                    self._write_token_file()
                except OAuthError as e:
                    log(f"Refresh failed, re-authentication required: {e}")
                    self.token = None
                    self.auth_dead.set()

    def login(self) -> bool:
        """Authenticates via Authorization Code + PKCE. Interactive only the
        first time (the token is then cached on disk)."""
        self.load_token()
        self.refresh_if_necessary()
        if self.token is not None:
            return True

        verifier, challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(16)

        params = {
            "client_id": CLIENT_ID,
            "state": state,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": " ".join(SCOPES),
            "redirect_uri": REDIRECT_URI,
        }
        auth_url = f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

        print(f"Opening the browser for authorization. If nothing opens, go to:\n{auth_url}\n")
        with contextlib.suppress(Exception):
            webbrowser.open(auth_url)

        log("Waiting for authorization in the browser (3 min max)...")
        try:
            code, returned_state, error = wait_for_oauth_callback(REDIRECT_URI)
        except OSError as e:
            log(
                f"Could not open the local server on {REDIRECT_URI}: {e}. "
                "Check that the port isn't already in use, or change "
                "IBROADCAST_REDIRECT_URI (and the Redirect URI configured "
                "on ibroadcast.com accordingly)."
            )
            return False

        if error:
            log(f"Error returned by iBroadcast: {error}")
            return False
        if not code:
            log("No code received (timeout, or the callback was never hit).")
            return False
        if returned_state != state:
            log("The returned 'state' parameter doesn't match what was sent, aborting for safety.")
            return False

        try:
            self.token = self.oauth_exchange_code(code, verifier)
            self.token["expires_at"] = time.time() + self.token["expires_in"]
            self.auth_dead.clear()
        except OAuthError as e:
            log(f"Error exchanging the code for a token: {e}")
            return False

        self.save_token()
        return True

    def auth_header(self) -> dict[str, str]:
        """The `Authorization` header for the current token. Public: used
        directly by upload.py for the raw multipart upload/md5 endpoints,
        which don't go through api_call()'s JSON wrapper. Requires a
        loaded token - call login() first."""
        assert self.token is not None
        return {"Authorization": f"{self.token['token_type']} {self.token['access_token']}"}

    def api_call(self, mode: str, extra: dict[str, Any] | None = None, retry: bool = True) -> Any:
        """Generic call to the JSON API (api.ibroadcast.com)."""
        body = {
            "mode": mode,
            "version": VERSION,
            "client": CLIENT_NAME,
            "device_name": DEVICE_NAME,
            "user_agent": USER_AGENT,
        }
        if extra:
            body.update(extra)

        response = requests.post(
            API_URL,
            data=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **self.auth_header(),
            },
        )

        if response.status_code == 401 and retry:
            self.refresh_if_necessary()
            self.save_token()
            return self.api_call(mode, extra, retry=False)

        if not response.ok:
            raise ServerError(f"Invalid server status ({mode}): {response.status_code}")

        data = response.json()
        if data.get("result") is False:
            raise ServerError(f"Call {mode} failed: {data.get('message')}")
        return data

    def fetch_library(self) -> Any:
        response = requests.post(
            LIBRARY_URL,
            data=json.dumps(
                {
                    "mode": "library",
                    "client": CLIENT_NAME,
                    "device_name": DEVICE_NAME,
                    "version": VERSION,
                }
            ),
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **self.auth_header(),
            },
        )
        if not response.ok:
            raise ServerError(f"Invalid server status (library): {response.status_code}")
        return response.json()
