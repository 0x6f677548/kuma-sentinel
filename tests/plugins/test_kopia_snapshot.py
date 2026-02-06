"""Tests for kopia_snapshot plugin."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest

from kuma_scout.plugins.kopia_snapshot import KopiaSnapshotConfig, KopiaSnapshotPlugin
from kuma_scout.plugins.models import GlobalConfig, LoggingConfig, UptimeKumaConfig


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma=UptimeKumaConfig(
            url="http://localhost:3001/api/push", token="global-token"
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def plugin(global_config):
    """Create kopia_snapshot plugin instance."""
    return KopiaSnapshotPlugin(global_config=global_config)


@pytest.fixture
def config():
    """Create basic kopia snapshot config."""
    return KopiaSnapshotConfig(
        name="test-snapshot",
        path="user@host:/path/to/repo",
        max_age_hours=24,
    )


class TestKopiaSnapshotExecution:
    """Test kopia snapshot plugin execution."""

    def test_recent_snapshot_success(self, plugin, config):
        """Test successful check with recent snapshot."""
        # Use a time 1 hour ago to ensure it's within 24h max_age
        recent_time = (
            (datetime.now(timezone.utc) - timedelta(hours=1))
            .isoformat()
            .replace("+00:00", "Z")
        )
        mock_output: list[dict[str, Any]] = [
            {
                "startTime": recent_time,
                "endTime": recent_time,
                "rootEntry": {"name": "test"},
            }
        ]

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, json.dumps(mock_output), "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "Snapshot is fresh" in result.message

    def test_old_snapshot_failure(self, plugin, config):
        """Test failure with old snapshot."""
        # Set max_age to 1 hour, snapshot is 2 hours old
        config.max_age_hours = 1
        mock_output: list[dict[str, Any]] = [
            {
                "startTime": "2024-01-01T10:00:00Z",  # 2 hours ago
                "endTime": "2024-01-01T10:05:00Z",
                "rootEntry": {"name": "test"},
            }
        ]

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, json.dumps(mock_output), "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Snapshot is too old" in result.message

    def test_no_snapshots_failure(self, plugin, config):
        """Test failure when no snapshots exist."""
        mock_output: list[dict[str, Any]] = []

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, json.dumps(mock_output), "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get snapshot info" in result.message

    def test_command_execution_error(self, plugin, config):
        """Test handling of command execution errors."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.side_effect = Exception("Command failed")

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Snapshot check error" in result.message

    def test_invalid_json_response(self, plugin, config):
        """Test handling of invalid JSON response."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "invalid json", "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get snapshot info" in result.message
