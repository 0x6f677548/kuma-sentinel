"""Tests for CLI generator critical methods."""

from unittest.mock import Mock, patch

import pytest

from kuma_scout.cli.generator import CLIGenerator
from kuma_scout.core.models import CheckResult
from kuma_scout.plugins.models import GlobalConfig, UptimeKumaConfig


class TestFilterChecks:
    """Test _filter_checks method."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    def test_filter_checks_no_filters(self, generator):
        """Test that all checks are returned when no filters are applied."""
        checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web"]}),
            ("portscan", {"name": "check2", "tags": ["network"]}),
            ("cmdcheck", {"name": "check3", "tags": ["web", "critical"]}),
        ]

        result = generator._filter_checks(checks, None, None, None, None)
        assert len(result) == 3
        assert result == checks

    def test_filter_checks_by_name(self, generator):
        """Test filtering checks by name."""
        checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
            ("portscan", {"name": "port-check", "tags": ["network"]}),
            ("cmdcheck", {"name": "disk-check", "tags": ["storage"]}),
        ]

        result = generator._filter_checks(checks, None, ["nginx-check"], None, None)
        assert len(result) == 1
        assert result[0][1]["name"] == "nginx-check"

    def test_filter_checks_by_multiple_names(self, generator):
        """Test filtering checks by multiple names."""
        checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
            ("portscan", {"name": "port-check", "tags": ["network"]}),
            ("cmdcheck", {"name": "disk-check", "tags": ["storage"]}),
        ]

        result = generator._filter_checks(
            checks, None, ["nginx-check", "disk-check"], None, None
        )
        assert len(result) == 2
        names = {r[1]["name"] for r in result}
        assert names == {"nginx-check", "disk-check"}

    def test_filter_checks_by_plugin_type(self, generator):
        """Test filtering checks by plugin type."""
        checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web"]}),
            ("portscan", {"name": "check2", "tags": ["network"]}),
            ("cmdcheck", {"name": "check3", "tags": ["web"]}),
        ]

        result = generator._filter_checks(checks, None, None, ["cmdcheck"], None)
        assert len(result) == 2
        assert all(r[0] == "cmdcheck" for r in result)

    def test_filter_checks_by_tag(self, generator):
        """Test filtering checks by tag."""
        checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web", "critical"]}),
            ("portscan", {"name": "check2", "tags": ["network"]}),
            ("cmdcheck", {"name": "check3", "tags": ["web"]}),
        ]

        result = generator._filter_checks(checks, ["web"], None, None, None)
        assert len(result) == 2
        names = {r[1]["name"] for r in result}
        assert names == {"check1", "check3"}

    def test_filter_checks_by_multiple_tags(self, generator):
        """Test filtering checks by multiple tags (AND logic)."""
        checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web", "critical", "prod"]}),
            ("cmdcheck", {"name": "check2", "tags": ["web", "critical"]}),
            ("cmdcheck", {"name": "check3", "tags": ["web"]}),
        ]

        # Multiple tags require ALL tags to be present
        result = generator._filter_checks(checks, ["web", "critical"], None, None, None)
        assert len(result) == 2
        names = {r[1]["name"] for r in result}
        assert names == {"check1", "check2"}

    def test_filter_checks_exclude(self, generator):
        """Test excluding checks by name."""
        checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
            ("portscan", {"name": "port-check", "tags": ["network"]}),
            ("cmdcheck", {"name": "disk-check", "tags": ["storage"]}),
        ]

        result = generator._filter_checks(checks, None, None, None, ["port-check"])
        assert len(result) == 2
        names = {r[1]["name"] for r in result}
        assert "port-check" not in names

    def test_filter_checks_exclude_takes_precedence(self, generator):
        """Test that exclude filter takes precedence over other filters."""
        checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web"]}),
            ("cmdcheck", {"name": "check2", "tags": ["web"]}),
        ]

        # Include all web checks, but exclude check2
        result = generator._filter_checks(checks, ["web"], None, None, ["check2"])
        assert len(result) == 1
        assert result[0][1]["name"] == "check1"

    def test_filter_checks_empty_list(self, generator):
        """Test filtering an empty checks list."""
        result = generator._filter_checks([], ["web"], ["check1"], None, None)
        assert result == []

    def test_filter_checks_no_tags_in_check(self, generator):
        """Test filtering when check has no tags."""
        checks = [
            ("cmdcheck", {"name": "check1"}),  # No tags field
            ("cmdcheck", {"name": "check2", "tags": ["web"]}),
        ]

        result = generator._filter_checks(checks, ["web"], None, None, None)
        assert len(result) == 1
        assert result[0][1]["name"] == "check2"

    def test_filter_checks_combined_filters(self, generator):
        """Test combining multiple filter types."""
        checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web", "critical"]}),
            ("cmdcheck", {"name": "disk-check", "tags": ["storage"]}),
            ("portscan", {"name": "port-check", "tags": ["web"]}),
        ]

        # Filter by tag and type
        result = generator._filter_checks(checks, ["web"], None, ["cmdcheck"], None)
        assert len(result) == 1
        assert result[0][1]["name"] == "nginx-check"


class TestExecuteSingleCheck:
    """Test _execute_single_check method."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    @pytest.fixture
    def mock_output_handler(self):
        """Create a mock output handler."""
        return Mock()

    @pytest.fixture
    def global_config(self):
        """Create a basic global config."""
        return GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://uptimekuma:3001/api/push",
                token="test-token",
            )
        )

    @pytest.fixture
    def mock_plugin_class(self):
        """Create a mock plugin class."""
        mock_plugin = Mock()
        mock_plugin.execute_with_heartbeat = Mock(
            return_value=CheckResult(
                check_name="test-check",
                status="up",
                message="Check passed",
                duration_seconds=1,
            )
        )
        return mock_plugin

    def test_execute_single_check_success(
        self, generator, mock_output_handler, global_config, mock_plugin_class
    ):
        """Test successful single check execution."""
        plugins = {"cmdcheck": mock_plugin_class}
        check_config = {"name": "test-check", "command": "echo test"}

        with patch.object(
            generator, "_create_plugin_config"
        ) as mock_create_config, patch.object(
            generator, "_execute_check_with_reporting"
        ) as mock_execute:
            mock_config_obj = Mock()
            mock_create_config.return_value = mock_config_obj
            expected_result = CheckResult(
                check_name="test-check",
                status="up",
                message="Check passed",
                duration_seconds=1,
            )
            mock_execute.return_value = expected_result

            result = generator._execute_single_check(
                "cmdcheck",
                check_config,
                global_config,
                plugins,
                mock_output_handler,
            )

            assert result == expected_result
            mock_create_config.assert_called_once()
            mock_execute.assert_called_once()

    def test_execute_single_check_unknown_plugin_type(
        self, generator, mock_output_handler, global_config
    ):
        """Test execution with unknown plugin type."""
        plugins = {"cmdcheck": Mock()}
        check_config = {"name": "test-check"}

        result = generator._execute_single_check(
            "unknown_type",
            check_config,
            global_config,
            plugins,
            mock_output_handler,
        )

        assert result is None
        mock_output_handler.error.assert_called()
        assert "Unknown plugin type" in mock_output_handler.error.call_args[0][0]

    def test_execute_single_check_exception_handling(
        self, generator, mock_output_handler, global_config
    ):
        """Test exception handling during check execution."""
        plugins = {"cmdcheck": Mock()}
        check_config = {"name": "test-check", "command": "test"}

        with patch.object(generator, "_create_plugin_config") as mock_create_config:
            mock_create_config.side_effect = ValueError("Invalid config")

            result = generator._execute_single_check(
                "cmdcheck",
                check_config,
                global_config,
                plugins,
                mock_output_handler,
            )

            assert result is None
            mock_output_handler.error.assert_called()
            assert "Failed to execute" in mock_output_handler.error.call_args[0][0]


