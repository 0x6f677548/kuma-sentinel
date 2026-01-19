"""Tests for configuration."""

import os
import tempfile

import pytest

from kuma_sentinel.core.config import DEFAULT_PORTSCAN_NMAP_PORTS, Config


def test_config_defaults():
    """Test configuration defaults."""
    config = Config()
    assert config.portscan_nmap_ports == DEFAULT_PORTSCAN_NMAP_PORTS
    assert config.portscan_nmap_timing == "T3"
    assert config.heartbeat_enabled is True
    assert config.heartbeat_interval == 300


def test_config_load_from_env(monkeypatch):
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_PORTS", "22,80,443")
    monkeypatch.setenv("KUMA_SENTINEL_PORTSCAN_NMAP_TIMING", "T4")

    config = Config()
    config.load_from_env()

    assert config.portscan_nmap_ports == "22,80,443"
    assert config.portscan_nmap_timing == "T4"


def test_config_load_from_ini():
    """Test loading configuration from INI file."""
    ini_content = """[logging]
log_file = /tmp/test.log

[heartbeat]
enabled = true
interval = 600

[uptime_kuma]
url = http://localhost/api/push

[heartbeat.uptime_kuma]
token = test_heartbeat

[portscan.uptime_kuma]
token = test_portscan

[portscan.nmap]
timing = T2

[portscan.targets]
ports = 1-10000
exclude_ips = 192.168.1.1
ip_ranges = 192.168.1.0/24,10.0.0.0/8
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(ini_content)
        f.flush()
        config_file = f.name

    try:
        config = Config()
        config.load_from_ini(config_file)

        assert config.log_file == "/tmp/test.log"
        assert config.portscan_nmap_ports == "1-10000"
        assert config.portscan_nmap_timing == "T2"
        assert config.portscan_exclude_ips == "192.168.1.1"
        assert config.heartbeat_interval == 600
        assert config.portscan_ip_ranges == ["192.168.1.0/24", "10.0.0.0/8"]
        assert config.uptime_kuma_url == "http://localhost/api/push"
        assert config.heartbeat_token == "test_heartbeat"
        assert config.portscan_token == "test_portscan"
    finally:
        os.unlink(config_file)


def test_config_validation_missing_ip_ranges():
    """Test validation fails without IP ranges."""
    config = Config()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.portscan_token = "token2"

    with pytest.raises(ValueError, match="No IP ranges specified"):
        config.validate()


def test_config_validation_missing_url():
    """Test validation fails without URL."""
    config = Config()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.heartbeat_token = "token1"
    config.portscan_token = "token2"

    with pytest.raises(ValueError, match="Uptime Kuma URL not provided"):
        config.validate()


def test_config_validation_invalid_timing():
    """Test validation fails with invalid timing."""
    config = Config()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.portscan_token = "token2"
    config.portscan_nmap_timing = "T9"

    with pytest.raises(ValueError, match="Invalid timing level"):
        config.validate()


def test_config_get_summary():
    """Test configuration summary generation."""
    config = Config()
    config.portscan_ip_ranges = ["192.168.1.0/24"]
    config.heartbeat_token = "secret"
    config.portscan_token = "token"

    summary = config.get_summary(mask_tokens=True)
    assert summary["heartbeat_token"] == "***"
    assert summary["portscan_token"] == "***"

    summary = config.get_summary(mask_tokens=False)
    assert summary["heartbeat_token"] == "secret"
    assert summary["portscan_token"] == "token"
