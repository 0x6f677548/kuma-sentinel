"""Tests for configuration loading with proper precedence and edge cases."""

from kuma_sentinel.core.config.portscan_config import PortscanConfig


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
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]
        assert config.portscan_exclude == []

        # Simulate Click's behavior when multiple=True option not provided
        # Click returns empty tuple () for unprovided multiple options
        args_from_click = {
            "config": "example.config.yaml",
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
        config.load_from_yaml("example.config.yaml")
        assert config.portscan_ip_ranges == ["192.168.100.110-199"]

        # Simulate Click providing actual arguments (as tuples)
        args_from_click = {
            "config": "example.config.yaml",
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
        config.load_from_yaml("example.config.yaml")
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
        config.load_from_yaml("example.config.yaml")
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
        config.load_from_yaml("example.config.yaml")
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
        config.load_from_yaml("example.config.yaml")
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
