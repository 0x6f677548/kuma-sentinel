"""Tests for portscan configuration."""

import os
import tempfile

import pytest
import yaml

from kuma_sentinel.core.config.portscan_config import PortscanConfig


def test_portscan_config_factory():
    """Test direct portscan config instantiation."""
    config = PortscanConfig()
    assert isinstance(config, PortscanConfig)


def test_portscan_config_defaults():
    """Test portscan configuration defaults."""
    config = PortscanConfig()
    assert config.portscan_nmap_ports == "1-1000"
    assert config.portscan_nmap_timing == "T3"
    assert config.heartbeat_enabled is True
    assert config.heartbeat_interval == 300


def test_portscan_config_load_from_yaml():
    """Test loading portscan configuration from YAML file."""
    yaml_content = {
        "logging": {"log_file": "/tmp/test.log"},
        "heartbeat": {
            "enabled": True,
            "interval": 600,
            "uptime_kuma": {"token": "test_heartbeat"},
        },
        "uptime_kuma": {"url": "http://localhost/api/push"},
        "portscan": {
            "uptime_kuma": {"token": "test_portscan"},
            "nmap": {"timing": "T2"},
            "ports": "1-10000",
            "exclude": ["192.168.1.1"],
            "ip_ranges": ["192.168.1.0/24", "10.0.0.0/8"],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        f.flush()
        config_file = f.name

    try:
        config = PortscanConfig()
        config.load_from_yaml(config_file)

        assert config.log_file == "/tmp/test.log"
        assert config.portscan_nmap_ports == "1-10000"
        assert config.portscan_nmap_timing == "T2"
        assert config.portscan_exclude == ["192.168.1.1"]
        assert config.heartbeat_interval == 600
        assert config.portscan_ip_ranges == ["192.168.1.0/24", "10.0.0.0/8"]
        assert config.uptime_kuma_url == "http://localhost/api/push"
        assert config.heartbeat_token == "test_heartbeat"
        assert config.command_token == "test_portscan"
    finally:
        os.unlink(config_file)


def test_portscan_config_validation_missing_ip_ranges():
    """Test validation fails without IP ranges."""
    config = PortscanConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"

    with pytest.raises(ValueError, match="No IP ranges specified"):
        config.validate()


def test_portscan_config_validation_missing_url():
    """Test validation fails without URL."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.heartbeat_token = "token1"
    config.command_token = "token2"

    with pytest.raises(ValueError, match="Uptime Kuma URL not provided"):
        config.validate()


def test_portscan_config_validation_invalid_timing():
    """Test validation fails with invalid timing."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.portscan_nmap_timing = "T9"

    with pytest.raises(ValueError, match="Invalid timing level"):
        config.validate()


def test_portscan_config_get_summary():
    """Test portscan configuration summary generation."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.heartbeat_token = "secret"
    config.command_token = "token"
    config.uptime_kuma_url = "http://localhost"

    summary = config.get_summary(mask_tokens=True)
    assert summary["heartbeat_token"] == "***"
    assert summary["portscan_token"] == "***"

    summary = config.get_summary(mask_tokens=False)
    assert summary["heartbeat_token"] == "secret"
    assert summary["portscan_token"] == "token"


def test_portscan_config_load_heartbeat_token_from_env(monkeypatch):
    """Test loading heartbeat token from environment variable."""
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "env_heartbeat_token")

    config = PortscanConfig()
    config.load_from_env()

    assert config.heartbeat_token == "env_heartbeat_token"


def test_portscan_config_load_portscan_token_from_env(monkeypatch):
    """Test loading portscan token from environment variable."""
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_TOKEN", "env_portscan_token")

    config = PortscanConfig()
    config.load_from_env()

    assert config.command_token == "env_portscan_token"


def test_token_loading_priority_portscan(monkeypatch, tmp_path):
    """Test token loading priority: CLI > YAML > Env > Defaults for portscan.

    Priority order:
    1. CLI arguments (highest)
    2. YAML file
    3. Environment variables
    4. Defaults (lowest)
    """
    # Set environment variables
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "env_heartbeat")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_TOKEN", "env_portscan")

    # Create YAML file with tokens
    config_file = tmp_path / "config.yaml"
    yaml_data = {
        "heartbeat": {"uptime_kuma": {"token": "ini_heartbeat"}},
        "portscan": {"uptime_kuma": {"token": "ini_portscan"}},
    }
    with open(config_file, "w") as f:
        yaml.dump(yaml_data, f)

    config = PortscanConfig()

    # Step 1: Load defaults (implicit in __init__)
    # Both tokens should be None

    # Step 2: Load from environment
    config.load_from_env()
    assert config.heartbeat_token == "env_heartbeat"
    assert config.command_token == "env_portscan"

    # Step 3: Load from YAML (overrides env)
    config.load_from_yaml(str(config_file))
    assert config.heartbeat_token == "ini_heartbeat"
    assert config.command_token == "ini_portscan"

    # Step 4: Load from CLI args (overrides everything)
    config.load_from_args(
        {"heartbeat_token": "cli_heartbeat", "portscan_token": "cli_portscan"}
    )
    assert config.heartbeat_token == "cli_heartbeat"
    assert config.command_token == "cli_portscan"


# ============================================================================
# Edge Case & Missing Coverage Tests
# ============================================================================


def test_portscan_config_parse_comma_separated_list_with_list_input():
    """Test _parse_comma_separated_list handles list input directly."""
    config = PortscanConfig()

    input_list = ["192.168.1.0/24", "10.0.0.0/8"]
    result = config._parse_comma_separated_list(input_list)  # type: ignore
    assert result == input_list


def test_portscan_config_parse_comma_separated_list_empty_strings():
    """Test _parse_comma_separated_list filters empty strings."""
    config = PortscanConfig()

    result = config._parse_comma_separated_list("192.168.1.0/24,,10.0.0.0/8,")
    assert result == ["192.168.1.0/24", "10.0.0.0/8"]


def test_portscan_config_load_bool_from_yaml(tmp_path):
    """Test loading boolean flag from YAML."""
    yaml_content = {
        "portscan": {
            "nmap": {"keep_xml_output": True},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        f.flush()
        config_file = f.name

    try:
        config = PortscanConfig()
        config.load_from_yaml(config_file)
        assert config.portscan_nmap_keep_xmloutput is True
    finally:
        os.unlink(config_file)


def test_portscan_config_get_summary_with_exclusions():
    """Test get_summary includes exclusion list."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.portscan_exclude = ["192.168.1.1", "192.168.1.2"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary(mask_tokens=False)

    assert summary["portscan_exclude"] == "192.168.1.1, 192.168.1.2"
    assert summary["portscan_nmap_keep_xmloutput"] is False


def test_portscan_config_get_summary_without_exclusions():
    """Test get_summary shows (none) for empty exclusion list."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary()

    assert summary["portscan_exclude"] == "(none)"


def test_portscan_config_get_summary_without_nmap_arguments():
    """Test get_summary shows (none) for empty nmap arguments."""
    config = PortscanConfig()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary()

    assert summary["portscan_nmap_arguments"] == "(none)"


def test_portscan_config_get_summary_with_nmap_arguments():
    """Test get_summary includes nmap arguments."""
    config = PortscanConfig()
    config.portscan_nmap_arguments = ["-A", "-v"]
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary(mask_tokens=False)

    assert summary["portscan_nmap_arguments"] == ["-A", "-v"]


def test_portscan_config_load_nmap_arguments_from_yaml(tmp_path):
    """Test loading nmap arguments from YAML."""
    yaml_content = {
        "portscan": {
            "nmap": {"arguments": ["-A", "-sV"]},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        f.flush()
        config_file = f.name

    try:
        config = PortscanConfig()
        config.load_from_yaml(config_file)
        assert config.portscan_nmap_arguments == ["-A", "-sV"]
    finally:
        os.unlink(config_file)


def test_portscan_parse_comma_separated_with_list_input():
    """Test _parse_comma_separated_list handles list input directly."""
    config = PortscanConfig()
    # This test specifically covers the isinstance(value, list) branch
    input_list = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
    result = config._parse_comma_separated_list(input_list)  # type: ignore
    assert result == input_list


def test_portscan_parse_comma_separated_edge_cases():
    """Test _parse_comma_separated_list with edge cases."""
    config = PortscanConfig()

    # Only whitespace
    assert config._parse_comma_separated_list("   ,  ,   ") == []

    # Single item
    assert config._parse_comma_separated_list("192.168.1.1") == ["192.168.1.1"]

    # Trailing/leading whitespace
    assert config._parse_comma_separated_list("  192.168.1.1  ,  192.168.1.2  ") == [
        "192.168.1.1",
        "192.168.1.2",
    ]

    # Empty string
    assert config._parse_comma_separated_list("") == []

    # None should be handled
    assert config._parse_comma_separated_list(None) == []  # type: ignore


def test_portscan_config_validation_success(monkeypatch, tmp_path):
    """Test validation succeeds with all required fields."""
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "heartbeat_token_123")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_TOKEN", "command_token_456")

    # Create YAML config with IP ranges since env vars only support tokens
    config_file = tmp_path / "config.yaml"
    yaml_content = {
        "uptime_kuma": {"url": "http://kuma:3001/api/push"},
        "heartbeat": {"uptime_kuma": {"token": "heartbeat_token_123"}},
        "portscan": {
            "ip_ranges": ["192.168.1.0/24"],
            "uptime_kuma": {"token": "command_token_456"},
        },
    }
    with open(config_file, "w") as f:
        yaml.dump(yaml_content, f)

    config = PortscanConfig()
    config.load_from_env()
    config.load_from_yaml(str(config_file))

    # Should not raise
    config.validate()


def test_portscan_config_validation_missing_uptime_url():
    """Test validation fails when URL is missing."""
    config = PortscanConfig()
    config.uptime_kuma_url = None
    config.heartbeat_token = "token"
    config.command_token = "token"

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Uptime Kuma URL" in str(exc_info.value)


def test_portscan_config_validation_missing_heartbeat_token():
    """Test validation fails when heartbeat token is missing."""
    config = PortscanConfig()
    config.uptime_kuma_url = "http://kuma"
    config.heartbeat_token = None
    config.command_token = "token"

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Heartbeat push token" in str(exc_info.value)


def test_portscan_config_validation_missing_command_token():
    """Test validation fails when command token is missing."""
    config = PortscanConfig()
    config.uptime_kuma_url = "http://kuma"
    config.heartbeat_token = "token"
    config.command_token = None

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Command push token" in str(exc_info.value)


def test_portscan_config_yaml_file_not_found():
    """Test loading from non-existent YAML file raises FileNotFoundError."""
    config = PortscanConfig()

    with pytest.raises(FileNotFoundError) as exc_info:
        config.load_from_yaml("/nonexistent/path/config.yaml")

    assert "Configuration file not found" in str(exc_info.value)


def test_portscan_config_yaml_invalid_format():
    """Test loading from invalid YAML file raises RuntimeError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("{ invalid: yaml: content:")
        f.flush()
        config_file = f.name

    try:
        config = PortscanConfig()
        with pytest.raises(RuntimeError) as exc_info:
            config.load_from_yaml(config_file)

        assert "Failed to parse config file" in str(exc_info.value)
    finally:
        os.unlink(config_file)

class TestPortRangeValidation:
    """Test port range validation in PortscanConfig."""

    def test_single_valid_port(self):
        """Test single valid port numbers."""
        PortscanConfig.validate_port_range("80")
        PortscanConfig.validate_port_range("443")
        PortscanConfig.validate_port_range("22")
        PortscanConfig.validate_port_range("1")
        PortscanConfig.validate_port_range("65535")

    def test_valid_port_range(self):
        """Test valid port ranges."""
        PortscanConfig.validate_port_range("1-1000")
        PortscanConfig.validate_port_range("20-25")
        PortscanConfig.validate_port_range("8000-9000")
        PortscanConfig.validate_port_range("443-445")

    def test_comma_separated_ports(self):
        """Test comma-separated ports."""
        PortscanConfig.validate_port_range("22,80,443")
        PortscanConfig.validate_port_range("20,21,22,23,25")
        PortscanConfig.validate_port_range("80,443,8080,8443")

    def test_mixed_ports_and_ranges(self):
        """Test mixed single ports and ranges."""
        PortscanConfig.validate_port_range("20-25,80,443")
        PortscanConfig.validate_port_range("22,80,443-445,3000-3005")
        PortscanConfig.validate_port_range("1-1000,5000-6000,8000-9000")

    def test_empty_port_spec(self):
        """Test empty port specification."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("")
        assert "cannot be empty" in str(exc_info.value)

    def test_port_too_low(self):
        """Test port number below 1."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("0")
        assert "out of range" in str(exc_info.value) or "between 1 and 65535" in str(
            exc_info.value
        )

    def test_port_too_high(self):
        """Test port number above 65535."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("65536")
        assert "out of range" in str(exc_info.value) or "between 1 and 65535" in str(
            exc_info.value
        )

    def test_range_start_too_high(self):
        """Test range where start port is too high."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("65536-65540")
        assert "out of range" in str(exc_info.value)

    def test_range_end_too_high(self):
        """Test range where end port is too high."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("8000-65536")
        assert "out of range" in str(exc_info.value)

    def test_range_reversed(self):
        """Test range where start > end."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("443-80")
        assert "start port" in str(exc_info.value).lower() and "end port" in str(
            exc_info.value
        ).lower()

    def test_invalid_format_letters(self):
        """Test invalid format with letters."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("http")
        assert "Invalid port specification" in str(exc_info.value)

    def test_invalid_format_special_chars(self):
        """Test invalid format with special characters."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("80;443")
        assert "Invalid port specification" in str(exc_info.value)

    def test_invalid_format_spaces(self):
        """Test invalid format with spaces."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("80, 443")
        assert "Invalid port specification" in str(exc_info.value)

    def test_invalid_format_extra_dashes(self):
        """Test invalid format with extra dashes."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("80-90-100")
        assert "Invalid port specification" in str(exc_info.value)

    def test_range_with_non_numeric(self):
        """Test range with non-numeric values."""
        with pytest.raises(ValueError) as exc_info:
            PortscanConfig.validate_port_range("80-abc")
        assert "Invalid port specification" in str(exc_info.value)

    def test_nmap_default_range(self):
        """Test nmap default range."""
        PortscanConfig.validate_port_range("1-1000")

    def test_common_port_combinations(self):
        """Test common port combinations."""
        PortscanConfig.validate_port_range("22,80,443,3000,8000-9000")
        PortscanConfig.validate_port_range("1-65535")

    def test_portscan_config_with_valid_ports(self):
        """Test PortscanConfig validation with valid ports."""
        config = PortscanConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.portscan_ip_ranges = ["192.168.1.0/24"]
        config.portscan_nmap_ports = "1-1000"

        # Should not raise
        config.validate()

    def test_portscan_config_with_invalid_ports(self):
        """Test PortscanConfig validation with invalid ports."""
        config = PortscanConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.portscan_ip_ranges = ["192.168.1.0/24"]
        config.portscan_nmap_ports = "65536"

        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid port specification" in str(exc_info.value)

    def test_portscan_config_with_port_out_of_range(self):
        """Test PortscanConfig with out-of-range port."""
        config = PortscanConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.portscan_ip_ranges = ["192.168.1.0/24"]
        config.portscan_nmap_ports = "80-65540"

        with pytest.raises(ValueError) as exc_info:
            config.validate()
        assert "Invalid port" in str(exc_info.value)

    def test_portscan_config_with_complex_ports(self):
        """Test PortscanConfig with complex port combinations."""
        config = PortscanConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "token1"
        config.command_token = "token2"
        config.portscan_ip_ranges = ["192.168.1.0/24"]
        config.portscan_nmap_ports = "20-25,80,443-445,3000,8000-9000"

        # Should not raise
        config.validate()


class TestConfigPrecedence:
    """Test configuration loading precedence: defaults -> env -> YAML -> args."""

    def test_yaml_preserved_when_click_empty_tuple_provided(self):
        """Test that YAML values are not overridden by Click's empty tuple from multiple=True.

        This is a regression test for the bug where Click's multiple=True option
        returns an empty tuple () when no arguments are provided, which was
        overriding YAML configuration values.

        Loading order should be:
        1. Defaults (set in __init__)
        2. Environment variables
        3. YAML file (highest precedence from non-CLI sources)
        4. CLI arguments (highest overall precedence, but empty tuples should not count)
        """
        # Create config and load from YAML
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]
        assert config.portscan_exclude == []

        # Simulate Click's behavior when multiple=True option not provided
        # Click returns empty tuple () for unprovided multiple options
        args_from_click = {
            "config": "test.config.yaml",
            "log_file": None,
            "uptime_kuma_url": None,
            "heartbeat_token": None,
            "token": None,
            "ip_ranges": (),  # Empty tuple from Click's multiple=True
            "exclude": (),  # Empty tuple from Click's multiple=True
            "ports": None,
            "timing": None,
        }

        # Load from args - should NOT override YAML values with empty tuples
        config.load_from_args(args_from_click)

        # YAML values should be preserved
        assert config.portscan_ip_ranges == [
            "192.168.100.110-199"
        ], "ip_ranges from YAML should not be overridden by empty tuple from CLI"
        assert (
            config.portscan_exclude == []
        ), "exclude from YAML should not be overridden by empty tuple from CLI"

    def test_yaml_overridden_when_click_provided_values(self):
        """Test that CLI arguments DO override YAML when values are provided."""
        # Create config and load from YAML
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]

        # Simulate Click providing actual arguments (as tuples)
        args_from_click = {
            "config": "test.config.yaml",
            "log_file": None,
            "uptime_kuma_url": None,
            "heartbeat_token": None,
            "token": None,
            "ip_ranges": ("10.0.0.0/8",),  # Provided tuple from CLI
            "exclude": ("10.0.0.1",),  # Provided tuple from CLI
            "ports": None,
            "timing": None,
        }

        # Load from args - SHOULD override YAML values when provided
        config.load_from_args(args_from_click)

        # CLI values should override YAML
        assert config.portscan_ip_ranges == [
            "10.0.0.0/8"
        ], "ip_ranges should be overridden by CLI arguments when provided"
        assert config.portscan_exclude == [
            "10.0.0.1"
        ], "exclude should be overridden by CLI arguments when provided"

    def test_timing_string_preserved_when_click_not_provided(self):
        """Test that string values from YAML are preserved when Click provides None."""
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_nmap_timing == "T5"

        # Simulate Click not providing timing argument
        args_from_click = {
            "timing": None,
            "ports": None,
            "ip_ranges": (),
            "exclude": (),
        }

        config.load_from_args(args_from_click)

        # YAML timing should be preserved
        assert (
            config.portscan_nmap_timing == "T5"
        ), "timing from YAML should be preserved when CLI provides None"

    def test_string_value_overridden_when_provided(self):
        """Test that string CLI arguments override YAML values."""
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_nmap_timing == "T5"

        # Simulate Click providing timing argument
        args_from_click = {
            "timing": "T0",
            "ports": None,
            "ip_ranges": (),
            "exclude": (),
        }

        config.load_from_args(args_from_click)

        # CLI timing should override YAML
        assert (
            config.portscan_nmap_timing == "T0"
        ), "timing should be overridden by CLI arguments when provided"

    def test_ports_string_preserved_when_click_not_provided(self):
        """Test that comma-separated string ports from YAML are preserved."""
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_nmap_ports == "1-1000"

        args_from_click = {
            "ports": None,
            "timing": None,
            "ip_ranges": (),
            "exclude": (),
        }

        config.load_from_args(args_from_click)

        # YAML ports should be preserved
        assert (
            config.portscan_nmap_ports == "1-1000"
        ), "ports from YAML should be preserved when CLI provides None"

    def test_ports_string_overridden_when_provided(self):
        """Test that CLI ports argument overrides YAML."""
        config = PortscanConfig()
        config.load_from_yaml("test.config.yaml")
        assert config.portscan_nmap_ports == "1-1000"

        args_from_click = {
            "ports": "22,80,443",
            "timing": None,
            "ip_ranges": (),
            "exclude": (),
        }

        config.load_from_args(args_from_click)

        # CLI ports should override YAML
        assert (
            config.portscan_nmap_ports == "22,80,443"
        ), "ports should be overridden by CLI arguments when provided"

        config.validate()
