"""
Tests for configuration loading and validation.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kuma_scout.core.config_loader import (
    _expand_env_vars,
    _load_yaml_config,
    _parse_checks,
    _parse_ssh_host,
    load_config,
)


class TestExpandEnvVars:
    """Test environment variable expansion functionality."""

    def test_expand_simple_var(self):
        """Test basic $VAR expansion."""
        os.environ["TEST_VAR"] = "expanded_value"
        try:
            result = _expand_env_vars("$TEST_VAR")
            assert result == "expanded_value"
        finally:
            del os.environ["TEST_VAR"]

    def test_expand_brace_var(self):
        """Test ${VAR} expansion."""
        os.environ["TEST_VAR"] = "brace_expanded"
        try:
            result = _expand_env_vars("${TEST_VAR}")
            assert result == "brace_expanded"
        finally:
            del os.environ["TEST_VAR"]

    def test_expand_missing_var(self):
        """Test that missing variables are left unchanged."""
        result = _expand_env_vars("$MISSING_VAR")
        assert result == "$MISSING_VAR"

    def test_expand_in_dict(self):
        """Test expansion in nested dictionary."""
        os.environ["TEST_TOKEN"] = "secret-token"
        try:
            data = {
                "uptime_kuma": {"url": "http://test:3001", "token": "$TEST_TOKEN"},
                "other": "no_expand",
            }
            result = _expand_env_vars(data)
            assert result["uptime_kuma"]["token"] == "secret-token"
            assert result["other"] == "no_expand"
        finally:
            del os.environ["TEST_TOKEN"]

    def test_expand_in_list(self):
        """Test expansion in list."""
        os.environ["TEST_PATH"] = "/tmp/test"
        try:
            data = ["$TEST_PATH", "static_value", {"nested": "$TEST_PATH"}]
            result = _expand_env_vars(data)
            assert result[0] == "/tmp/test"
            assert result[1] == "static_value"
            assert result[2]["nested"] == "/tmp/test"
        finally:
            del os.environ["TEST_PATH"]

    def test_expand_mixed_syntax(self):
        """Test both $VAR and ${VAR} in same data."""
        os.environ["VAR1"] = "value1"
        os.environ["VAR2"] = "value2"
        try:
            data = {
                "token1": "$VAR1",
                "token2": "${VAR2}",
                "list": ["$VAR1", "${VAR2}"],
            }
            result = _expand_env_vars(data)
            assert result["token1"] == "value1"
            assert result["token2"] == "value2"
            assert result["list"] == ["value1", "value2"]
        finally:
            del os.environ["VAR1"]
            del os.environ["VAR2"]

    def test_no_expansion_for_non_strings(self):
        """Test that non-string values are unchanged."""
        data = {
            "number": 42,
            "boolean": True,
            "none": None,
            "list": [1, 2, 3],
            "dict": {"nested": 123},
        }
        result = _expand_env_vars(data)
        assert result == data


class TestLoadYamlConfig:
    """Test YAML config loading with env var expansion."""

    def test_load_with_env_expansion(self):
        """Test that YAML loading expands environment variables."""
        os.environ["TEST_URL"] = "http://expanded:3001"
        os.environ["TEST_TOKEN"] = "expanded-token"
        try:
            yaml_content = """
uptime_kuma:
  url: $TEST_URL
  token: ${TEST_TOKEN}
other:
  static: value
"""
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(yaml_content)
                temp_path = f.name

            try:
                result = _load_yaml_config(Path(temp_path))
                assert result["uptime_kuma"]["url"] == "http://expanded:3001"
                assert result["uptime_kuma"]["token"] == "expanded-token"
                assert result["other"]["static"] == "value"
            finally:
                Path(temp_path).unlink()
        finally:
            del os.environ["TEST_URL"]
            del os.environ["TEST_TOKEN"]

    def test_load_empty_config(self):
        """Test loading empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            result = _load_yaml_config(Path(temp_path))
            assert result == {}
        finally:
            Path(temp_path).unlink()


class TestParseChecks:
    """Test _parse_checks function."""

    def test_parse_checks_invalid_checks_type(self):
        """Test _parse_checks with invalid checks type."""
        with pytest.raises(ValueError, match="must be a list"):
            _parse_checks({"checks": "not a list"})

    def test_parse_checks_check_not_dict(self):
        """Test _parse_checks with check that is not a dict."""
        with pytest.raises(ValueError, match="Check 0 must be a dictionary"):
            _parse_checks({"checks": ["not a dict"]})

    def test_parse_checks_missing_name(self):
        """Test _parse_checks with check missing name."""
        with pytest.raises(ValueError, match="Check 0 missing required 'name' field"):
            _parse_checks({"checks": [{"type": "cmdcheck"}]})

    """Test full config loading functionality."""

    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        config_content = """
uptime_kuma:
  url: http://test:3001/api/push
  token: test-token

logging:
  level: INFO

checks:
  - name: test-check
    type: cmdcheck
    command: echo hello
    timeout: 30
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            global_config, checks = load_config(temp_path, ignore_file_permissions=True)
            uptime_kuma = global_config.uptime_kuma
            assert uptime_kuma is not None
            assert uptime_kuma.url == "http://test:3001/api/push"
            assert uptime_kuma.token == "test-token"
            assert len(checks) == 1
            assert checks[0][0] == "cmdcheck"
            assert checks[0][1]["name"] == "test-check"
        finally:
            Path(temp_path).unlink()

    def test_load_config_with_env_vars(self):
        """Test loading config with environment variable expansion."""
        os.environ["CONFIG_TOKEN"] = "env-token"
        os.environ["CONFIG_URL"] = "http://env:3001"
        try:
            config_content = """
