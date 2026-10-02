"""Tests for ibroadcast_sync.cli's argparse setup.

The interactive wizard isn't covered here (needs stdin mocking that isn't
worth the complexity for a personal utility) - this focuses on flag
parsing/validation and the two orchestration decisions in main() that are
cheap to verify without a real client: --dump-playlists needing no
credentials, and CLIENT_ID being checked at the right point.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from ibroadcast_sync import cli
from ibroadcast_sync.cli import build_parser


class TestBuildParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.source_dir is None
        assert args.no_upload is False
        assert args.no_playlists is False
        assert args.workers == 4
        assert args.dry_run is False
        assert args.sync_ratings is False
        assert args.dump_library is False
        assert args.dump_playlists is False

    def test_dry_run_flag(self) -> None:
        args = build_parser().parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_source_dir(self) -> None:
        args = build_parser().parse_args(["--source-dir", "/music"])
        assert args.source_dir == "/music"

    def test_workers_is_an_int(self) -> None:
        args = build_parser().parse_args(["--workers", "8"])
        assert args.workers == 8

    def test_no_upload_and_no_playlists_together(self) -> None:
        args = build_parser().parse_args(["--no-upload", "--no-playlists"])
        assert args.no_upload is True
        assert args.no_playlists is True

    def test_sync_ratings_flag(self) -> None:
        args = build_parser().parse_args(["--sync-ratings"])
        assert args.sync_ratings is True

    @pytest.mark.parametrize("value", ["0", "-1", "-5"])
    def test_workers_rejects_non_positive_values(self, value: str, capsys: pytest.CaptureFixture) -> None:
        # Regression test: these used to parse "successfully" and only
        # crash later with a raw ThreadPoolExecutor ValueError; argparse
        # should now reject them upfront with a clean error instead.
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--workers", value])
        assert "positive integer" in capsys.readouterr().err

    def test_workers_rejects_non_integer(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--workers", "four"])


class TestDumpPlaylistsDoesNotRequireClientId:
    def test_dump_playlists_runs_without_a_configured_client_id(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        # Regression test: --dump-playlists never touches the iBroadcast
        # API, but used to be blocked by the "CLIENT_ID not configured"
        # check anyway - contradicting the README, which has people try
        # this command before setting up credentials.
        monkeypatch.setattr(cli, "CLIENT_ID", "REPLACE_WITH_YOUR_CLIENT_ID")
        monkeypatch.setattr("sys.argv", ["ibroadcast-sync", "--dump-playlists"])
        fake_playlists = MagicMock(return_value=[{"name": "Test", "tracks": []}])
        monkeypatch.setattr(cli, "get_music_app_playlists", fake_playlists)
        mock_client_class = MagicMock()
        monkeypatch.setattr(cli, "IBroadcastClient", mock_client_class)

        cli.main()

        fake_playlists.assert_called_once()
        mock_client_class.assert_not_called()  # never even tried to authenticate
        assert "Test" in capsys.readouterr().out


class TestDeadAuthStopsRun:
    def test_exits_after_upload_aborts_for_dead_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "CLIENT_ID", "configured-client-id")
        monkeypatch.setattr("sys.argv", ["ibroadcast-sync", "--sync-ratings"])
        client = MagicMock()
        client.login.return_value = True
        client.auth_dead = threading.Event()
        monkeypatch.setattr(cli, "IBroadcastClient", lambda: client)

        def abort_upload(*_args: object, **_kwargs: object) -> None:
            client.auth_dead.set()

        monkeypatch.setattr(cli, "do_upload", abort_upload)
        mock_playlists = MagicMock()
        mock_ratings = MagicMock()
        monkeypatch.setattr(cli, "sync_playlists", mock_playlists)
        monkeypatch.setattr(cli, "sync_ratings", mock_ratings)

        with pytest.raises(SystemExit) as exc_info:
            cli.main()

        assert exc_info.value.code == 1
        mock_playlists.assert_not_called()
        mock_ratings.assert_not_called()

    def test_returns_error_status_if_ratings_loses_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "CLIENT_ID", "configured-client-id")
        monkeypatch.setattr(
            "sys.argv", ["ibroadcast-sync", "--no-upload", "--no-playlists", "--sync-ratings"]
        )
        client = MagicMock()
        client.login.return_value = True
        client.auth_dead = threading.Event()
        monkeypatch.setattr(cli, "IBroadcastClient", lambda: client)

        def lose_auth(*_args: object, **_kwargs: object) -> None:
            client.auth_dead.set()

        monkeypatch.setattr(cli, "sync_ratings", lose_auth)

        with pytest.raises(SystemExit) as exc_info:
            cli.main()

        assert exc_info.value.code == 1
