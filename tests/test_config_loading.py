"""Tests for configuration loading with proper precedence and edge cases."""

from typing import Any, Dict

import pytest

from kuma_scout.core.config.portscan_config import PortscanConfig


class TestConfigPrecedence:
    """Test configuration loading precedence: defaults -> env -> YAML -> args."""

    def test_yaml_preserved_when_typer_empty_list_provided(self):
        """Test that YAML values are not overridden by Typer's empty list from List[] types.

        This is a regression test for the bug where Typer's List[] option
        returns an empty list [] when no arguments are provided, which was
        overriding YAML configuration values.

        Loading order should be:
        1. Defaults (set in __init__)
        2. Environment variables
        3. YAML file (highest precedence from non-CLI sources)
        4. CLI arguments (highest overall precedence, but empty lists should not count)
        """
        # Create config and load from YAML
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]
        assert config.portscan_exclude == []

        # Simulate Typer's behavior when List[] option not provided
        # Typer returns empty list [] for unprovided list options
        args_from_typer: Dict[str, Any] = {
            "config": "example.config.yaml",
            "log_file": None,
            "uptime_kuma_url": None,
            "heartbeat_token": None,
            "token": None,
            "ip_ranges": [],  # Empty list from Typer's List[] type
            "exclude": [],  # Empty list from Typer's List[] type
            "ports": None,
            "timing": None,
        }

        # Load from args - should NOT override YAML values with empty lists
        config.load_from_args(args_from_typer)

        # YAML values should be preserved
        assert config.portscan_ip_ranges == [
            "192.168.100.110-199"
        ], "ip_ranges from YAML should not be overridden by empty list from CLI"
        assert (
            config.portscan_exclude == []
        ), "exclude from YAML should not be overridden by empty list from CLI"

    def test_yaml_overridden_when_typer_provided_values(self):
        """Test that CLI arguments DO override YAML when values are provided."""
        # Create config and load from YAML
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]

        # Simulate Typer providing actual arguments (as lists)
        args_from_typer: Dict[str, Any] = {
            "config": "example.config.yaml",
            "log_file": None,
            "uptime_kuma_url": None,
            "heartbeat_token": None,
            "token": None,
            "ip_ranges": ["10.0.0.0/8"],  # Provided list from CLI
            "exclude": ["10.0.0.1"],  # Provided list from CLI
            "ports": None,
            "timing": None,
        }

        # Load from args - SHOULD override YAML values when provided
        config.load_from_args(args_from_typer)

        # CLI values should override YAML
        assert config.portscan_ip_ranges == [
            "10.0.0.0/8"
        ], "ip_ranges should be overridden by CLI arguments when provided"
        assert config.portscan_exclude == [
            "10.0.0.1"
        ], "exclude should be overridden by CLI arguments when provided"

    def test_timing_string_preserved_when_typer_not_provided(self):
        """Test that string values from YAML are preserved when Typer provides None."""
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_nmap_timing == "T5"

        # Simulate Typer not providing timing argument
        args_from_typer: Dict[str, Any] = {
            "timing": None,
            "ports": None,
            "ip_ranges": [],
            "exclude": [],
        }

        config.load_from_args(args_from_typer)

        # YAML timing should be preserved
        assert (
            config.portscan_nmap_timing == "T5"
        ), "timing from YAML should be preserved when CLI provides None"

    def test_string_value_overridden_when_provided(self):
        """Test that string CLI arguments override YAML values."""
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_nmap_timing == "T5"

        # Simulate Typer providing timing argument
        args_from_typer: Dict[str, Any] = {
            "timing": "T0",
            "ports": None,
            "ip_ranges": [],
            "exclude": [],
        }

        config.load_from_args(args_from_typer)

        # CLI timing should override YAML
        assert (
            config.portscan_nmap_timing == "T0"
        ), "timing should be overridden by CLI arguments when provided"

    def test_ports_string_preserved_when_typer_not_provided(self):
        """Test that comma-separated string ports from YAML are preserved."""
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_nmap_ports == "1-1000"

        args_from_typer: Dict[str, Any] = {
            "ports": None,
            "timing": None,
            "ip_ranges": [],
            "exclude": [],
        }

        config.load_from_args(args_from_typer)

        # YAML ports should be preserved
        assert (
            config.portscan_nmap_ports == "1-1000"
        ), "ports from YAML should be preserved when CLI provides None"

    def test_ports_string_overridden_when_provided(self):
        """Test that CLI ports argument overrides YAML."""
        config = PortscanConfig()
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_nmap_ports == "1-1000"

        args_from_typer: Dict[str, Any] = {
            "ports": "22,80,443",
            "timing": None,
            "ip_ranges": [],
            "exclude": [],
        }

        config.load_from_args(args_from_typer)

        # CLI ports should override YAML
        assert (
            config.portscan_nmap_ports == "22,80,443"
        ), "ports should be overridden by CLI arguments when provided"


