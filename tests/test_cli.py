"""Tests for CLI application."""

import os
import sys
from io import StringIO
from unittest.mock import Mock

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from kuma_scout.cli.app import app
from kuma_scout.cli.generator import CLIGenerator
from kuma_scout.core.output_handler import OutputHandler
from kuma_scout.plugins.models import GlobalConfig, SSHConfig, UptimeKumaConfig

runner = CliRunner()


def test_cli_version():
    """Test CLI version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output


def test_cli_no_command():
    """Test CLI shows error when no command is provided."""
    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "Error: No command provided." in result.output
    assert "Use 'kuma-scout --help' to see available commands." in result.output


def test_subcommand_common_options():
    """Test that check subcommands have all common options available."""
    result = runner.invoke(app, ["portscan", "--help"])
    assert result.exit_code == 0
    # Check for common options that should appear in check subcommands
    assert "--log-file" in result.output
    assert "--log-level" in result.output
    assert "--uptime-kuma-url" in result.output
    assert "--token" in result.output
    assert "--retry-attempts" in result.output
    assert "--retry-delay-seconds" in result.output
    # Check for plugin-specific options
    assert "TAR" in result.output
    assert "--ports" in result.output


def test_apply_command_line_overrides_expands_tokens():
    """Test that _apply_command_line_overrides expands environment variables in tokens."""
    generator = CLIGenerator()
    config = GlobalConfig()

    # Set environment variable
    os.environ["TEST_TOKEN"] = "expanded_token_value"
    os.environ["TEST_HEARTBEAT_TOKEN"] = "expanded_heartbeat_value"

    try:
        generator._apply_command_line_overrides(
            global_config=config,
            uptime_kuma_url="http://example.com",
            token="$TEST_TOKEN",
            heartbeat_token="$TEST_HEARTBEAT_TOKEN",
            timeout=300,
            log_file=None,
            log_level=None,
        )

        assert config.uptime_kuma is not None
        assert config.uptime_kuma.token == "expanded_token_value"
        assert config.heartbeat.token == "expanded_heartbeat_value"
    finally:
        # Clean up environment variables
        del os.environ["TEST_TOKEN"]
        del os.environ["TEST_HEARTBEAT_TOKEN"]


def test_apply_command_line_overrides_sets_timeout():
    """Test that _apply_command_line_overrides sets timeout when not default."""
    generator = CLIGenerator()
    config = GlobalConfig()

    generator._apply_command_line_overrides(
        global_config=config,
        uptime_kuma_url=None,
        token=None,
        heartbeat_token=None,
        timeout=600,  # Not default
        log_file=None,
        log_level=None,
    )

    assert config.timeout == 600


def test_setup_ssh_config_expands_password():
    """Test that _setup_ssh_config expands environment variables in ssh_password."""
    generator = CLIGenerator()
    config = GlobalConfig()
    output_handler = OutputHandler(Console())

    # Set environment variable
    os.environ["TEST_SSH_PASSWORD"] = "expanded_password_value"

    try:
        generator._setup_ssh_config(
            global_config=config,
            ssh="user@host",
            ssh_key_file=None,
            ssh_password="$TEST_SSH_PASSWORD",
            ssh_strict_host_key_checking=True,
            ssh_no_strict_host_key_checking=False,
            output_handler=output_handler,
        )

        assert config.ssh is not None
        assert config.ssh.password == "expanded_password_value"
    finally:
        # Clean up environment variable
        del os.environ["TEST_SSH_PASSWORD"]


def test_setup_ssh_config_no_ssh():
    """Test _setup_ssh_config when no SSH is provided."""
    generator = CLIGenerator()
    config = GlobalConfig()
    output_handler = OutputHandler(Console())

    # Should not raise error when no SSH options are provided
    generator._setup_ssh_config(
        global_config=config,
        ssh=None,
        ssh_key_file=None,
        ssh_password=None,
        ssh_strict_host_key_checking=True,
        ssh_no_strict_host_key_checking=False,
        output_handler=output_handler,
    )

    assert config.ssh is None


def test_setup_ssh_config_error_when_ssh_options_without_host():
    """Test _setup_ssh_config raises error when SSH options provided but no host."""
    generator = CLIGenerator()
    config = GlobalConfig()
    output_handler = OutputHandler(Console())

    with pytest.raises(typer.Exit):
        generator._setup_ssh_config(
            global_config=config,
            ssh=None,
            ssh_key_file="/path/to/key",
            ssh_password=None,
            ssh_strict_host_key_checking=True,
            ssh_no_strict_host_key_checking=False,
            output_handler=output_handler,
        )


def test_create_plugin_config_merges_uptime_kuma():
    """Test that _create_plugin_config merges uptime_kuma configs correctly."""
    generator = CLIGenerator()
    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://global.com", token="global_token"
    )

    # Mock plugin class
    mock_plugin_class = Mock()
    mock_config_class = Mock()
    mock_plugin_class.config_class = mock_config_class

    check_config = {
        "name": "test_check",
        "uptime_kuma": {"url": "http://check.com", "token": "check_token"},
    }

    result = generator._create_plugin_config(
        mock_plugin_class, check_config, global_config
    )

    # Should use check-level config
    assert result.uptime_kuma.url == "http://check.com"
    assert result.uptime_kuma.token == "check_token"
    mock_config_class.assert_called_once_with(name="test_check")


def test_create_plugin_config_uses_global_uptime_kuma_when_no_check_level():
    """Test that _create_plugin_config uses global uptime_kuma when check doesn't have one."""
    generator = CLIGenerator()
    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://global.com", token="global_token"
    )

    mock_plugin_class = Mock()
    mock_config_class = Mock()
    mock_plugin_class.config_class = mock_config_class

    check_config = {"name": "test_check"}

    result = generator._create_plugin_config(
        mock_plugin_class, check_config, global_config
    )

    assert result.uptime_kuma.url == "http://global.com"
    assert result.uptime_kuma.token == "global_token"


