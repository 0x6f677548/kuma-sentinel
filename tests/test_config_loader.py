"""
Tests for configuration loading and validation.
"""

import os
import tempfile
from pathlib import Path

import pytest

from kuma_scout.core.config_loader import (
    _expand_env_vars,
    _load_yaml_config,
    filter_checks,
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


class TestLoadConfig:
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
            assert global_config.uptime_kuma.url == "http://test:3001/api/push"
            assert global_config.uptime_kuma.token == "test-token"
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
                assert global_config.uptime_kuma.url == "http://env:3001/api/push"
                assert global_config.uptime_kuma.token == "env-token"
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


class TestFilterChecks:
    """Test check filtering functionality."""

    def create_mock_checks(self):
        """Create mock checks for testing."""
        from kuma_scout.plugins.cmdcheck import CmdCheckConfig

        check1 = CmdCheckConfig(
            name="check1", command="echo hello", tags=["web", "production"]
        )
        check2 = CmdCheckConfig(
            name="check2", command="echo world", tags=["db", "production"]
        )
        check3 = CmdCheckConfig(
            name="check3", command="echo test", tags=["web", "staging"]
        )

        return [
            ("cmdcheck", check1),
            ("cmdcheck", check2),
            ("cmdcheck", check3),
        ]

    def test_filter_by_names(self):
        """Test filtering checks by name."""
        checks = self.create_mock_checks()
        result = filter_checks(checks, names=["check1", "check3"])
        assert len(result) == 2
        assert result[0][1].name == "check1"
        assert result[1][1].name == "check3"

    def test_filter_by_tags(self):
        """Test filtering checks by tags."""
        checks = self.create_mock_checks()
        result = filter_checks(checks, tags=["web"])
        assert len(result) == 2
        assert all("web" in check[1].tags for check in result)

    def test_filter_by_type(self):
        """Test filtering checks by type."""
        checks = self.create_mock_checks()
        result = filter_checks(checks, check_type="cmdcheck")
        assert len(result) == 3  # All are cmdcheck

    def test_filter_exclude(self):
        """Test excluding checks by name."""
        checks = self.create_mock_checks()
        result = filter_checks(checks, exclude=["check2"])
        assert len(result) == 2
        assert all(check[1].name != "check2" for check in result)

    def test_filter_combined(self):
        """Test combined filtering."""
        checks = self.create_mock_checks()
        result = filter_checks(checks, tags=["production"], exclude=["check1"])
        assert len(result) == 1
        assert result[0][1].name == "check2"

    def test_filter_no_filters(self):
        """Test with no filters (should return all)."""
        checks = self.create_mock_checks()
        result = filter_checks(checks)
        assert len(result) == 3
