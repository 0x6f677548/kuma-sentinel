"""Tests for CLI generator critical methods."""

from typing import Dict, List
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

    def test_generate_list_checks_command(self, generator):
        """Test that list checks command can be generated."""
        command = generator.generate_list_checks_command()
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


class TestSetupRunCommand:
    """Test _setup_run_command method."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    @patch("kuma_scout.cli.generator.load_config")
    @patch("kuma_scout.cli.generator.setup_logging")
    @patch("kuma_scout.cli.generator.setup_default_logging")
    def test_setup_run_command_success(
        self, mock_setup_default, mock_setup_logging, mock_load_config, generator
    ):
        """Test successful setup of run command."""
        from kuma_scout.plugins.models import GlobalConfig

        mock_global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com")
        )
        mock_checks = [("cmdcheck", {"name": "test"})]

        mock_load_config.return_value = (mock_global_config, mock_checks)

        with patch("kuma_scout.cli.generator.OutputHandler"):
            result = generator._setup_run_command(
                config="test.yaml",
                ignore_file_permissions=False,
                uptime_kuma_url=None,
                token=None,
                heartbeat_token=None,
                timeout=30,
                log_file=None,
                log_level=None,
                ssh=None,
                ssh_key_file=None,
                ssh_password=None,
                ssh_strict_host_key_checking=True,
                ssh_no_strict_host_key_checking=False,
                quiet=False,
                verbose=False,
            )

            mock_setup_default.assert_called_once()
            mock_setup_logging.assert_called_once_with(None, "INFO", verbose=False)
            mock_load_config.assert_called_once_with(
                "test.yaml", ignore_file_permissions=False
            )
            assert len(result) == 3  # output_handler, global_config, checks

    @patch("kuma_scout.cli.generator.load_config")
    @patch("kuma_scout.cli.generator.setup_logging")
    @patch("kuma_scout.cli.generator.setup_default_logging")
    def test_setup_run_command_config_error(
        self, mock_setup_default, mock_setup_logging, mock_load_config, generator
    ):
        """Test setup with config loading error."""
        mock_load_config.side_effect = ValueError("Invalid config")

        with patch(
            "kuma_scout.cli.generator.OutputHandler"
        ) as mock_output_handler_class:
            mock_output_handler = Mock()
            mock_output_handler_class.return_value = mock_output_handler

            with pytest.raises(RuntimeError):  # typer.Exit inherits from RuntimeError
                generator._setup_run_command(
                    config="invalid.yaml",
                    ignore_file_permissions=False,
                    uptime_kuma_url=None,
                    token=None,
                    heartbeat_token=None,
                    timeout=30,
                    log_file=None,
                    log_level=None,
                    ssh=None,
                    ssh_key_file=None,
                    ssh_password=None,
                    ssh_strict_host_key_checking=True,
                    ssh_no_strict_host_key_checking=False,
                    quiet=False,
                    verbose=False,
                )

            mock_output_handler.error.assert_called_once_with(
                "Configuration error: Invalid config", echo=True
            )

    @patch("kuma_scout.cli.generator.load_config")
    @patch("kuma_scout.cli.generator.setup_logging")
    @patch("kuma_scout.cli.generator.setup_default_logging")
    def test_setup_run_command_with_ssh(
        self, mock_setup_default, mock_setup_logging, mock_load_config, generator
    ):
        """Test setup with SSH configuration."""
        from kuma_scout.plugins.models import GlobalConfig

        mock_global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com")
        )
        mock_checks = [("cmdcheck", {"name": "test"})]

        mock_load_config.return_value = (mock_global_config, mock_checks)

        with patch("kuma_scout.cli.generator.OutputHandler"):
            result = generator._setup_run_command(
                config="test.yaml",
                ignore_file_permissions=False,
                uptime_kuma_url=None,
                token=None,
                heartbeat_token=None,
                timeout=30,
                log_file=None,
                log_level=None,
                ssh="user@host:2222",
                ssh_key_file="/path/to/key",
                ssh_password="secret",
                ssh_strict_host_key_checking=False,
                ssh_no_strict_host_key_checking=False,
                quiet=False,
                verbose=False,
            )

            mock_setup_default.assert_called_once()
            mock_setup_logging.assert_called_once_with(None, "INFO", verbose=False)
            mock_load_config.assert_called_once_with(
                "test.yaml", ignore_file_permissions=False
            )
            assert len(result) == 3
            # Check that SSH config was set
            output_handler, global_config, checks = result
            assert global_config.ssh is not None
            assert global_config.ssh.host == "host"
            assert global_config.ssh.user == "user"
            assert global_config.ssh.port == 2222
            assert global_config.ssh.key_file == "/path/to/key"
            assert global_config.ssh.password == "secret"
            assert global_config.ssh.strict_host_key_checking is False


class TestHandleDryRun:
    """Test _handle_dry_run method."""

    @pytest.fixture
    def generator(self):
        """Create a CLIGenerator instance."""
        return CLIGenerator()

    def test_handle_dry_run_no_filters(self, generator):
        """Test dry run with no filters."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "check1", "tags": ["web"]}),
            ("portscan", {"name": "check2", "tags": ["network"]}),
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=None,
            name=None,
            plugin_type=None,
            exclude=None,
        )

        mock_output_handler.info.assert_any_call("Configuration: test.yaml", echo=True)
        mock_output_handler.info.assert_any_call(
            "Found 2 check(s) to execute", echo=True
        )

    def test_handle_dry_run_with_filters(self, generator):
        """Test dry run with filters applied."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=["web"],
            name=None,
            plugin_type=None,
            exclude=None,
        )

        mock_output_handler.info.assert_any_call("Configuration: test.yaml", echo=True)
        mock_output_handler.info.assert_any_call("Tag filters: web", echo=True)
        mock_output_handler.info.assert_any_call(
            "Found 1 check(s) to execute", echo=True
        )

    def test_handle_dry_run_with_name_filter(self, generator):
        """Test dry run with name filter."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=None,
            name=["nginx-check"],
            plugin_type=None,
            exclude=None,
        )

        mock_output_handler.info.assert_any_call("Configuration: test.yaml", echo=True)
        mock_output_handler.info.assert_any_call("Name filters: nginx-check", echo=True)
        mock_output_handler.info.assert_any_call(
            "Found 1 check(s) to execute", echo=True
        )

    def test_handle_dry_run_with_plugin_type_filter(self, generator):
        """Test dry run with plugin type filter."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=None,
            name=None,
            plugin_type=["cmdcheck"],
            exclude=None,
        )

        mock_output_handler.info.assert_any_call("Configuration: test.yaml", echo=True)
        mock_output_handler.info.assert_any_call("Type filters: cmdcheck", echo=True)
        mock_output_handler.info.assert_any_call(
            "Found 1 check(s) to execute", echo=True
        )

    def test_handle_dry_run_with_exclude_filter(self, generator):
        """Test dry run with exclude filter."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "nginx-check", "tags": ["web"]}),
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=None,
            name=None,
            plugin_type=None,
            exclude=["old-check"],
        )

        mock_output_handler.info.assert_any_call("Configuration: test.yaml", echo=True)
        mock_output_handler.info.assert_any_call(
            "Excluding checks: old-check", echo=True
        )
        mock_output_handler.info.assert_any_call(
            "Found 1 check(s) to execute", echo=True
        )

    def test_handle_dry_run_check_without_tags(self, generator):
        """Test dry run with check that has no tags."""
        mock_output_handler = Mock()
        filtered_checks = [
            ("cmdcheck", {"name": "check1"}),  # No tags
        ]

        generator._handle_dry_run(
            mock_output_handler,
            filtered_checks,
            config="test.yaml",
            tag=None,
            name=None,
            plugin_type=None,
            exclude=None,
        )

        mock_output_handler.info.assert_any_call("  - 'check1' (cmdcheck)", echo=True)