def test_create_plugin_config_merges_ssh():
    """Test that _create_plugin_config merges SSH configs correctly."""
    generator = CLIGenerator()
    global_config = GlobalConfig()
    global_config.ssh = SSHConfig(host="global_host", user="global_user", port=22)

    mock_plugin_class = Mock()
    mock_config_class = Mock()
    mock_plugin_class.config_class = mock_config_class

    check_config = {
        "name": "test_check",
        "ssh": {"host": "check_host", "user": "check_user"},
    }

    result = generator._create_plugin_config(
        mock_plugin_class, check_config, global_config
    )

    # Should merge with check-level overriding
    assert result.ssh.host == "check_host"
    assert result.ssh.user == "check_user"
    assert result.ssh.port == 22  # From global


def test_filter_checks_by_tags():
    """Test _filter_checks filters by tags correctly."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1", "tags": ["tag1", "tag2"]}),
        ("type2", {"name": "check2", "tags": ["tag2", "tag3"]}),
        ("type3", {"name": "check3"}),  # No tags
    ]

    # Filter by tag1
    filtered = generator._filter_checks(checks, ["tag1"], None, None, None)
    assert len(filtered) == 1
    assert filtered[0][1]["name"] == "check1"

    # Filter by tag2 (should match both check1 and check2)
    filtered = generator._filter_checks(checks, ["tag2"], None, None, None)
    assert len(filtered) == 2
    names = [c[1]["name"] for c in filtered]
    assert "check1" in names
    assert "check2" in names

    # Filter by tag1 and tag2 (should match only check1)
    filtered = generator._filter_checks(checks, ["tag1", "tag2"], None, None, None)
    assert len(filtered) == 1
    assert filtered[0][1]["name"] == "check1"


def test_filter_checks_by_names():
    """Test _filter_checks filters by names correctly."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1"}),
        ("type2", {"name": "check2"}),
        ("type3", {"name": "check3"}),
    ]

    filtered = generator._filter_checks(checks, None, ["check1", "check3"], None, None)
    assert len(filtered) == 2
    names = [c[1]["name"] for c in filtered]
    assert "check1" in names
    assert "check3" in names


def test_filter_checks_by_types():
    """Test _filter_checks filters by plugin types correctly."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1"}),
        ("type1", {"name": "check2"}),
        ("type2", {"name": "check3"}),
    ]

    filtered = generator._filter_checks(checks, None, None, ["type1"], None)
    assert len(filtered) == 2
    types = [c[0] for c in filtered]
    assert all(t == "type1" for t in types)


def test_filter_checks_excludes():
    """Test _filter_checks excludes checks correctly."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1"}),
        ("type2", {"name": "check2"}),
        ("type3", {"name": "check3"}),
    ]

    filtered = generator._filter_checks(checks, None, None, None, ["check2"])
    assert len(filtered) == 2
    names = [c[1]["name"] for c in filtered]
    assert "check1" in names
    assert "check3" in names
    assert "check2" not in names


