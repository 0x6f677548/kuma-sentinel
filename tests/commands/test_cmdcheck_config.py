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
        assert config.cmdcheck_commands == []
        assert config.cmdcheck_timeout == 30
        assert config.cmdcheck_expect_exit_code == 0
        assert config.cmdcheck_capture_output is True
        assert config.cmdcheck_success_pattern is None
        assert config.cmdcheck_failure_pattern is None


class TestYAMLLoading:
    """Test YAML configuration loading."""

    def test_load_single_command_from_yaml(self, config, tmp_path):
        """Test loading single command from YAML (always as a list)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("""
logging:
  log_file: /var/log/test.log
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  commands:
    - command: "test -f /tmp/file"
  timeout: 60
  expect_exit_code: 0
  capture_output: true
  uptime_kuma:
    token: cmdcheck-token
""")

        config.load_from_yaml(str(yaml_file))

        assert len(config.cmdcheck_commands) == 1
        assert config.cmdcheck_commands[0]["command"] == "test -f /tmp/file"
        assert config.cmdcheck_timeout == 60
        assert config.cmdcheck_expect_exit_code == 0
        assert config.cmdcheck_capture_output is True
        assert config.command_token == "cmdcheck-token"

    def test_load_multiple_commands_from_yaml(self, config, tmp_path):
        """Test loading multiple commands from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("""
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  commands:
    - command: "systemctl is-active service1"
      name: service1
      timeout: 10
    - command: "systemctl is-active service2"
      name: service2
      timeout: 15
  uptime_kuma:
    token: cmdcheck-token
""")

        config.load_from_yaml(str(yaml_file))

        assert len(config.cmdcheck_commands) == 2
        assert config.cmdcheck_commands[0]["command"] == "systemctl is-active service1"
        assert config.cmdcheck_commands[0]["name"] == "service1"
        assert config.cmdcheck_commands[0]["timeout"] == 10
        assert config.cmdcheck_commands[1]["command"] == "systemctl is-active service2"
        assert config.cmdcheck_commands[1]["name"] == "service2"
        assert config.cmdcheck_commands[1]["timeout"] == 15

    def test_load_patterns_from_yaml(self, config, tmp_path):
        """Test loading regex patterns from YAML."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("""
uptime_kuma:
  url: http://localhost:3001/api/push
heartbeat:
  uptime_kuma:
    token: heartbeat-token
cmdcheck:
  commands:
    - command: "tail -n 100 /var/log/app.log"
  success_pattern: "^healthy"
  failure_pattern: "ERROR|CRITICAL"
  uptime_kuma:
    token: cmdcheck-token
