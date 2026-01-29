"""Tests for kopiasnapshotstatus command."""

from unittest.mock import patch

from typer.testing import CliRunner

from kuma_scout.cli.app import app

runner = CliRunner()


@patch("kuma_scout.cli.commands.executor.CommandExecutor.execute_with_orchestration")
def test_kopiasnapshotstatus_snapshot_parsing(mock_execute):
    """Test kopiasnapshotstatus command snapshot argument parsing."""
    # Mock the execution to avoid running the checker
    mock_execute.return_value = None

    # Test with valid snapshot arguments
    result = runner.invoke(
        app,
        [
            "kopiasnapshotstatus",
            "--snapshot",
            "/data,24",
            "--snapshot",
            "/backups",
            "--max-age-hours",
            "48",
            "--uptime-kuma-url",
            "http://test",
            "--heartbeat-token",
            "test",
            "--token",
            "test",
        ],
    )
    assert result.exit_code == 0
    # Check that execute was called with correct args
    mock_execute.assert_called_once()
    args = mock_execute.call_args[0][0]
    assert args["snapshots"] == [("/data", 24), ("/backups", 48)]


@patch("kuma_scout.cli.commands.executor.CommandExecutor.execute_with_orchestration")
def test_kopiasnapshotstatus_invalid_snapshot_parsing(mock_execute):
    """Test kopiasnapshotstatus command with invalid snapshot arguments."""
    result = runner.invoke(
        app,
        [
            "kopiasnapshotstatus",
            "--snapshot",
            "invalid,format,extra",
            "--uptime-kuma-url",
            "http://test",
            "--heartbeat-token",
            "test",
            "--token",
            "test",
        ],
    )
    assert result.exit_code == 1
    assert "Error parsing snapshot arguments" in result.output
    # execute should not be called
    mock_execute.assert_not_called()


@patch("kuma_scout.cli.commands.executor.CommandExecutor.execute_with_orchestration")
def test_kopiasnapshotstatus_ssh_snapshot(mock_execute):
    """Test kopiasnapshotstatus command with SSH snapshot."""
    mock_execute.return_value = None

    result = runner.invoke(
        app,
        [
            "kopiasnapshotstatus",
            "--snapshot",
            "user@host:/path,12",
            "--uptime-kuma-url",
            "http://test",
            "--heartbeat-token",
            "test",
            "--token",
            "test",
        ],
    )
    assert result.exit_code == 0
    args = mock_execute.call_args[0][0]
    assert args["snapshots"] == [("user@host:/path", 12)]
