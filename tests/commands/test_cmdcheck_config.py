"""Tests for cmdcheck configuration."""

import pytest

from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig


@pytest.fixture
def config():
    """Create cmdcheck config for testing."""
    return CmdCheckConfig()


class TestConfigBasicDefaults:
    """Test configuration defaults."""

    def test_defaults(self, config):
        """Test default values are set correctly."""
        assert config.cmdcheck_command is None
        assert config.cmdcheck_commands == []
        assert config.cmdcheck_multiple is False
        assert config.cmdcheck_timeout == 30
        assert config.cmdcheck_expect_exit_code == 0
        assert config.cmdcheck_capture_output is True
        assert config.cmdcheck_success_pattern is None
        assert config.cmdcheck_failure_pattern is None


class TestYAMLLoading:
    """Test YAML configuration loading."""

    def test_load_single_command_from_yaml(self, config, tmp_path):
        """Test loading single command from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            """
logging:
  log_file: /var/log/test.log
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  command: "test -f /tmp/file"
  timeout: 60
  expect_exit_code: 0
  capture_output: true
  uptime_kuma:
    token: cmdcheck-token
"""
        )

        config.load_from_yaml(str(yaml_file))

        assert config.cmdcheck_command == "test -f /tmp/file"
        assert config.cmdcheck_timeout == 60
        assert config.cmdcheck_expect_exit_code == 0
        assert config.cmdcheck_capture_output is True
        assert config.command_token == "cmdcheck-token"

    def test_load_multiple_commands_from_yaml(self, config, tmp_path):
        """Test loading multiple commands from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            """
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  multiple: true
  commands:
    - command: "systemctl is-active service1"
      name: service1
      timeout: 10
    - command: "systemctl is-active service2"
      name: service2
      timeout: 15
  uptime_kuma:
    token: cmdcheck-token
"""
        )

        config.load_from_yaml(str(yaml_file))

        assert config.cmdcheck_multiple is True
        assert len(config.cmdcheck_commands) == 2
        assert config.cmdcheck_commands[0]["command"] == "systemctl is-active service1"
        assert config.cmdcheck_commands[0]["name"] == "service1"
        assert config.cmdcheck_commands[0]["timeout"] == 10

    def test_load_patterns_from_yaml(self, config, tmp_path):
        """Test loading regex patterns from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            """
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  command: "tail -n 100 /var/log/app.log"
  success_pattern: "^healthy"
  failure_pattern: "ERROR|CRITICAL"
  uptime_kuma:
    token: cmdcheck-token
"""
        )

        config.load_from_yaml(str(yaml_file))

        assert config.cmdcheck_success_pattern == "^healthy"
        assert config.cmdcheck_failure_pattern == "ERROR|CRITICAL"

    def test_yaml_file_not_found(self, config):
        """Test handling of missing YAML file."""
        with pytest.raises(FileNotFoundError):
            config.load_from_yaml("/nonexistent/config.yaml")

    def test_yaml_parse_error(self, config, tmp_path):
        """Test handling of invalid YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("invalid: yaml: content: [")

        with pytest.raises(RuntimeError):
            config.load_from_yaml(str(yaml_file))


class TestCLIArgumentLoading:
    """Test CLI argument loading."""

    def test_load_single_command_from_args(self, config):
        """Test loading single command from CLI args."""
        args = {
            "command": "test -f /tmp/file",
            "timeout": 60,
            "expect_exit_code": 0,
        }

        config.load_from_args(args)

        assert config.cmdcheck_command == "test -f /tmp/file"
        assert config.cmdcheck_timeout == 60
        # Token is not loaded from args (it comes from positional args or env vars)
        assert config.command_token is None

    def test_load_multiple_commands_from_args(self, config):
        """Test loading multiple commands from CLI args (tuple conversion)."""
        # Simulate what Click provides for multiple=True
        args = {
            "commands": ("echo test", "grep test"),
            "timeout": 30,
        }

        config.load_from_args(args)

        # Should convert tuple to list of dicts
        assert len(config.cmdcheck_commands) == 2
        assert config.cmdcheck_commands[0]["command"] == "echo test"
        assert config.cmdcheck_commands[1]["command"] == "grep test"

    def test_empty_args_dont_override_defaults(self, config):
        """Test empty args don't override YAML/env values."""
        # Set initial value from YAML
        config.cmdcheck_timeout = 60

        # Load args with empty values
        args = {"timeout": None}

        config.load_from_args(args)

        # Should keep previous value
        assert config.cmdcheck_timeout == 60

    def test_load_patterns_from_args(self, config):
        """Test loading patterns from CLI args."""
        args = {
            "command": "test",
            "success_pattern": "OK",
            "failure_pattern": "FAIL",
        }

        config.load_from_args(args)

        assert config.cmdcheck_success_pattern == "OK"
        assert config.cmdcheck_failure_pattern == "FAIL"


