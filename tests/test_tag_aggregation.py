"""Tests for tag-based result aggregation functionality."""

from unittest.mock import MagicMock, patch

from kuma_scout.cli.generator import CLIGenerator
from kuma_scout.core.models import CheckResult
from kuma_scout.plugins.models import GlobalConfig, TagConfig, UptimeKumaConfig


def mock_logger():
    """Create a mock logger for testing."""
    return MagicMock()


class TestAggregationLogic:
    """Test aggregation computation logic."""

    def test_compute_aggregated_result_all_up(self):
        """Test aggregation when all checks are up."""
        gen = CLIGenerator()
        results = [
            CheckResult(
                check_name="check1", status="up", message="OK", duration_seconds=5
            ),
            CheckResult(
                check_name="check2", status="up", message="OK", duration_seconds=3
            ),
        ]

        status, message, duration_ms = gen._compute_aggregated_result(
            results, "test-tag"
        )

        assert status == "up"
        assert "2/2 healthy" in message
        assert "UP: 'check1', 'check2'" in message
        assert duration_ms == 8000  # 5 + 3 seconds

    def test_compute_aggregated_result_any_down(self):
        """Test aggregation when any check is down."""
        gen = CLIGenerator()
        results = [
            CheckResult(
                check_name="check1", status="up", message="OK", duration_seconds=5
            ),
            CheckResult(
                check_name="check2", status="down", message="Failed", duration_seconds=2
            ),
            CheckResult(
                check_name="check3", status="up", message="OK", duration_seconds=3
            ),
        ]

        status, message, duration_ms = gen._compute_aggregated_result(
            results, "test-tag"
        )

        assert status == "down"
        assert "2/3 healthy" in message
        assert "UP: 'check1', 'check3'" in message
        assert "DOWN: 'check2'" in message
        assert duration_ms == 10000  # 5 + 2 + 3 seconds

    def test_compute_aggregated_result_all_down(self):
        """Test aggregation when all checks are down."""
        gen = CLIGenerator()
        results = [
            CheckResult(
                check_name="check1", status="down", message="Failed", duration_seconds=1
            ),
            CheckResult(
                check_name="check2", status="down", message="Failed", duration_seconds=1
            ),
        ]

        status, message, duration_ms = gen._compute_aggregated_result(
            results, "test-tag"
        )

        assert status == "down"
        assert "0/2 healthy" in message
        assert duration_ms == 2000

    def test_compute_aggregated_result_no_checks(self):
        """Test aggregation with empty result list."""
        gen = CLIGenerator()
        results: list[CheckResult] = []

        status, message, duration_ms = gen._compute_aggregated_result(results, "tag")

        assert status == "up"
        assert "no checks executed" in message
        assert duration_ms == 0

    def test_compute_aggregated_result_single_check(self):
        """Test aggregation with single check."""
        gen = CLIGenerator()
        results = [
            CheckResult(
                check_name="only-check",
                status="down",
                message="Failed",
                duration_seconds=10,
            )
        ]

        status, message, duration_ms = gen._compute_aggregated_result(results, "tag")

        assert status == "down"
        assert "0/1 healthy" in message
        assert "DOWN: 'only-check'" in message
        assert duration_ms == 10000


