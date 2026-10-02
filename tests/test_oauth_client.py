"""Tests for ibroadcast_sync.oauth_client.

Network calls are always mocked here - these tests never hit the real
iBroadcast API.
"""

from __future__ import annotations

import base64
import hashlib
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ibroadcast_sync import oauth_client
from ibroadcast_sync.oauth_client import (
    IBroadcastClient,
    OAuthError,
    ServerError,
    generate_pkce_pair,
    wait_for_oauth_callback,
)


@pytest.fixture
def token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirects TOKEN_FILE to a throwaway path for the duration of a test."""
    path = tmp_path / "token.json"
    monkeypatch.setattr(oauth_client, "TOKEN_FILE", path)
    return path


class TestGeneratePkcePair:
    def test_challenge_is_sha256_of_verifier(self) -> None:
        verifier, challenge = generate_pkce_pair()
        expected_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected_challenge

    def test_verifier_has_no_padding(self) -> None:
        verifier, _ = generate_pkce_pair()
        assert "=" not in verifier

    def test_pairs_are_random(self) -> None:
        assert generate_pkce_pair() != generate_pkce_pair()


class TestTokenPersistence:
    def test_load_token_missing_file_sets_none(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.load_token()
        assert client.token is None

    def test_save_and_load_round_trip(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"access_token": "abc", "token_type": "Bearer"}
        client.save_token()

        reloaded = IBroadcastClient()
        reloaded.load_token()
        assert reloaded.token == client.token

    def test_save_token_sets_restrictive_permissions(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"access_token": "abc"}
        client.save_token()
        mode = token_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestRefreshIfNecessary:
    def test_does_nothing_when_token_is_none(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = None
        client.refresh_if_necessary()  # should not raise
        assert client.token is None

    def test_does_nothing_when_token_not_expired(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() + 3600, "refresh_token": "r"}
        with patch.object(client, "refresh_token") as mock_refresh:
            client.refresh_if_necessary()
        mock_refresh.assert_not_called()

    def test_refreshes_and_persists_when_expired(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() - 1, "refresh_token": "old-refresh"}
        new_token = {
            "access_token": "new",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch.object(client, "refresh_token", return_value=new_token) as mock_refresh:
            client.refresh_if_necessary()

        mock_refresh.assert_called_once_with("old-refresh")
        assert client.token is not None
        assert client.token["access_token"] == "new"
        assert not client.auth_dead.is_set()
        # Persisted to disk immediately (not just held in memory) - this
        # matters if the server rotates the refresh_token on every use.
        reloaded = IBroadcastClient()
        reloaded.load_token()
        assert reloaded.token is not None
        assert reloaded.token["access_token"] == "new"

    def test_refresh_response_without_refresh_token_keeps_the_old_one(self, token_file: Path) -> None:
        # Regression test: some OAuth servers omit refresh_token from a
        # refresh response entirely when it hasn't changed. A full replace
        # of self.token (instead of a merge) would silently drop it here,
        # breaking every subsequent refresh with a KeyError.
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() - 1, "refresh_token": "old-refresh"}
        new_token_without_refresh_token = {
            "access_token": "new",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        with patch.object(client, "refresh_token", return_value=new_token_without_refresh_token):
            client.refresh_if_necessary()

        assert client.token is not None
        assert client.token["access_token"] == "new"
        assert client.token["refresh_token"] == "old-refresh"

    def test_marks_auth_dead_on_refresh_failure(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() - 1, "refresh_token": "old-refresh"}
        with patch.object(client, "refresh_token", side_effect=OAuthError("invalid_grant", "expired")):
            client.refresh_if_necessary()

        assert client.token is None
        assert client.auth_dead.is_set()


class TestFetchLibraryTokenRefresh:
    """Regression tests: fetch_library() used to have no 401-refresh logic
    at all, unlike api_call()/upload_file() - a token that expired during
    a long upload run (sync_playlists()/sync_ratings() both call
    fetch_library() right after do_upload()) made the whole playlists/
    ratings step fail outright instead of silently refreshing."""

    def test_retries_after_refreshing_an_expired_token(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() + 3600, "access_token": "old", "token_type": "Bearer"}

        first_response = MagicMock(status_code=401, ok=False)
        second_response = MagicMock(status_code=200, ok=True)
        second_response.json.return_value = {"library": {}}

        def fake_refresh() -> None:
            client.token = {"expires_at": time.time() + 3600, "access_token": "new", "token_type": "Bearer"}

        with (
            patch(
                "ibroadcast_sync.oauth_client.requests.post",
                side_effect=[first_response, second_response],
            ) as mock_post,
            patch.object(client, "refresh_if_necessary", side_effect=fake_refresh),
            patch.object(client, "save_token"),
        ):
            result = client.fetch_library()

        assert result == {"library": {}}
        assert mock_post.call_count == 2

    def test_dead_refresh_token_raises_server_error(self, token_file: Path) -> None:
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() + 3600, "access_token": "old", "token_type": "Bearer"}

        fake_401 = MagicMock(status_code=401, ok=False)
        with (
            patch("ibroadcast_sync.oauth_client.requests.post", return_value=fake_401),
            patch.object(client, "refresh_if_necessary", side_effect=lambda: setattr(client, "token", None)),
            pytest.raises(ServerError, match="no longer valid"),
        ):
            client.fetch_library()


class TestApiCallDeadToken:
    def test_401_with_unrefreshable_token_raises_server_error_not_assertion(self, token_file: Path) -> None:
        # Regression test: api_call() used to retry unconditionally after
        # refresh_if_necessary(), even when the refresh had just failed
        # and cleared self.token to None - the retried call then hit
        # auth_header()'s `assert self.token is not None` and crashed with
        # a bare AssertionError instead of a clear, catchable ServerError.
        client = IBroadcastClient()
        client.token = {"expires_at": time.time() + 3600, "access_token": "a", "token_type": "Bearer"}

        fake_401 = MagicMock(status_code=401, ok=False)
        with (
            patch("ibroadcast_sync.oauth_client.requests.post", return_value=fake_401),
            patch.object(client, "refresh_if_necessary", side_effect=lambda: setattr(client, "token", None)),
            pytest.raises(ServerError, match="no longer valid"),
        ):
            client.api_call("status")


class TestWaitForOauthCallback:
    """Starts a real local server on a throwaway port - these are the only
    tests in the suite that touch an actual socket, deliberately, since
    this is exactly the kind of "single blocking request" logic that's
    easy to get subtly wrong (see the favicon-race regression test)."""

    URL = "http://localhost:18912/callback"

    def test_returns_code_and_state_from_the_real_callback(self) -> None:
        result: list[tuple[str | None, str | None, str | None]] = []
        thread = threading.Thread(target=lambda: result.append(wait_for_oauth_callback(self.URL, timeout=5)))
        thread.start()
        time.sleep(0.2)  # let the server start listening
        urllib.request.urlopen(f"{self.URL}?code=abc123&state=xyz789", timeout=5)
        thread.join(timeout=5)

        assert result == [("abc123", "xyz789", None)]

    def test_ignores_a_request_to_an_unrelated_path_first(self) -> None:
        # Regression test: a browser's automatic GET /favicon.ico (or any
        # other request that isn't the actual OAuth redirect) must not be
        # mistaken for the callback - it should be answered and ignored,
        # with the server continuing to wait for the real one.
        result: list[tuple[str | None, str | None, str | None]] = []
        thread = threading.Thread(target=lambda: result.append(wait_for_oauth_callback(self.URL, timeout=5)))
        thread.start()
        time.sleep(0.2)
        # urlopen() raises HTTPError for a non-2xx response - a plain 404
        # (rather than silently succeeding) is exactly what confirms the
        # stray request was rejected instead of being treated as the
        # callback.
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen("http://localhost:18912/favicon.ico", timeout=5)
        assert exc_info.value.code == 404
        time.sleep(0.1)
        urllib.request.urlopen(f"{self.URL}?code=real-code&state=real-state", timeout=5)
        thread.join(timeout=5)

        assert result == [("real-code", "real-state", None)]

    def test_times_out_if_nothing_ever_arrives(self) -> None:
        start = time.monotonic()
        result = wait_for_oauth_callback("http://localhost:18913/callback", timeout=1)
        elapsed = time.monotonic() - start

        assert result == (None, None, None)
        assert elapsed < 3  # didn't hang well past the requested timeout
