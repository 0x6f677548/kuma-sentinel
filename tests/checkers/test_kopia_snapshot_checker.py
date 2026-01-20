"""Tests for Kopia snapshot checker."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from kuma_sentinel.core.checkers.kopia_snapshot_checker import (
    KopiaSnapshotChecker,
    _get_latest_snapshot_age,
    _parse_iso_timestamp,
    _parse_snapshot_timestamp,
    _run_kopia_command,
)
from kuma_sentinel.core.config.kopia_snapshot_config import KopiaSnapshotConfig
from kuma_sentinel.core.models import CheckResult


class TestParseSnapshotTimestamp:
    """Test timestamp parsing from kopia output."""

    def test_parse_valid_timestamp(self):
        """Test parsing valid timestamp."""
        line = "2024-01-15 10:30:45 k7a4d2b1c root@host /data"
        result = _parse_snapshot_timestamp(line)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45

    def test_parse_timestamp_with_leading_whitespace(self):
        """Test parsing timestamp with leading whitespace."""
        line = "  2024-01-15 10:30:45 k7a4d2b1c root@host /data"
        result = _parse_snapshot_timestamp(line)

        assert result is not None
        assert result.year == 2024

    def test_parse_invalid_timestamp_format(self):
        """Test parsing invalid timestamp format."""
        line = "invalid timestamp data"
        result = _parse_snapshot_timestamp(line)

        assert result is None

    def test_parse_empty_line(self):
        """Test parsing empty line."""
        result = _parse_snapshot_timestamp("")

        assert result is None

    def test_parse_timestamp_edge_cases(self):
        """Test parsing edge case timestamps."""
        # Test different valid dates
        line = "2024-12-31 23:59:59 snapshot"
        result = _parse_snapshot_timestamp(line)

        assert result is not None
        assert result.month == 12
        assert result.day == 31


class TestParseIsoTimestamp:
    """Test ISO 8601 timestamp parsing from JSON."""

    def test_parse_valid_iso_timestamp_with_z(self):
        """Test parsing valid ISO timestamp with Z suffix."""
        timestamp = "2026-01-19T00:00:11.570523988Z"
        result = _parse_iso_timestamp(timestamp)

        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 19
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_valid_iso_timestamp_with_offset(self):
        """Test parsing valid ISO timestamp with timezone offset."""
        timestamp = "2026-01-19T00:00:11.570523988+00:00"
        result = _parse_iso_timestamp(timestamp)

        assert result is not None
        assert result.year == 2026

    def test_parse_invalid_iso_timestamp(self):
        """Test parsing invalid ISO timestamp."""
        result = _parse_iso_timestamp("not-a-timestamp")

        assert result is None

    def test_parse_empty_timestamp(self):
        """Test parsing empty timestamp."""
        result = _parse_iso_timestamp("")

        assert result is None

    def test_parse_iso_timestamp_nanoseconds(self):
        """Test parsing ISO timestamp with nanoseconds."""
        timestamp = "2026-01-19T00:00:18.029727037Z"
        result = _parse_iso_timestamp(timestamp)

        assert result is not None
        assert result.microsecond > 0


class TestRunKopiaCommand:
    """Test kopia command execution."""

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker.subprocess.run")
    def test_successful_command(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr="",
        )

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "version"])

        assert success is True
        assert stdout == "output"
        assert stderr == ""

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker.subprocess.run")
    def test_failed_command(self, mock_run):
        """Test failed command execution."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message",
        )

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "bad"])

        assert success is False

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker.subprocess.run")
    def test_command_timeout(self, mock_run):
        """Test command timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "slow"])

        assert success is False
        assert stderr == "Command timed out"


class TestGetLatestSnapshotAge:
    """Test snapshot age calculation from JSON response."""

    @staticmethod
    def create_json_snapshot(end_time: str, snapshot_id: str = "test-id") -> dict:
        """Helper to create a mock snapshot JSON object."""
        return {
            "id": snapshot_id,
            "source": {
                "host": "fileserver",
                "userName": "root",
                "path": "/test/path",
            },
            "endTime": end_time,
            "startTime": "2026-01-19T00:00:11.570523988Z",
            "stats": {
                "totalSize": 49613972190,
                "fileCount": 20291,
                "cachedFiles": 20291,
                "nonCachedFiles": 0,
                "dirCount": 4657,
                "errorCount": 0,
            },
            "retentionReason": ["latest-1", "daily-1"],
        }

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_fresh_snapshot_age(self, mock_run):
        """Test getting age of fresh snapshot from JSON."""
        now = datetime.now()
        recent = now - timedelta(hours=2)
        end_time = recent.isoformat() + "Z"

        snapshot = self.create_json_snapshot(end_time)
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()

        with patch(
            "kuma_sentinel.core.checkers.kopia_snapshot_checker.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat

            age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is not None
        assert 1.9 < age < 2.1  # Should be approximately 2 hours
        assert metadata is not None
        assert metadata["id"] == "test-id"
        assert metadata["stats"]["fileCount"] == 20291
        assert "daily-1" in metadata["retention_reason"]

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_no_snapshots(self, mock_run):
        """Test when no snapshots exist."""
        output = json.dumps([])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is None
        assert metadata is None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_command_failed(self, mock_run):
        """Test when kopia command fails."""
        mock_run.return_value = (False, None, "Connection refused")

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is None
        assert metadata is None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_malformed_json(self, mock_run):
        """Test when JSON is malformed."""
        mock_run.return_value = (True, "not valid json", None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is None
        assert metadata is None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_missing_end_time(self, mock_run):
        """Test when snapshot is missing endTime field."""
        snapshot = self.create_json_snapshot("2026-01-19T00:00:11.570523988Z")
        del snapshot["endTime"]
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is None
        assert metadata is None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_single_object_response(self, mock_run):
        """Test when kopia returns a single object instead of array."""
        now = datetime.now()
        recent = now - timedelta(hours=1)
        end_time = recent.isoformat() + "Z"

        snapshot = self.create_json_snapshot(end_time)
        output = json.dumps(snapshot)  # Single object, not array
        mock_run.return_value = (True, output, None)

        logger = MagicMock()

        with patch(
            "kuma_sentinel.core.checkers.kopia_snapshot_checker.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat

            age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is not None
        assert 0.9 < age < 1.1  # Should be approximately 1 hour
        assert metadata is not None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_with_errors(self, mock_run):
        """Test when snapshot has errors (errorCount > 0)."""
        now = datetime.now()
        recent = now - timedelta(hours=1)
        end_time = recent.isoformat() + "Z"

        snapshot = self.create_json_snapshot(end_time)
        snapshot["stats"]["errorCount"] = 5  # Set error count > 0

        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should treat snapshot with errors as failed
        assert age is None
        assert metadata is None
        # Verify error was logged
        logger.error.assert_called()

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_command_includes_all_flag(self, mock_run):
        """Test that the command includes --all flag to see snapshots from all users."""
        now = datetime.now()
        recent = now - timedelta(hours=1)
        end_time = recent.isoformat() + "Z"

        snapshot = self.create_json_snapshot(end_time)
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Verify the command includes --all flag
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][1]
        assert "--all" in cmd
        assert "--json" in cmd
        assert "/test/path" in cmd


class TestKopiaSnapshotChecker:
    """Test KopiaSnapshotChecker class."""

    @staticmethod
    def create_metadata() -> dict:
        """Helper to create mock metadata."""
        return {
            "id": "test-snapshot-id",
            "stats": {
                "totalSize": 49613972190,
                "fileCount": 20291,
            },
            "retention_reason": ["daily-1"],
        }

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_all_fresh(self, mock_age):
        """Test execution when all snapshots are fresh."""
        metadata1 = self.create_metadata()
        metadata2 = self.create_metadata()
        mock_age.side_effect = [
            (5.0, metadata1),
            (12.0, metadata2),
        ]  # Two fresh snapshots

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups", "max_age_hours": 24},
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert "All snapshots fresh" in result.message
        assert result.details["snapshots"]["/data"]["age_hours"] == 5.0
        assert result.details["snapshots"]["/backups"]["age_hours"] == 12.0

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_snapshot_too_old(self, mock_age):
        """Test execution when snapshot is too old."""
        metadata1 = self.create_metadata()
        mock_age.side_effect = [
            (5.0, metadata1),
            (48.0, self.create_metadata()),
        ]  # Second is too old

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups", "max_age_hours": 24},
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "too old" in result.message.lower()

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_per_path_max_age_hours(self, mock_age):
        """Test execution with per-path max_age_hours thresholds."""
        metadata1 = self.create_metadata()
        metadata2 = self.create_metadata()
        mock_age.side_effect = [
            (5.0, metadata1),   # /data: 5h < 24h (OK)
            (30.0, metadata2),  # /backups: 30h < 48h (OK, using per-path threshold)
        ]

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups", "max_age_hours": 48},
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert "All snapshots fresh" in result.message
        assert result.details["snapshots"]["/data"]["age_hours"] == 5.0
        assert result.details["snapshots"]["/backups"]["age_hours"] == 30.0

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_per_path_max_age_hours_fallback_to_default(self, mock_age):
        """Test execution using default max_age_hours for paths without explicit threshold."""
        metadata1 = self.create_metadata()
        metadata2 = self.create_metadata()
        mock_age.side_effect = [
            (5.0, metadata1),
            (12.0, metadata2),
        ]

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups"},  # No explicit max_age_hours, should use default
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert result.details["snapshots"]["/backups"]["age_hours"] == 12.0

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_snapshot_missing(self, mock_age):
        """Test execution when snapshot cannot be retrieved."""
        metadata1 = self.create_metadata()
        mock_age.side_effect = [(5.0, metadata1), (None, None)]  # Second fails

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups", "max_age_hours": 24},
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "failed" in result.message.lower()

    def test_execute_no_paths_configured(self):
        """Test execution with no snapshots configured."""
        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = []
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "no snapshots" in result.message.lower()

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_result_has_required_fields(self, mock_age):
        """Test result has all required fields."""
        metadata = self.create_metadata()
        mock_age.return_value = (10.0, metadata)

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [{"path": "/data", "max_age_hours": 24}]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert isinstance(result, CheckResult)
        assert result.check_name == "kopiasnapshotstatus"
        assert result.status in ["up", "down"]
        assert result.message is not None
        assert result.duration_seconds >= 0
        assert result.details is not None