class TestSendAggregatedResults:
    """Test sending aggregated results to Uptime Kuma."""

    def test_send_aggregated_results_no_tags_requested(self):
        """Test that nothing is sent when no tags are requested."""
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig()
        results_by_tag: dict[str, list[CheckResult]] = {"tag1": []}

        with patch("kuma_scout.cli.generator.send_push") as mock_send:
            gen._send_aggregated_results(results_by_tag, None, global_config, logger)
            mock_send.assert_not_called()

    def test_send_aggregated_results_no_tag_config(self):
        """Test when tags are requested but specific tag config doesn't exist."""
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test"),
            tags={"other-tag": TagConfig(token="other-token")},
        )
        results_by_tag: dict[str, list[CheckResult]] = {"tag1": []}

        with patch("kuma_scout.cli.generator.send_push") as mock_send:
            gen._send_aggregated_results(
                results_by_tag, ["tag1"], global_config, logger
            )
            mock_send.assert_not_called()
            logger.warning.assert_called()

    def test_send_aggregated_results_success(self):
        """Test successful aggregation and reporting."""
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test"),
            tags={
                "network": TagConfig(token="network-token"),
                "backup": TagConfig(token="backup-token"),
            },
        )

        results_by_tag: dict[str, list[CheckResult]] = {
            "network": [
                CheckResult(
                    check_name="check1", status="up", message="OK", duration_seconds=5
                ),
                CheckResult(
                    check_name="check2", status="up", message="OK", duration_seconds=3
                ),
            ],
            "backup": [
                CheckResult(
                    check_name="backup1",
                    status="down",
                    message="Failed",
                    duration_seconds=2,
                ),
            ],
        }

        with patch(
            "kuma_scout.cli.generator.send_push", return_value=True
        ) as mock_send:
            gen._send_aggregated_results(
                results_by_tag, ["network", "backup"], global_config, logger
            )

            # Verify send_push called twice (once per tag)
            assert mock_send.call_count == 2

            # Verify network tag call
            network_call = [
                call
                for call in mock_send.call_args_list
                if call[1]["push_token"] == "network-token"
            ]
            assert len(network_call) == 1
            assert network_call[0][1]["status"] == "up"
            assert "2/2 healthy" in network_call[0][1]["message"]

            # Verify backup tag call
            backup_call = [
                call
                for call in mock_send.call_args_list
                if call[1]["push_token"] == "backup-token"
            ]
            assert len(backup_call) == 1
            assert backup_call[0][1]["status"] == "down"
            assert "0/1 healthy" in backup_call[0][1]["message"]

    def test_send_aggregated_results_no_checks_for_tag(self):
        """Test when requested tag has no checks."""
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test"),
            tags={"network": TagConfig(token="network-token")},
        )

        results_by_tag: dict[str, list[CheckResult]] = {"network": []}

        with patch("kuma_scout.cli.generator.send_push") as mock_send:
            gen._send_aggregated_results(
                results_by_tag, ["network"], global_config, logger
            )

            # Should debug log but not send
            mock_send.assert_not_called()
            logger.debug.assert_called()

    def test_send_aggregated_results_send_fails(self):
        """Test error handling when sending to Uptime Kuma fails."""
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test"),
            tags={"network": TagConfig(token="network-token")},
        )

        results_by_tag: dict[str, list[CheckResult]] = {
            "network": [
                CheckResult(
                    check_name="check1", status="up", message="OK", duration_seconds=5
                )
            ]
        }

        with patch(
            "kuma_scout.cli.generator.send_push", return_value=False
        ) as mock_send:
            gen._send_aggregated_results(
                results_by_tag, ["network"], global_config, logger
            )

            mock_send.assert_called_once()
            logger.error.assert_called()

    def test_auto_aggregation_multiple_tags(self):
        """Test that aggregation automatically includes all tags in executed checks.

        This simulates the behavior after running checks without --tag filters.
        All tags present in executed checks are automatically aggregated.
        """
        gen = CLIGenerator()
        logger = mock_logger()
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test"),
            tags={
                "network": TagConfig(token="network-token"),
                "critical": TagConfig(token="critical-token"),
            },
        )

        # Results from checks that have multiple tags
        results_by_tag: dict[str, list[CheckResult]] = {
            "network": [
                CheckResult(
                    check_name="internet-check",
                    status="up",
                    message="OK",
                    duration_seconds=5,
                    tags=["network"],
                ),
            ],
            "critical": [
                CheckResult(
                    check_name="database-check",
                    status="up",
                    message="OK",
                    duration_seconds=3,
                    tags=["critical"],
                ),
            ],
        }

        # Simulate auto-aggregation: all tags in results_by_tag are aggregated
        all_tags = list(results_by_tag.keys())

        with patch(
            "kuma_scout.cli.generator.send_push", return_value=True
        ) as mock_send:
            gen._send_aggregated_results(
                results_by_tag, all_tags, global_config, logger
            )

            # Verify both tags were sent
            assert mock_send.call_count == 2

            # Verify network tag
            network_calls = [
                call
                for call in mock_send.call_args_list
                if call[1]["push_token"] == "network-token"
            ]
            assert len(network_calls) == 1

            # Verify critical tag
            critical_calls = [
                call
                for call in mock_send.call_args_list
                if call[1]["push_token"] == "critical-token"
            ]
            assert len(critical_calls) == 1


class TestCheckResultTags:
    """Test CheckResult tags functionality."""

    def test_check_result_default_empty_tags(self):
        """Test that CheckResult has empty tags by default."""
        result = CheckResult(
            check_name="test", status="up", message="OK", duration_seconds=1
        )
        assert result.tags == []

    def test_check_result_with_tags(self):
        """Test CheckResult with tags."""
        result = CheckResult(
            check_name="test",
            status="up",
            message="OK",
            duration_seconds=1,
            tags=["network", "critical"],
        )
        assert result.tags == ["network", "critical"]

    def test_check_result_tags_mutable(self):
        """Test that tags can be modified after creation."""
        result = CheckResult(
            check_name="test", status="up", message="OK", duration_seconds=1
        )
        result.tags = ["network"]
        assert result.tags == ["network"]


class TestGlobalConfigTags:
    """Test GlobalConfig tags support."""

    def test_global_config_default_empty_tags(self):
        """Test that GlobalConfig has empty tags by default."""
        config = GlobalConfig()
        assert config.tags == {}

    def test_global_config_with_tags(self):
        """Test GlobalConfig with tags."""
        config = GlobalConfig(
            tags={
                "network": TagConfig(token="network-token"),
                "backup": TagConfig(token="backup-token"),
            }
        )
        assert len(config.tags) == 2
        assert config.tags["network"].token == "network-token"
        assert config.tags["backup"].token == "backup-token"

    def test_tag_config_with_description(self):
        """Test TagConfig with optional description."""
        tag = TagConfig(token="test-token", description="Test description")
        assert tag.token == "test-token"
        assert tag.description == "Test description"

    def test_tag_config_description_optional(self):
        """Test TagConfig without description."""
        tag = TagConfig(token="test-token")
        assert tag.token == "test-token"
        assert tag.description is None