uptime_kuma:
  url: $CONFIG_URL/api/push
  token: ${CONFIG_TOKEN}

checks:
  - name: env-check
    type: cmdcheck
    command: echo $HOME
"""
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(config_content)
                temp_path = f.name

            try:
                global_config, checks = load_config(
                    temp_path, ignore_file_permissions=True
                )
                uptime_kuma = global_config.uptime_kuma
                assert uptime_kuma is not None
                assert uptime_kuma.url == "http://env:3001/api/push"
                assert uptime_kuma.token == "env-token"
                assert len(checks) == 1
                # The command should have $HOME expanded
                assert "$HOME" not in checks[0][1]["command"]  # Should be expanded
            finally:
                Path(temp_path).unlink()
        finally:
            del os.environ["CONFIG_TOKEN"]
            del os.environ["CONFIG_URL"]

    def test_load_config_missing_file(self):
        """Test loading non-existent config file."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config("/nonexistent/path.yaml")

    def test_load_config_invalid_checks(self):
        """Test loading config with invalid checks structure."""
        config_content = """
checks: "not a list"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid global configuration"):
                load_config(temp_path, ignore_file_permissions=True)
        finally:
            Path(temp_path).unlink()

    def test_load_config_missing_type(self):
        """Test loading config with check missing type field."""
        config_content = """
checks:
  - name: test-check
    command: echo hello
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(
                ValueError, match="Check 0 missing required 'type' field"
            ):
                load_config(temp_path, ignore_file_permissions=True)
        finally:
            Path(temp_path).unlink()

    def test_load_config_missing_name(self):
        """Test loading config with check missing name field."""
        config_content = """
checks:
  - type: cmdcheck
    command: echo hello
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(
                ValueError, match="Check 0 missing required 'name' field"
            ):
                load_config(temp_path, ignore_file_permissions=True)
        finally:
            Path(temp_path).unlink()

    @patch("kuma_scout.core.config_loader.log_security_event")
    def test_load_config_ignore_permissions(self, mock_log_security):
        """Test loading config with ignored file permissions."""
        config_content = """
uptime_kuma:
  url: http://test:3001
  token: test-token
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            global_config, checks = load_config(temp_path, ignore_file_permissions=True)
            mock_log_security.assert_called_once_with(
                "config_file_permissions_ignored",
                f"Config file permission checks bypassed for {temp_path} - file may contain sensitive data with overly permissive access",
                level="warning",
            )
        finally:
            Path(temp_path).unlink()

    @patch("kuma_scout.core.config_loader.log_security_event")
    @patch("pathlib.Path.stat")
    def test_load_config_bad_permissions(self, mock_stat, mock_log_security):
        """Test loading config with bad file permissions."""
        # Mock stat to return world-readable permissions
        import stat

        mock_stat.return_value.st_mode = stat.S_IRUSR | stat.S_IROTH  # 0o404

        config_content = """
uptime_kuma:
  url: http://test:3001
  token: test-token
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="has overly permissive permissions"):
                load_config(temp_path, ignore_file_permissions=False)
            mock_log_security.assert_called_once_with(
                "config_file_overly_permissive",
                f"Config file {temp_path} has overly permissive permissions (readable by group/other) - contains sensitive data",
                level="error",
            )
        finally:
            Path(temp_path).unlink()


class TestParseSSHHost:
    """Test SSH host parsing functionality."""

    def test_parse_user_at_host(self):
        """Test parsing user@host format."""
        raw_config = {"ssh": {"host": "user@example.com"}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert raw_config["ssh"]["user"] == "user"

    def test_parse_host_with_port(self):
        """Test parsing host:port format."""
        raw_config = {"ssh": {"host": "example.com:2222"}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert raw_config["ssh"]["port"] == 2222

    def test_parse_user_at_host_with_port(self):
        """Test parsing user@host:port format."""
        raw_config = {"ssh": {"host": "user@example.com:2222"}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert raw_config["ssh"]["user"] == "user"
        assert raw_config["ssh"]["port"] == 2222

    def test_parse_host_only(self):
        """Test parsing host only."""
        raw_config = {"ssh": {"host": "example.com"}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert "user" not in raw_config["ssh"]
        assert "port" not in raw_config["ssh"]

    def test_no_override_existing_user(self):
        """Test that existing user is not overridden."""
        raw_config = {"ssh": {"host": "user@example.com", "user": "existing_user"}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert raw_config["ssh"]["user"] == "existing_user"

    def test_no_override_existing_port(self):
        """Test that existing port is not overridden."""
        raw_config = {"ssh": {"host": "example.com:2222", "port": 22}}
        _parse_ssh_host(raw_config)
        assert raw_config["ssh"]["host"] == "example.com"
        assert raw_config["ssh"]["port"] == 22

    def test_no_ssh_section(self):
        """Test no modification when no ssh section."""
        raw_config = {"other": "value"}
        original = raw_config.copy()
        _parse_ssh_host(raw_config)
        assert raw_config == original

    def test_no_host_in_ssh(self):
        """Test no modification when no host in ssh section."""
        raw_config = {"ssh": {"user": "user"}}
        original = raw_config.copy()
        _parse_ssh_host(raw_config)
        assert raw_config == original
