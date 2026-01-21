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


def test_portscan_config_load_from_env(monkeypatch):
    """Test loading portscan configuration from environment variables."""
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_PORTS", "22,80,443")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_TIMING", "T4")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_IP_RANGES", "192.168.1.0/24,10.0.0.0/8")

    config = PortscanConfig()
    config.load_from_env()

    assert config.portscan_nmap_ports == "22,80,443"
    assert config.portscan_nmap_timing == "T4"
    assert config.portscan_ip_ranges == ["192.168.1.0/24", "10.0.0.0/8"]


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


def test_portscan_config_parse_bool_true_variants(monkeypatch):
    """Test _parse_bool converts various true representations."""
    config = PortscanConfig()

    # Test with environment variable set to various truthy values
    for truthy_value in ["true", "True", "TRUE", "1", "yes", "YES"]:
        monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT", truthy_value)
        config = PortscanConfig()
        config.load_from_env()
        assert config.portscan_nmap_keep_xmloutput is True, f"Failed for {truthy_value}"


def test_portscan_config_parse_bool_false_variants(monkeypatch):
    """Test _parse_bool converts various false representations."""
    config = PortscanConfig()

    # Test with environment variable set to various falsy values
    for falsy_value in ["false", "False", "FALSE", "0", "no", "NO", ""]:
        monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT", falsy_value)
        config = PortscanConfig()
        config.load_from_env()
        assert config.portscan_nmap_keep_xmloutput is False, f"Failed for {falsy_value}"


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


def test_portscan_config_nmap_timeout_int_conversion(monkeypatch):
    """Test nmap timeout is converted to int from environment variable."""
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_TIMEOUT", "7200")

    config = PortscanConfig()
    config.load_from_env()

    assert config.portscan_nmap_timeout == 7200
    assert isinstance(config.portscan_nmap_timeout, int)


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


def test_portscan_config_validation_success(monkeypatch):
    """Test validation succeeds with all required fields."""
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "heartbeat_token_123")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_TOKEN", "command_token_456")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_IP_RANGES", "192.168.1.0/24")

    config = PortscanConfig()
    config.uptime_kuma_url = (
        "http://kuma:3001/api/push"  # Set directly since not in env vars
    )
    config.load_from_env()

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