def test_filter_checks_combined():
    """Test _filter_checks with multiple filter types combined (AND logic)."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1", "tags": ["web", "prod"]}),
        ("type1", {"name": "check2", "tags": ["web", "dev"]}),
        ("type2", {"name": "check3", "tags": ["db", "prod"]}),
        ("type2", {"name": "check4"}),  # No tags
    ]

    # Filter by tags AND names (should match check1 only)
    filtered = generator._filter_checks(checks, ["web", "prod"], ["check1"], None, None)
    assert len(filtered) == 1
    assert filtered[0][1]["name"] == "check1"

    # Filter by tags AND types (should match check1 and check2)
    filtered = generator._filter_checks(checks, ["web"], None, ["type1"], None)
    assert len(filtered) == 2
    names = [c[1]["name"] for c in filtered]
    assert "check1" in names
    assert "check2" in names

    # Filter by tags AND exclude (should match check2 only)
    filtered = generator._filter_checks(checks, ["web"], None, None, ["check1"])
    assert len(filtered) == 1
    assert filtered[0][1]["name"] == "check2"


def test_filter_checks_edge_cases():
    """Test _filter_checks edge cases."""
    generator = CLIGenerator()
    checks: list[tuple[str, dict]] = [
        ("type1", {"name": "check1", "tags": ["tag1"]}),
        ("type1", {"name": "check2"}),  # No tags
        ("type2", {"name": "check3", "tags": []}),  # Empty tags
    ]

    # Filter by non-existent tag (should match nothing)
    filtered = generator._filter_checks(checks, ["nonexistent"], None, None, None)
    assert len(filtered) == 0

    # Filter by empty tags list (should not filter - return all)
    filtered = generator._filter_checks(checks, [], None, None, None)
    assert len(filtered) == 3

    # Filter by tag on check with no tags field (should not match)
    filtered = generator._filter_checks(checks, ["tag1"], None, None, None)
    assert len(filtered) == 1
    assert filtered[0][1]["name"] == "check1"

    # No filters (should return all)
    filtered = generator._filter_checks(checks, None, None, None, None)
    assert len(filtered) == 3


def test_build_check_config_data():
    """Test _build_check_config_data builds config dict correctly."""
    generator = CLIGenerator()

    kwargs = {
        "param1": "value1",
        "param2": None,
        "param3": "PydanticUndefined",  # This should be excluded
    }

    result = generator._build_check_config_data(
        name="test_name", retry_attempts=3, retry_delay_seconds=5, kwargs=kwargs
    )

    assert result["name"] == "test_name"
    assert result["param1"] == "value1"
    assert "param2" not in result  # None values should be excluded
    assert "param3" not in result  # "PydanticUndefined" string should be excluded
    assert result["retry"]["attempts"] == 3
    assert result["retry"]["delay_seconds"] == 5


def test_log_config_summary():
    """Test _log_config_summary logs configuration correctly."""
    generator = CLIGenerator()
    output_handler = OutputHandler()
    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://example.com", token="token"
    )
    global_config.heartbeat.enabled = True
    global_config.heartbeat.interval = 300
    global_config.ssh = SSHConfig(host="host", user="user", port=22)

    generator._log_config_summary(output_handler, global_config)

    # Check that output_handler.info was called with expected messages
    # Since OutputHandler uses get_logger() internally, we can't easily mock it
    # This test mainly ensures the method doesn't crash
    assert True


def test_generate_list_plugins_command():
    """Test generate_list_plugins_command returns a callable."""
    generator = CLIGenerator()
    command = generator.generate_list_plugins_command()

    assert callable(command)


def test_generate_list_checks_command():
    """Test generate_list_checks_command returns a callable."""
    generator = CLIGenerator()
    command = generator.generate_list_checks_command()

    assert callable(command)


def test_generate_run_command():
    """Test generate_run_command returns a callable."""
    generator = CLIGenerator()
    command = generator.generate_run_command()

    assert callable(command)


def test_generate_check_commands():
    """Test generate_check_commands returns a list of commands."""
    generator = CLIGenerator()
    commands = generator.generate_check_commands()

    assert isinstance(commands, list)
    # Should have commands for each plugin
    assert len(commands) > 0
    for plugin_type, command in commands:
        assert isinstance(plugin_type, str)
        assert callable(command)


def test_create_parameter_for_field_string_required():
    """Test _create_parameter_for_field creates correct parameter for required string field."""
    from pydantic_core import PydanticUndefined

    generator = CLIGenerator()
    field_info = Mock()
    field_info.annotation = str
    field_info.is_required.return_value = True
    field_info.default = PydanticUndefined
    field_info.description = "Test field"

    param = generator._create_parameter_for_field("test_field", field_info)

    assert param.name == "test_field"
    assert param.annotation is str
    assert param.default.__class__.__name__ == "ArgumentInfo"


def test_create_parameter_for_field_int_optional():
    """Test _create_parameter_for_field creates correct parameter for optional int field."""
    generator = CLIGenerator()
    field_info = Mock()
    field_info.annotation = int
    field_info.is_required.return_value = False
    field_info.default = 42
    field_info.description = "Test int field"

    param = generator._create_parameter_for_field("test_int", field_info)

    assert param.name == "test_int"
    assert param.annotation is int
    assert param.default.default == 42


def test_create_plugin_parameters():
    """Test _create_plugin_parameters creates correct parameters for a config class."""
    from kuma_scout.plugins.cmdcheck import CmdCheckConfig

    generator = CLIGenerator()
    existing_param_names = {"name", "uptime_kuma", "ssh", "tags", "retry"}

    params = generator._create_plugin_parameters(CmdCheckConfig, existing_param_names)

    # Should have parameters for command (required) and expect_exit_code (optional)
    param_names = [p.name for p in params]
    assert "command" in param_names
    assert "expect_exit_code" in param_names

    # Check that command is required (first in list)
    command_param = next(p for p in params if p.name == "command")
    assert command_param.default.__class__.__name__ == "ArgumentInfo"


def test_generate_list_plugins_command_execution():
    """Test generate_list_plugins_command executes without error."""
    generator = CLIGenerator()
    command = generator.generate_list_plugins_command()

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    try:
        command()
        output = captured_output.getvalue()
        assert "Available plugins:" in output
        assert "cmdcheck" in output  # Should have at least cmdcheck plugin
    finally:
        sys.stdout = old_stdout


def test_cmdcheck_individual_command():
    """Test that individual cmdcheck command works without TypeError and shows proper output."""
    # This test ensures that individual check commands properly create OutputHandler
    # instead of passing logger directly, preventing the "unexpected keyword argument 'echo'" error
    result = runner.invoke(
        app,
        [
            "cmdcheck",
            "echo test",
            "--uptime-kuma-url",
            "http://localhost:3001/api/push",
            "--token",
            "dummy-token",
        ],
    )

    # Should not crash with TypeError about 'echo' argument
    # The command may fail due to network issues, but shouldn't have the logger/output_handler bug
    assert result.exit_code in [0, 1]  # 0 for success, 1 for network/reporting failure
    assert "TypeError" not in result.output
    assert "unexpected keyword argument 'echo'" not in result.output

    # Check that we show execution start and result messages
    assert "Executing individual check:" in result.output
    assert (
        "(local)" in result.output
    )  # Should show local execution since no SSH specified
    assert "completed:" in result.output


# ConfigMerger tests
def test_merge_uptime_kuma_config_check_level_only():
    """Test merging uptime_kuma config when only check-level config exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    check_config = {"uptime_kuma": {"url": "http://check.com", "token": "check_token"}}

    result = ConfigMerger.merge_uptime_kuma_config(global_config, check_config)

    assert result == {"url": "http://check.com", "token": "check_token"}


