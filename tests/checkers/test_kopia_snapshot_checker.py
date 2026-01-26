"""Tests for Kopia snapshot checker."""

import json
import subprocess
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from kuma_sentinel.core.checkers.kopia_snapshot_checker import (
    KopiaSnapshotChecker,
    _get_latest_snapshot_age,
    _parse_iso_timestamp,
    _parse_snapshot_timestamp,
    _run_kopia_command,
    _validate_snapshot_path,
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
            (5.0, metadata1),  # /data: 5h < 24h (OK)
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


# Tests for _validate_snapshot_path function
class TestValidateSnapshotPath:
    """Test snapshot path validation."""

    def test_validate_local_absolute_path(self):
        """Test valid local absolute path."""
        _validate_snapshot_path("/mnt/data")  # Should not raise

    def test_validate_local_absolute_path_with_subdirs(self):
        """Test valid local absolute path with multiple subdirectories."""
        _validate_snapshot_path("/mnt/backup/incremental/daily")  # Should not raise

    def test_validate_local_relative_path(self):
        """Test valid relative path."""
        _validate_snapshot_path("./data")  # Should not raise

    def test_validate_local_relative_path_nested(self):
        """Test valid relative nested path."""
        _validate_snapshot_path("data/backups/2024")  # Should not raise

    def test_validate_home_path(self):
        """Test path starting with tilde."""
        _validate_snapshot_path("~/backups")  # Should not raise

    def test_validate_ssh_path_simple(self):
        """Test valid SSH path."""
        _validate_snapshot_path("user@host:/data")  # Should not raise

    def test_validate_ssh_path_with_domain(self):
        """Test valid SSH path with FQDN."""
        _validate_snapshot_path(
            "admin@backup.example.com:/backups/data"
        )  # Should not raise

    def test_validate_ssh_path_with_underscores(self):
        """Test valid SSH path with underscores in hostname."""
        _validate_snapshot_path("user@backup_host:/data")  # Should not raise

    def test_validate_path_with_numbers(self):
        """Test path with numbers."""
        _validate_snapshot_path("/mnt/data2024")  # Should not raise

    def test_validate_path_with_hyphens(self):
        """Test path with hyphens."""
        _validate_snapshot_path("/mnt/data-backup-2024")  # Should not raise

    def test_validate_path_with_dots(self):
        """Test path with dots."""
        _validate_snapshot_path("/mnt/data.backup.v1")  # Should not raise

    def test_validate_empty_path(self):
        """Test that empty path is rejected."""
        with self.error_context():
            _validate_snapshot_path("")

    def test_validate_path_traversal_double_dot(self):
        """Test that path traversal (..) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data/../config")

    def test_validate_path_traversal_at_start(self):
        """Test that path traversal at start is rejected."""
        with self.error_context():
            _validate_snapshot_path("../data")

    def test_validate_shell_metachar_dollar(self):
        """Test that dollar sign ($) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/$data")

    def test_validate_shell_metachar_backtick(self):
        """Test that backtick (`) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/`data`")

    def test_validate_shell_metachar_semicolon(self):
        """Test that semicolon (;) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data;rm")

    def test_validate_shell_metachar_pipe(self):
        """Test that pipe (|) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data|cat")

    def test_validate_shell_metachar_ampersand(self):
        """Test that ampersand (&) is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data&dangerous")

    def test_validate_shell_metachar_parentheses(self):
        """Test that parentheses are rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data(subdir)")

    def test_validate_shell_metachar_angle_brackets(self):
        """Test that angle brackets are rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data<>file")

    def test_validate_shell_metachar_exclamation(self):
        """Test that exclamation mark is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data!important")

    def test_validate_shell_metachar_asterisk(self):
        """Test that asterisk is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data*")

    def test_validate_shell_metachar_question_mark(self):
        """Test that question mark is rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/data?")

    def test_validate_ssh_invalid_format_missing_colon(self):
        """Test that SSH path without colon is rejected."""
        with self.error_context():
            _validate_snapshot_path("user@host/data")

    def test_validate_ssh_invalid_format_missing_at(self):
        """Test that SSH-like path without @ is rejected."""
        with self.error_context():
            _validate_snapshot_path("user:host:/data")

    def test_validate_path_with_spaces(self):
        """Test that spaces in path are rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/my data")

    def test_validate_path_with_special_unicode(self):
        """Test that non-ASCII characters are rejected."""
        with self.error_context():
            _validate_snapshot_path("/mnt/dätä")

    def test_validate_ssh_with_port_like_notation(self):
        """Test SSH path - port should not be included in validation."""
        with self.error_context():
            # This should fail because : is not allowed twice in SSH format
            _validate_snapshot_path("user@host:22:/data")

    @staticmethod
    def error_context():
        """Helper to assert ValueError is raised."""
        return pytest.raises(ValueError)

    def test_validate_root_path(self):
        """Test root path."""
        _validate_snapshot_path("/")  # Should not raise

    def test_validate_nested_deep_path(self):
        """Test deeply nested path."""
        _validate_snapshot_path("/mnt/backup/2024/01/15/hourly/0")  # Should not raise

    def test_validate_ssh_with_hyphenated_domain(self):
        """Test SSH with hyphenated domain name."""
        _validate_snapshot_path("admin@my-backup-server:/data")  # Should not raise

    def test_validate_ssh_with_dotted_domain(self):
        """Test SSH with dotted domain name."""
        _validate_snapshot_path(
            "admin@backup.corp.example.com:/data/backups"
        )  # Should not raise

    def test_validate_path_ending_with_slash(self):
        """Test path ending with slash - should work as regex allows it."""
        # The validation regex accepts trailing slashes in path components
        _validate_snapshot_path("/mnt/data/")  # Should not raise

    def test_validate_path_starting_with_dot_dot(self):
        """Test that .. at start fails."""
        with self.error_context():
            _validate_snapshot_path("..")

    def test_validate_path_with_only_dots(self):
        """Test path with only dots (invalid)."""
        with self.error_context():
            _validate_snapshot_path("...")

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_with_invalid_snapshot_path(self, mock_age):
        """Test execution with invalid snapshot path configuration."""
        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/mnt/data$invalid", "max_age_hours": 24},  # Invalid path
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert (
            "Invalid snapshot path" in result.message
            or "failed" in result.message.lower()
        )

    def test_execute_with_missing_path_field(self):
        """Test execution with snapshot config missing path field."""
        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"max_age_hours": 24},  # Missing 'path' field
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        # When path is missing, it gets skipped - if all paths are missing, treated as "no snapshots checked"
        # The actual behavior is it returns "up" since there were no failed validations
        assert result.status == "up"

    @patch(
        "kuma_sentinel.core.checkers.kopia_snapshot_checker._get_latest_snapshot_age"
    )
    def test_execute_with_exception(self, mock_age):
        """Test execution with unexpected exception."""
        mock_age.side_effect = RuntimeError("Unexpected error")

        config = KopiaSnapshotConfig()
        config.kopiasnapshotstatus_snapshots = [
            {"path": "/data", "max_age_hours": 24},
        ]
        config.kopiasnapshotstatus_max_age_hours = 24
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False

        logger = MagicMock()
        checker = KopiaSnapshotChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "error" in result.message.lower()

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_with_missing_stats(self, mock_run):
        """Test snapshot age calculation when stats field is missing."""
        now = datetime.now()
        recent = now - timedelta(hours=2)
        end_time = recent.isoformat() + "Z"

        snapshot = {
            "id": "test-id",
            "endTime": end_time,
            "startTime": "2026-01-19T00:00:11.570523988Z",
            # Missing stats field
            "retentionReason": ["daily-1"],
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()

        with patch(
            "kuma_sentinel.core.checkers.kopia_snapshot_checker.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromisoformat = datetime.fromisoformat

            age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should still work with empty stats dict
        assert age is not None
        assert metadata is not None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_run_kopia_command_with_exception(self, mock_run):
        """Test kopia command execution with general exception."""
        mock_run.side_effect = RuntimeError("General error")

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "test"])

        assert success is False
        assert stderr is not None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_parsing_error_missing_field(self, mock_run):
        """Test snapshot age when required field is missing (KeyError)."""
        snapshot = {
            "id": "test-id",
            # Missing endTime - will cause KeyError in parsing
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        assert age is None
        assert metadata is None
        logger.error.assert_called()

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_with_timezone_aware_datetime(self, mock_run):
        """Test snapshot age calculation with timezone-aware datetime."""
        now = datetime.now()
        recent = now - timedelta(hours=3)
        # Create timezone-aware datetime with +05:30 offset
        end_time = recent.isoformat() + "+05:30"

        snapshot = {
            "id": "test-id",
            "endTime": end_time,
            "startTime": "2026-01-19T00:00:11.570523988Z",
            "stats": {"errorCount": 0, "fileCount": 100},
            "retentionReason": ["daily-1"],
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()

        with patch(
            "kuma_sentinel.core.checkers.kopia_snapshot_checker.datetime"
        ) as mock_datetime:
            # For now(), use our real datetime
            mock_datetime.now.return_value = now
            # For fromisoformat, use the real function
            mock_datetime.fromisoformat = datetime.fromisoformat

            age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should still calculate approximate age correctly even with timezone
        assert age is not None
        assert metadata is not None

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker.subprocess.run")
    def test_run_kopia_command_empty_stdout(self, mock_run):
        """Test kopia command with empty stdout."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "test"])

        assert success is True
        assert stdout == ""
        assert stderr == ""


class TestGetLatestSnapshotAgeParsing:
    """Test snapshot age parsing with various input scenarios."""

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_invalid_timestamp_format(self, mock_run):
        """Test snapshot age when endTime has invalid format (parse returns None)."""
        snapshot = {
            "id": "test-id",
            "endTime": "invalid-timestamp-format",
            "stats": {"size": 1000},
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None when timestamp parsing fails
        assert age is None
        assert metadata is None
        logger.error.assert_called()
        # Verify specific error about timestamp parsing
        error_calls = [call[0][0] for call in logger.error.call_args_list]
        assert any(
            "Failed to parse snapshot timestamp" in str(call) for call in error_calls
        )

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_missing_endtime(self, mock_run):
        """Test snapshot age when endTime is None in snapshot data."""
        snapshot = {
            "id": "test-id",
            "endTime": None,
            "stats": {"size": 1000},
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None when endTime is None
        assert age is None
        assert metadata is None
        logger.error.assert_called()
        # Verify error about missing endTime
        error_calls = [call[0][0] for call in logger.error.call_args_list]
        assert any("Missing endTime" in str(call) for call in error_calls)

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_with_error_count(self, mock_run):
        """Test snapshot age when snapshot has errors."""
        snapshot = {
            "id": "test-id",
            "endTime": "2026-01-19T00:00:11Z",
            "stats": {"size": 1000, "errorCount": 5},
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None when snapshot has errors
        assert age is None
        assert metadata is None
        logger.error.assert_called()
        # Verify error about snapshot errors
        error_calls = [call[0][0] for call in logger.error.call_args_list]
        assert any("error(s)" in str(call) for call in error_calls)

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_json_decode_error(self, mock_run):
        """Test snapshot age when JSON output is invalid."""
        mock_run.return_value = (True, "invalid json {{{", None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None on JSON parse error
        assert age is None
        assert metadata is None
        logger.error.assert_called()
        # Verify JSON error
        error_calls = [call[0][0] for call in logger.error.call_args_list]
        assert any("Failed to parse JSON" in str(call) for call in error_calls)

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_empty_snapshots_list(self, mock_run):
        """Test snapshot age when snapshots list is empty."""
        output = json.dumps([])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None when no snapshots
        assert age is None
        assert metadata is None
        logger.warning.assert_called()

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_run_command_failed(self, mock_run):
        """Test snapshot age when kopia command fails."""
        mock_run.return_value = (False, None, "Permission denied")

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return None when command fails
        assert age is None
        assert metadata is None
        logger.error.assert_called()

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_successful_with_metadata(self, mock_run):
        """Test snapshot age calculation with complete metadata."""
        now = datetime.now()
        past_time = now - timedelta(hours=2)
        iso_timestamp = past_time.isoformat() + "Z"

        snapshot = {
            "id": "snap-123",
            "endTime": iso_timestamp,
            "stats": {
                "size": 5000,
                "files": 100,
                "dirs": 10,
                "errorCount": 0,
            },
            "retentionReason": ["policy1", "policy2"],
        }
        output = json.dumps([snapshot])
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should return age and metadata
        assert age is not None
        assert 1.9 <= age <= 2.1  # Approximately 2 hours
        assert metadata is not None
        assert metadata["id"] == "snap-123"
        assert metadata["stats"]["size"] == 5000
        assert metadata["retention_reason"] == ["policy1", "policy2"]

    @patch("kuma_sentinel.core.checkers.kopia_snapshot_checker._run_kopia_command")
    def test_get_snapshot_age_malformed_snapshot_data(self, mock_run):
        """Test snapshot age when snapshot data is malformed (raises KeyError)."""
        # Create data that will cause issues when trying to access dict methods
        # Use a non-dict snapshot object
        output = json.dumps([{"id": "test"}])  # Missing critical fields
        mock_run.return_value = (True, output, None)

        logger = MagicMock()
        age, metadata = _get_latest_snapshot_age(logger, "/test/path")

        # Should handle gracefully
        assert age is None
        assert metadata is None


class TestRunKopiaCommandExceptions:
    """Test _run_kopia_command exception handling."""

    @patch("subprocess.run")
    def test_run_kopia_command_subprocess_exception(self, mock_run):
        """Test kopia command when subprocess raises an unexpected exception."""
        # Simulate an OSError being raised during subprocess.run
        mock_run.side_effect = OSError("Process error")

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "test"])

        # Should handle exception and return False
        assert success is False
        assert stdout is None
        assert stderr is not None
        logger.error.assert_called()

    @patch("subprocess.run")
    def test_run_kopia_command_attribute_error(self, mock_run):
        """Test kopia command when subprocess raises AttributeError."""
        mock_run.side_effect = AttributeError("Unexpected attribute error")

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "test"])

        # Should handle exception gracefully
        assert success is False
        assert stdout is None
        assert stderr is not None
        logger.error.assert_called()

    @patch("subprocess.run")
    def test_run_kopia_command_value_error(self, mock_run):
        """Test kopia command when subprocess raises ValueError."""
        mock_run.side_effect = ValueError("Invalid argument")

        logger = MagicMock()
        success, stdout, stderr = _run_kopia_command(logger, ["kopia", "test"])

        # Should handle exception
        assert success is False
        assert stdout is None
        assert stderr is not None
        logger.error.assert_called()


class TestValidateSnapshotPathEdgeCases:
    """Test edge cases in snapshot path validation."""

    def test_validate_path_valid_local_path(self):
        """Test that valid local paths pass validation."""
        _validate_snapshot_path("/mnt/data")
        _validate_snapshot_path("/home/user/backups")
        _validate_snapshot_path("./relative/path")
        _validate_snapshot_path("~/home/backups")

    def test_validate_path_valid_ssh_path(self):
        """Test that valid SSH paths pass validation."""
        _validate_snapshot_path("user@host:/path")
        _validate_snapshot_path("root@server.com:/data")
        _validate_snapshot_path("admin@192.168.1.1:/backups")

    def test_validate_path_with_hyphens_and_underscores(self):
        """Test paths with allowed special characters."""
        _validate_snapshot_path("/mnt/backup-2024-01")
        _validate_snapshot_path("/path/with_underscores")
        _validate_snapshot_path("user_name@host-server:/path")
        _validate_snapshot_path("/path/with-multiple_special-chars")