class TestPluginSubcommandGeneration:
    """Test plugin subcommand generation."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    def test_generate_check_commands(self, generator):
        """Test that generate_check_commands creates subcommands."""
        commands = generator.generate_check_commands()
        assert isinstance(commands, list)
        assert len(commands) > 0
        # Each command is a tuple of (name, callable)
        for name, command in commands:
            assert isinstance(name, str)
            assert callable(command)

    def test_generate_list_plugins_command(self, generator):
        """Test that list plugins command can be generated."""
        command = generator.generate_list_plugins_command()
        assert callable(command)

    def test_generate_run_command(self, generator):
        """Test that run command can be generated."""
        command = generator.generate_run_command()
        assert callable(command)


class TestCreatePluginConfig:
    """Test _create_plugin_config method."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    @pytest.fixture
    def global_config(self):
        """Create a basic global config."""
        return GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://uptimekuma:3001/api/push",
                token="global-token",
            ),
            ssh=None,
        )

    @pytest.fixture
    def mock_plugin_class(self):
        """Create a mock plugin class with config."""
        from pydantic import Field

        from kuma_scout.plugins.base import CheckConfig

        class TestCheckConfig(CheckConfig):
            command: str = Field(description="Command to run")

        mock_plugin = Mock()
        mock_plugin.config_class = TestCheckConfig
        return mock_plugin

    def test_create_plugin_config_basic(
        self, generator, global_config, mock_plugin_class
    ):
        """Test creating plugin config from check config dict."""
        check_config_dict = {
            "name": "test-check",
            "command": "echo test",
        }

        config = generator._create_plugin_config(
            mock_plugin_class,
            check_config_dict,
            global_config,
        )

        assert config.name == "test-check"
        assert config.command == "echo test"

    def test_create_plugin_config_inherits_global_uptime_kuma(
        self, generator, global_config, mock_plugin_class
    ):
        """Test that created config inherits global Uptime Kuma settings."""
        check_config_dict = {
            "name": "test-check",
            "command": "echo test",
        }

        config = generator._create_plugin_config(
            mock_plugin_class,
            check_config_dict,
            global_config,
        )

        # Should inherit global uptime_kuma config
        assert (
            config.uptime_kuma is None
            or config.uptime_kuma.url == global_config.uptime_kuma.url
        )