""")

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
        """Test loading single command from CLI args (wrapped as list)."""
        args = {
            "command": "test -f /tmp/file",
            "timeout": 60,
            "expect_exit_code": 0,
        }

        config.load_from_args(args)

        # Single command is wrapped in list
        assert len(config.cmdcheck_commands) == 1
        assert config.cmdcheck_commands[0]["command"] == "test -f /tmp/file"
        assert config.cmdcheck_timeout == 60
        # Token is not loaded from args (it comes from positional args or env vars)
        assert config.command_token is None

    def test_load_multiple_commands_from_args(self, config):
        """Test that CLI args only support single command (not multiple)."""
        # Note: CLI only supports single --command argument
        # For multiple commands, use YAML configuration
        # This test documents that "commands" key from args is not used in CLI
        args = {
            "command": "single command",
            "timeout": 30,
        }

        config.load_from_args(args)

        # Single command is wrapped in list
        assert len(config.cmdcheck_commands) == 1
        assert config.cmdcheck_commands[0]["command"] == "single command"

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

        assert len(config.cmdcheck_commands) == 1
        assert config.cmdcheck_commands[0]["command"] == "test"
        assert config.cmdcheck_success_pattern == "OK"
        assert config.cmdcheck_failure_pattern == "FAIL"


class TestValidation:
    """Test configuration validation."""

    def test_validate_requires_commands(self, config):
        """Test validation requires at least one command."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = []

        with pytest.raises(ValueError, match="Must specify at least one command"):
            config.validate()

    def test_validate_single_command(self, config):
        """Test validation passes with single command in list."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test"}]

        # Should not raise
        config.validate()

    def test_validate_timeout_range(self, config):
        """Test timeout must be 1-300 seconds."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test"}]
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
        config.cmdcheck_commands = [{"command": "test"}]
        config.cmdcheck_expect_exit_code = 256

        with pytest.raises(ValueError, match="Exit code must be"):
            config.validate()

    def test_validate_success_pattern_regex(self, config):
        """Test success pattern must be valid regex."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test"}]
        config.cmdcheck_success_pattern = "[invalid("

        with pytest.raises(ValueError, match="success_pattern.*regex"):
            config.validate()

    def test_validate_failure_pattern_regex(self, config):
        """Test failure pattern must be valid regex."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test"}]
        config.cmdcheck_failure_pattern = "[invalid("

        with pytest.raises(ValueError, match="failure_pattern.*regex"):
            config.validate()

    def test_validate_per_command_missing_command_field(self, config):
        """Test per-command validation requires command field."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"name": "test"}]  # Missing 'command' field

        with pytest.raises(ValueError, match="missing 'command'"):
            config.validate()

    def test_validate_per_command_empty_command(self, config):
        """Test per-command validation rejects empty command."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": ""}]  # Empty command

        with pytest.raises(ValueError, match="empty command"):
            config.validate()

    def test_validate_per_command_timeout(self, config):
        """Test per-command timeout validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test", "timeout": 400}]

        with pytest.raises(ValueError, match="timeout must be"):
            config.validate()

    def test_validate_per_command_exit_code(self, config):
        """Test per-command exit code validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test", "expect_exit_code": 256}]

        with pytest.raises(ValueError, match="exit code must be"):
            config.validate()

    def test_validate_per_command_patterns(self, config):
        """Test per-command pattern validation."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test", "success_pattern": "[invalid("}]

        with pytest.raises(ValueError, match="invalid success_pattern"):
            config.validate()

    def test_valid_single_command_config(self, config):
        """Test valid single command configuration."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
        config.cmdcheck_commands = [{"command": "test -f /tmp/file"}]

        # Should not raise
        config.validate()

    def test_valid_multiple_commands_config(self, config):
        """Test valid multiple commands configuration."""
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_token = "token"
        config.command_token = "token"
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
        config.cmdcheck_commands = [{"command": "test -f /tmp/file"}]
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "🔧 Command Configuration" in summary
        assert "1 command" in str(summary)
        assert "test -f /tmp/file" in str(summary)

    def test_summary_multiple_commands(self, config):
        """Test summary for multiple commands configuration."""
        config.cmdcheck_commands = [
            {"command": "true"},
            {"command": "true"},
            {"command": "true"},
        ]
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "🔧 Command Configuration" in summary
        assert "3 commands" in str(summary)

    def test_summary_masks_token(self, config):
        """Test token masking in summary."""
        config.cmdcheck_commands = [{"command": "test"}]
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=True)

        assert "***" in str(summary)
        assert "secret-token" not in str(summary)

    def test_summary_unmask_token(self, config):
        """Test unmasked token in summary."""
        config.cmdcheck_commands = [{"command": "test"}]
        config.command_token = "secret-token"

        summary = config.get_summary(mask_tokens=False)

        assert "secret-token" in str(summary)

    def test_summary_with_patterns(self, config):
        """Test summary includes patterns."""
        config.cmdcheck_commands = [{"command": "tail /var/log/app.log"}]
        config.cmdcheck_success_pattern = "^healthy"
        config.cmdcheck_failure_pattern = "ERROR|CRITICAL"

        summary = config.get_summary()

        assert "^healthy" in str(summary)
        assert "ERROR|CRITICAL" in str(summary)

    def test_summary_truncates_long_command(self, config):
        """Test long commands are truncated in summary."""
        long_cmd = "x" * 100
        config.cmdcheck_commands = [{"command": long_cmd}]

        summary = config.get_summary()

        # Should truncate to 60 chars + "..."
        command_display = summary["🔧 Command Configuration"]["Command(s)"]
        assert len(command_display) < len(long_cmd)
        assert "..." in command_display