class TestProcessResults:
    """Test _process_results method."""

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
                token="test-token",
            )
        )

    def test_process_results_with_results(self, generator, global_config):
        """Test processing results when there are results to process."""
        mock_output_handler = Mock()
        results_by_tag = {
            "web": [
                CheckResult(
                    check_name="nginx-check",
                    status="up",
                    message="OK",
                    duration_seconds=1,
                    tags=["web"],
                    plugin_type="cmdcheck",
                )
            ]
        }
        all_results = list(results_by_tag["web"])

        with patch.object(generator, "_send_aggregated_results") as mock_send:
            generator._process_results_and_report(
                results_by_tag, all_results, global_config, mock_output_handler
            )

            mock_send.assert_called_once()
            mock_output_handler.print_table.assert_called_once()

    def test_process_results_no_results_by_tag(self, generator, global_config):
        """Test processing when there are no results by tag."""
        mock_output_handler = Mock()
        results_by_tag: Dict[str, List[CheckResult]] = {}
        all_results: List[CheckResult] = [
            CheckResult(
                check_name="nginx-check",
                status="up",
                message="OK",
                duration_seconds=1,
                tags=["web"],
                plugin_type="cmdcheck",
            )
        ]

        with patch.object(generator, "_send_aggregated_results") as mock_send:
            generator._process_results_and_report(
                results_by_tag, all_results, global_config, mock_output_handler
            )

            mock_send.assert_not_called()
            mock_output_handler.print_table.assert_called_once()

    def test_process_results_no_all_results(self, generator, global_config):
        """Test processing when there are no results at all."""
        mock_output_handler = Mock()
        results_by_tag: Dict[str, List[CheckResult]] = {"web": []}
        all_results: List[CheckResult] = []

        with patch.object(generator, "_send_aggregated_results") as mock_send:
            generator._process_results_and_report(
                results_by_tag, all_results, global_config, mock_output_handler
            )

            mock_send.assert_not_called()
            mock_output_handler.print_table.assert_not_called()