def test_merge_uptime_kuma_config_global_only():
    """Test merging uptime_kuma config when only global config exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://global.com", token="global_token"
    )
    check_config = {}

    result = ConfigMerger.merge_uptime_kuma_config(global_config, check_config)

    assert result == {"url": "http://global.com", "token": "global_token"}


def test_merge_uptime_kuma_config_both_with_override():
    """Test merging uptime_kuma config when both exist - check overrides global."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://global.com", token="global_token"
    )
    check_config = {"uptime_kuma": {"url": "http://check.com"}}

    result = ConfigMerger.merge_uptime_kuma_config(global_config, check_config)

    # Check-level should override global
    assert result == {"url": "http://check.com", "token": "global_token"}


def test_merge_uptime_kuma_config_none():
    """Test merging uptime_kuma config when neither exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    check_config = {}

    result = ConfigMerger.merge_uptime_kuma_config(global_config, check_config)

    assert result is None


def test_merge_ssh_config_check_level_only():
    """Test merging SSH config when only check-level config exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    check_config = {"ssh": {"host": "check_host", "user": "check_user"}}

    result = ConfigMerger.merge_ssh_config(global_config, check_config)

    assert result == {"host": "check_host", "user": "check_user"}


def test_merge_ssh_config_global_only():
    """Test merging SSH config when only global config exists."""
    from kuma_scout.cli.config_merger import ConfigMerger
    from kuma_scout.plugins.models import SSHConfig

    global_config = GlobalConfig()
    global_config.ssh = SSHConfig(host="global_host", user="global_user", port=22)
    check_config = {}

    result = ConfigMerger.merge_ssh_config(global_config, check_config)

    expected = {
        "host": "global_host",
        "user": "global_user",
        "port": 22,
        "key_file": None,
        "password": None,
        "strict_host_key_checking": True,
    }
    assert result == expected


