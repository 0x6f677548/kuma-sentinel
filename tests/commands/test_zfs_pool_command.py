"""Tests for zfspoolstatus command."""

from unittest.mock import patch

from typer.testing import CliRunner

from kuma_scout.cli.app import app

runner = CliRunner()


@patch("kuma_scout.cli.commands.executor.CommandExecutor.execute_with_orchestration")
def test_zfspoolstatus_pool_parsing(mock_execute):
    """Test zfspoolstatus command pool argument parsing."""
    mock_execute.return_value = None

    result = runner.invoke(
        app,
        [
            "zfspoolstatus",
            "--pool",
            "tank,20",
            "--pool",
            "backup",
            "--min-free-percent",
            "15",
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
    assert args["pools"] == [("tank", 20), ("backup", 15)]


@patch("kuma_scout.cli.commands.executor.CommandExecutor.execute_with_orchestration")
def test_zfspoolstatus_invalid_pool_parsing(mock_execute):
    """Test zfspoolstatus command with invalid pool arguments."""
    result = runner.invoke(
        app,
        [
            "zfspoolstatus",
            "--pool",
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
    assert "Error parsing pool arguments" in result.output
    mock_execute.assert_not_called()