class TestCommandsNormalizer:
    """Test the commands normalizer function."""

    def test_normalizes_single_string(self, config):
        """Test normalizing single command string."""
        result = config._normalize_commands("test command")

        assert len(result) == 1
        assert result[0]["command"] == "test command"

    def test_normalizes_list_of_dicts(self, config):
        """Test normalizing list of dicts."""
        input_list = [
            {"command": "test1", "timeout": 10},
            {"command": "test2", "timeout": 20},
        ]

        result = config._normalize_commands(input_list)

        assert len(result) == 2
        assert result[0]["command"] == "test1"
        assert result[0]["timeout"] == 10

    def test_normalizes_list_of_strings(self, config):
        """Test normalizing list of strings."""
        input_list = ["test1", "test2", "test3"]

        result = config._normalize_commands(input_list)

        assert len(result) == 3
        assert all(isinstance(cmd, dict) for cmd in result)
        assert result[0]["command"] == "test1"
        assert result[1]["command"] == "test2"
        assert result[2]["command"] == "test3"

    def test_normalizes_tuple_input(self, config):
        """Test normalizing tuple input (from Click)."""
        input_tuple = ("test1", "test2", "test3")

        result = config._normalize_commands(input_tuple)

        assert len(result) == 3
        assert result[0]["command"] == "test1"

    def test_handles_none_input(self, config):
        """Test normalizer handles None gracefully."""
        result = config._normalize_commands(None)

        assert result == []

    def test_handles_empty_list(self, config):
        """Test normalizer handles empty list."""
        result = config._normalize_commands([])

        assert result == []


class TestURLValidation:
    """Test Uptime Kuma URL validation."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        from kuma_sentinel.core.config.base import ConfigBase

        ConfigBase.validate_uptime_kuma_url("http://localhost:3001/api/push")
        ConfigBase.validate_uptime_kuma_url("http://uptimekuma.example.com/api/push")
        ConfigBase.validate_uptime_kuma_url("http://192.168.1.1:3001/api/push")

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        from kuma_sentinel.core.config.base import ConfigBase

        ConfigBase.validate_uptime_kuma_url("https://uptimekuma.example.com/api/push")
        ConfigBase.validate_uptime_kuma_url("https://monitoring.acme.com")
        ConfigBase.validate_uptime_kuma_url("https://kuma:3001/api/push")

    def test_empty_url(self):
        """Test empty URL raises error."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("")
        assert "cannot be empty" in str(exc_info.value)

    def test_none_url(self):
        """Test None URL raises error."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url(None)
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_scheme(self):
        """Test URL with invalid scheme."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("ftp://uptimekuma.com/api/push")
        assert "scheme must be 'http' or 'https'" in str(exc_info.value)

    def test_no_scheme(self):
        """Test URL without scheme."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("uptimekuma.com/api/push")
        assert "scheme must be 'http' or 'https'" in str(exc_info.value)

    def test_missing_hostname(self):
        """Test URL without hostname."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("http:///api/push")
        assert "hostname" in str(exc_info.value).lower()

    def test_url_with_spaces(self):
        """Test URL with spaces."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("http://my site.com/api/push")
        assert "spaces" in str(exc_info.value)

    def test_url_with_trailing_slash(self):
        """Test URL with trailing slash."""
        from kuma_sentinel.core.config.base import ConfigBase

        with pytest.raises(ValueError) as exc_info:
            ConfigBase.validate_uptime_kuma_url("http://uptimekuma.com/")
        assert "trailing slash" in str(exc_info.value)

    def test_url_with_query_params(self):
        """Test URL with query parameters."""
        from kuma_sentinel.core.config.base import ConfigBase

        # Should pass - valid URL
        ConfigBase.validate_uptime_kuma_url("http://uptimekuma.com/api/push?token=abc")

    def test_url_with_port(self):
        """Test URL with explicit port."""
        from kuma_sentinel.core.config.base import ConfigBase

        ConfigBase.validate_uptime_kuma_url("http://localhost:3001/api/push")
        ConfigBase.validate_uptime_kuma_url("https://monitoring.io:8443/health")

    def test_url_with_auth(self):
        """Test URL with authentication."""
        from kuma_sentinel.core.config.base import ConfigBase

        ConfigBase.validate_uptime_kuma_url("http://user:pass@uptimekuma.com/api/push")

    def test_cmdcheck_config_with_valid_url(self):
        """Test CmdCheckConfig validation with valid URL."""
        config = CmdCheckConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.cmdcheck_commands = [{"command": "echo test"}]

        # Should not raise
        config.validate()

    def test_cmdcheck_config_with_invalid_url(self):
        """Test CmdCheckConfig validation with invalid URL."""
        config = CmdCheckConfig()
        config.uptime_kuma_url = "ftp://invalid.com"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.cmdcheck_commands = [{"command": "echo test"}]

        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid Uptime Kuma URL" in str(exc_info.value)

    def test_cmdcheck_config_with_malformed_url(self):
        """Test CmdCheckConfig validation with malformed URL."""
        config = CmdCheckConfig()
        config.uptime_kuma_url = "not-a-url"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.cmdcheck_commands = [{"command": "echo test"}]

        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid Uptime Kuma URL" in str(exc_info.value)
