"""Tests for CheckResult model."""

import pytest

from kuma_sentinel.core.models import CheckResult


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_check_result_valid_up_status(self):
        """Test creating CheckResult with 'up' status."""
        result = CheckResult(
            check_name="portscan",
            status="up",
            message="All ports responsive",
            duration_seconds=5,
        )

        assert result.check_name == "portscan"
        assert result.status == "up"
        assert result.message == "All ports responsive"
        assert result.duration_seconds == 5
        assert result.details == {}

    def test_check_result_valid_down_status(self):
        """Test creating CheckResult with 'down' status."""
        result = CheckResult(
            check_name="kopia_snapshot",
            status="down",
            message="Snapshot failed",
            duration_seconds=10,
        )

        assert result.status == "down"

    def test_check_result_invalid_status_raises_error(self):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            CheckResult(
                check_name="test", status="invalid", message="Test", duration_seconds=5
            )

        assert "Status must be 'up' or 'down'" in str(exc_info.value)

    def test_check_result_with_custom_details(self):
        """Test CheckResult with custom details."""
        details = {"ports": [80, 443], "response_time": 0.5}
        result = CheckResult(
            check_name="portscan",
            status="up",
            message="Ports responding",
            duration_seconds=2,
            details=details,
        )

        assert result.details == details
        assert result.details["ports"] == [80, 443]

    def test_check_result_post_init_validates_status(self):
        """Test __post_init__ validates status field."""
        invalid_statuses = ["UP", "DOWN", "ok", "fail", "pending", ""]

        for invalid_status in invalid_statuses:
            with pytest.raises(ValueError):
                CheckResult(
                    check_name="test",
                    status=invalid_status,
                    message="test",
                    duration_seconds=1,
                )

    def test_check_result_zero_duration(self):
        """Test CheckResult with zero duration."""
        result = CheckResult(
            check_name="quick_check",
            status="up",
            message="Quick check",
            duration_seconds=0,
        )

        assert result.duration_seconds == 0

    def test_check_result_large_duration(self):
        """Test CheckResult with large duration."""
        result = CheckResult(
            check_name="long_check",
            status="up",
            message="Long check",
            duration_seconds=3600,
        )

        assert result.duration_seconds == 3600

    def test_check_result_unicode_message(self):
        """Test CheckResult with unicode in message."""
        result = CheckResult(
            check_name="test",
            status="up",
            message="✅ Check passed successfully",
            duration_seconds=1,
        )

        assert "✅" in result.message

    def test_check_result_empty_details(self):
        """Test CheckResult with explicitly empty details."""
        result = CheckResult(
            check_name="test",
            status="up",
            message="test",
            duration_seconds=1,
            details={},
        )

        assert result.details == {}

    def test_check_result_complex_details(self):
        """Test CheckResult with nested complex details."""
        details = {
            "hosts": [
                {"ip": "192.168.1.1", "ports": [80, 443]},
                {"ip": "192.168.1.2", "ports": [22, 3389]},
            ],
            "summary": {"total_hosts": 2, "responsive": 2, "failed": 0},
        }
        result = CheckResult(
            check_name="portscan",
            status="up",
            message="All hosts responsive",
            duration_seconds=5,
            details=details,
        )

        assert len(result.details["hosts"]) == 2
        assert result.details["summary"]["responsive"] == 2