class TestSSHConfig:
    """Test SSH configuration parsing from YAML and CLI."""

    def test_yaml_ssh_connection_string_parsing(self):
        """Test that YAML SSH connection strings are parsed correctly."""
        import os
        import tempfile

        yaml_content = """
ssh:
  connection: user@host:2222
  key_file: /path/to/key
portscan:
  ip_ranges: ['192.168.1.0/24']
uptime_kuma:
  url: http://test.com
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            config = PortscanConfig()
            config.load_from_yaml(config_file)

            assert config.ssh_host == "host"
            assert config.ssh_user == "user"
            assert config.ssh_port == 2222
            assert config.ssh_key_file == "/path/to/key"
        finally:
            os.unlink(config_file)

    def test_yaml_command_specific_ssh_override(self):
        """Test that command-specific SSH connection strings override global ones."""
        import os
        import tempfile

        yaml_content = """
ssh:
  connection: global@globalhost:22
portscan:
  ssh:
    connection: command@commandhost:3333
  ip_ranges: ['192.168.1.0/24']
uptime_kuma:
  url: http://test.com
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            config = PortscanConfig()
            config.load_from_yaml(config_file)

            # Command-specific should override global
            assert config.ssh_host == "commandhost"
            assert config.ssh_user == "command"
            assert config.ssh_port == 3333
        finally:
            os.unlink(config_file)

    def test_cli_ssh_connection_string_parsing(self):
        """Test that CLI SSH connection strings are parsed correctly."""
        config = PortscanConfig()

        # Simulate CLI args with SSH connection string
        args = {
            "ssh": "admin@server:2222",
            "ssh_key_file": "/etc/ssh/key",
            "ssh_password": None,
            "ssh_strict_host_key_checking": True,
        }

        config.load_from_args(args)

        assert config.ssh_host == "server"
        assert config.ssh_user == "admin"
        assert config.ssh_port == 2222
        assert config.ssh_key_file == "/etc/ssh/key"

    def test_cli_ssh_connection_string_with_defaults(self):
        """Test CLI SSH parsing with default port."""
        config = PortscanConfig()

        args = {
            "ssh": "user@host",  # No port specified
            "ssh_key_file": None,
            "ssh_password": None,
            "ssh_strict_host_key_checking": True,
        }

        config.load_from_args(args)

        assert config.ssh_host == "host"
        assert config.ssh_user == "user"
        assert config.ssh_port == 22  # Default port

    def test_ssh_config_precedence_cli_overrides_yaml(self):
        """Test that CLI SSH args override YAML configuration."""
        import os
        import tempfile

        yaml_content = """
ssh:
  connection: yaml@yamlhost:22
  key_file: /yaml/key
portscan:
  ip_ranges: ['192.168.1.0/24']
uptime_kuma:
  url: http://test.com
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            config = PortscanConfig()
            config.load_from_yaml(config_file)

            # YAML should be loaded
            assert config.ssh_host == "yamlhost"
            assert config.ssh_key_file == "/yaml/key"

            # CLI should override
            args = {
                "ssh": "cli@clihost:3333",
                "ssh_key_file": "/cli/key",
                "ssh_password": None,
                "ssh_strict_host_key_checking": True,
            }

            config.load_from_args(args)

            assert config.ssh_host == "clihost"
            assert config.ssh_user == "cli"
            assert config.ssh_port == 3333
            assert config.ssh_key_file == "/cli/key"
        finally:
            os.unlink(config_file)


def test_base_config_get_nested_value():
    """Test _get_nested_value method with various paths."""
    from kuma_scout.core.config.base import ConfigBase

    config = ConfigBase()
    data = {"a": {"b": {"c": "value"}}, "list": [1, 2, 3], "empty": {}}

    # Existing nested path
    assert config._get_nested_value(data, "a.b.c") == "value"

    # Non-existing path
    assert config._get_nested_value(data, "a.b.d") is None

    # Top-level key
    assert config._get_nested_value(data, "list") == [1, 2, 3]

    # Empty path
    assert config._get_nested_value(data, "") is None

    # Path to non-dict
    assert config._get_nested_value(data, "list.0") is None


def test_base_config_convert_value():
    """Test _convert_value method with various converters."""
    from kuma_scout.core.config.base import ConfigBase, FieldMapping

    config = ConfigBase()

    # Test int converter on string
    mapping = FieldMapping(arg_key="test", yaml_path="test", converter=int)
    assert config._convert_value("42", mapping) == 42

    # Test str converter on string
    mapping = FieldMapping(arg_key="test", yaml_path="test", converter=str)
    assert config._convert_value("123", mapping) == "123"

    # Test with non-string (should return as-is)
    assert config._convert_value(123, mapping) == 123

    # Test with invalid converter
    def failing_converter(x):
        raise ValueError("conversion failed")

    mapping = FieldMapping(
        arg_key="test", yaml_path="test", converter=failing_converter
    )
    with pytest.raises(ValueError, match="conversion failed"):
        config._convert_value("input", mapping)


def test_base_config_apply_field_mappings_from_yaml_missing_value():
    """Test _apply_field_mappings_from_yaml when yaml value is None."""
    from kuma_scout.core.config.base import ConfigBase

    config = ConfigBase()

    # Test with data that doesn't have the path
    data = {"other": "value"}

    # This should not raise and not set any field
    config._apply_field_mappings_from_yaml(data)