class TestEnvironmentVariables:
    """Test environment variable loading."""

    def test_load_from_env(self, config, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("KUMA_SENTINEL_CMDCHECK_TIMEOUT", "120")
        monkeypatch.setenv("KUMA_SENTINEL_CMDCHECK_EXPECT_EXIT_CODE", "1")
        monkeypatch.setenv("KUMA_SENTINEL_CMDCHECK_CAPTURE_OUTPUT", "false")

        config.load_from_env()

        assert config.cmdcheck_timeout == 120
        assert config.cmdcheck_expect_exit_code == 1
        assert config.cmdcheck_capture_output is False

    def test_env_vars_override_yaml(self, config, tmp_path, monkeypatch):
        """Test environment variables override YAML config."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            """
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  command: "test -f /tmp/file"
  timeout: 60
  uptime_kuma:
    token: cmdcheck-token
"""
        )

        monkeypatch.setenv("KUMA_SENTINEL_CMDCHECK_TIMEOUT", "120")

        config.load_from_yaml(str(yaml_file))
        config.load_from_env()

        # Env var value should override YAML (higher precedence)
        assert config.cmdcheck_timeout == 120

    def test_cli_args_override_yaml_and_env(self, config, tmp_path, monkeypatch):
        """Test CLI args override YAML and env vars."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            """
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  command: "test -f /tmp/file"
  timeout: 60
  uptime_kuma:
    token: cmdcheck-token
"""
        )

        monkeypatch.setenv("KUMA_SENTINEL_CMDCHECK_TIMEOUT", "120")

        config.load_from_yaml(str(yaml_file))
        config.load_from_env()

        # Override with CLI args
        config.load_from_args({"timeout": 90})

        # CLI should win
        assert config.cmdcheck_timeout == 90


class TestValidation:
    """Test configuration validation."""

    def test_validate_requires_command(self, config):
        """Test validation requires either command or commands."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = None
        config.cmdcheck_commands = []

        with pytest.raises(ValueError, match="Must specify either"):
            config.validate()

    def test_validate_cannot_have_both_command_and_commands(self, config):
        """Test cannot have both single and multiple commands."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test"
        config.cmdcheck_commands = [{"command": "test"}]

        with pytest.raises(ValueError, match="Cannot specify both"):
            config.validate()

    def test_validate_timeout_range(self, config):
        """Test timeout must be 1-300 seconds."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test"
        config.cmdcheck_timeout = 0

        with pytest.raises(ValueError, match="Timeout must be"):
            config.validate()

        config.cmdcheck_timeout = 301

        with pytest.raises(ValueError, match="Timeout must be"):
            config.validate()

    def test_validate_exit_code_range(self, config):
        """Test exit code must be 0-255."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test"
        config.cmdcheck_expect_exit_code = 256

        with pytest.raises(ValueError, match="Exit code must be"):
            config.validate()

    def test_validate_success_pattern_regex(self, config):
        """Test success pattern must be valid regex."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test"
        config.cmdcheck_success_pattern = "[invalid("

        with pytest.raises(ValueError, match="success_pattern.*regex"):
            config.validate()

    def test_validate_failure_pattern_regex(self, config):
        """Test failure pattern must be valid regex."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test"
        config.cmdcheck_failure_pattern = "[invalid("

        with pytest.raises(ValueError, match="failure_pattern.*regex"):
            config.validate()

    def test_validate_multiple_commands_fields(self, config):
        """Test validation of individual commands."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [{"command": ""}]  # Empty command

        with pytest.raises(ValueError, match="empty command"):
            config.validate()

    def test_validate_per_command_timeout(self, config):
        """Test per-command timeout validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [{"command": "test", "timeout": 400}]

        with pytest.raises(ValueError, match="timeout must be"):
            config.validate()

    def test_validate_per_command_exit_code(self, config):
        """Test per-command exit code validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [{"command": "test", "expect_exit_code": 256}]

        with pytest.raises(ValueError, match="exit code must be"):
            config.validate()

    def test_validate_per_command_patterns(self, config):
        """Test per-command pattern validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [
            {"command": "test", "success_pattern": "[invalid("}
        ]

        with pytest.raises(ValueError, match="invalid success_pattern"):
            config.validate()

    def test_valid_single_command_config(self, config):
        """Test valid single command configuration."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_command = "test -f /tmp/file"

        # Should not raise
        config.validate()

    def test_valid_multiple_commands_config(self, config):
        """Test valid multiple commands configuration."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [
            {"command": "true", "name": "cmd1"},
            {"command": "true", "name": "cmd2"},
        ]

        # Should not raise
        config.validate()


class TestGetSummary:
    """Test configuration summary generation."""

    def test_summary_single_command(self, config):
        """Test summary for single command configuration."""
        config.cmdcheck_command = "test -f /tmp/file"
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "🔧 Command Configuration" in summary
        assert summary["🔧 Command Configuration"]["Mode"] == "Single"
        assert "test -f /tmp/file" in str(summary)

    def test_summary_multiple_commands(self, config):
        """Test summary for multiple commands configuration."""
        config.cmdcheck_multiple = True
        config.cmdcheck_commands = [
            {"command": "true"},
            {"command": "true"},
            {"command": "true"},
        ]
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "🔧 Command Configuration" in summary
        assert summary["🔧 Command Configuration"]["Mode"] == "Multiple"
        assert "3 commands" in str(summary)

    def test_summary_masks_token(self, config):
        """Test token masking in summary."""
        config.cmdcheck_command = "test"
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "***" in str(summary)
        assert "secret-token" not in str(summary)

    def test_summary_unmask_token(self, config):
        """Test unmasked token in summary."""
        config.cmdcheck_command = "test"
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=False)

        assert "secret-token" in str(summary)

    def test_summary_with_patterns(self, config):
        """Test summary includes patterns."""
        config.cmdcheck_command = "tail /var/log/app.log"
        config.cmdcheck_success_pattern = "^healthy"
        config.cmdcheck_failure_pattern = "ERROR|CRITICAL"

        summary = config.get_summary()

        assert "^healthy" in str(summary)
        assert "ERROR|CRITICAL" in str(summary)

    def test_summary_truncates_long_command(self, config):
        """Test long commands are truncated in summary."""
        long_cmd = "x" * 100
        config.cmdcheck_command = long_cmd

        summary = config.get_summary()

        # Should truncate to 60 chars + "..."
        command_display = summary["🔧 Command Configuration"]["Command(s)"]
        assert len(command_display) < len(long_cmd)
        assert "..." in command_display


class TestCommandsConverter:
    """Test the commands converter function."""

    def test_converts_list_of_dicts(self, config):
        """Test converting list of dicts."""
        input_list = [
            {"command": "test1", "timeout": 10},
            {"command": "test2", "timeout": 20},
        ]

        result = config._commands_converter(input_list)

        assert len(result) == 2
        assert result[0]["command"] == "test1"
        assert result[0]["timeout"] == 10

    def test_converts_list_of_tuples(self, config):
        """Test converting list of tuples."""
        input_list = [("test1", {"timeout": 10}), ("test2", {"timeout": 20})]

        result = config._commands_converter(input_list)

        assert len(result) == 2
        assert result[0]["command"] == "test1"

    def test_converts_list_of_strings(self, config):
        """Test converting list of command tuples to dicts."""
        # Converter expects dicts or tuples like Click would provide
        input_list = [("test1",), ("test2",), ("test3",)]

        result = config._commands_converter(input_list)

        assert len(result) == 3
        assert all(isinstance(cmd, dict) for cmd in result)
        assert result[0]["command"] == "test1"
        assert result[1]["command"] == "test2"
        assert result[2]["command"] == "test3"

    def test_handles_none_input(self, config):
        """Test converter handles None gracefully."""
        result = config._commands_converter(None)

        assert result == []

    def test_handles_empty_list(self, config):
        """Test converter handles empty list."""
        result = config._commands_converter([])

        assert result == []