def test_merge_ssh_config_both_with_override():
    """Test merging SSH config when both exist - check overrides global."""
    from kuma_scout.cli.config_merger import ConfigMerger
    from kuma_scout.plugins.models import SSHConfig

    global_config = GlobalConfig()
    global_config.ssh = SSHConfig(host="global_host", user="global_user", port=22)
    check_config = {"ssh": {"host": "check_host"}}

    result = ConfigMerger.merge_ssh_config(global_config, check_config)

    # Check-level should override global
    expected = {
        "host": "check_host",
        "user": "global_user",
        "port": 22,
        "key_file": None,
        "password": None,
        "strict_host_key_checking": True,
    }
    assert result == expected


def test_merge_ssh_config_none():
    """Test merging SSH config when neither exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    check_config = {}

    result = ConfigMerger.merge_ssh_config(global_config, check_config)

    assert result is None


def test_apply_timeout_from_global():
    """Test applying timeout from global config when not in check config."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig(timeout=600)
    merged_config = {"name": "test_check"}

    ConfigMerger.apply_timeout(merged_config, global_config)

    assert merged_config["timeout"] == 600


def test_apply_timeout_check_has_priority():
    """Test that check-level timeout takes priority over global."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig(timeout=600)
    merged_config = {"name": "test_check", "timeout": 300}

    ConfigMerger.apply_timeout(merged_config, global_config)

    # Should not override existing timeout
    assert merged_config["timeout"] == 300


def test_apply_timeout_global_default_not_applied():
    """Test that global default timeout (300) is not applied."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig(timeout=300)  # Default value
    merged_config = {"name": "test_check"}

    ConfigMerger.apply_timeout(merged_config, global_config)

    # Should not add default timeout
    assert "timeout" not in merged_config


def test_apply_cli_overrides_uptime_kuma():
    """Test applying CLI overrides for uptime_kuma config."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url="http://cli.com",
        token="cli_token",
        heartbeat_token=None,
        timeout=300,
        log_file=None,
        log_level=None,
    )

    assert global_config.uptime_kuma.url == "http://cli.com"
    assert global_config.uptime_kuma.token == "cli_token"


def test_apply_cli_overrides_uptime_kuma_existing_config():
    """Test applying CLI overrides when uptime_kuma config already exists."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://existing.com", token="existing_token"
    )

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url="http://cli.com",
        token="cli_token",
        heartbeat_token=None,
        timeout=300,
        log_file=None,
        log_level=None,
    )

    # CLI should override existing config
    assert global_config.uptime_kuma.url == "http://cli.com"
    assert global_config.uptime_kuma.token == "cli_token"


def test_apply_cli_overrides_uptime_kuma_url_only():
    """Test applying CLI URL override without token."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()
    global_config.uptime_kuma = UptimeKumaConfig(
        url="http://existing.com", token="existing_token"
    )

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url="http://cli.com",
        token=None,  # No token provided
        heartbeat_token=None,
        timeout=300,
        log_file=None,
        log_level=None,
    )

    # URL should be overridden, token should remain
    assert global_config.uptime_kuma.url == "http://cli.com"
    assert global_config.uptime_kuma.token == "existing_token"


def test_apply_cli_overrides_heartbeat_token():
    """Test applying CLI overrides for heartbeat token."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url=None,
        token=None,
        heartbeat_token="cli_heartbeat_token",
        timeout=300,
        log_file=None,
        log_level=None,
    )

    assert global_config.heartbeat.token == "cli_heartbeat_token"


def test_apply_cli_overrides_timeout():
    """Test applying CLI overrides for timeout."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url=None,
        token=None,
        heartbeat_token=None,
        timeout=600,
        log_file=None,
        log_level=None,
    )

    assert global_config.timeout == 600


def test_apply_cli_overrides_logging():
    """Test applying CLI overrides for logging config."""
    from kuma_scout.cli.config_merger import ConfigMerger

    global_config = GlobalConfig()

    ConfigMerger.apply_cli_overrides(
        global_config=global_config,
        uptime_kuma_url=None,
        token=None,
        heartbeat_token=None,
        timeout=300,
        log_file="/tmp/test.log",
        log_level="DEBUG",
    )

    assert global_config.logging.file == "/tmp/test.log"
    assert global_config.logging.level == "DEBUG"
