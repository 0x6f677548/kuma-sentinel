"""Tests for configuration."""

import os
import tempfile

import pytest
import yaml

from kuma_sentinel.core.config.kopia_snapshot_config import KopiaSnapshotConfig
from kuma_sentinel.core.config.portscan_config import (
    PortscanConfig,
)


def test_config_factory():
    """Test direct config instantiation."""
    portscan_cfg = PortscanConfig()
    assert isinstance(portscan_cfg, PortscanConfig)

    kopia_cfg = KopiaSnapshotConfig()
    assert isinstance(kopia_cfg, KopiaSnapshotConfig)


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
        "heartbeat": {"enabled": True, "interval": 600, "uptime_kuma": {"token": "test_heartbeat"}},
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


def test_kopia_config_load_from_yaml():
    """Test loading kopia configuration from YAML file with per-path thresholds."""
    yaml_content = {
        "logging": {"log_file": "/tmp/test.log"},
        "uptime_kuma": {"url": "http://localhost/api/push"},
        "heartbeat": {"uptime_kuma": {"token": "test_heartbeat"}},
        "kopiasnapshotstatus": {
            "snapshots": [
                {"path": "/data", "max_age_hours": 24},
                {"path": "/backups", "max_age_hours": 48},
            ],
            "max_age_hours": 24,
            "uptime_kuma": {"token": "test_kopia"},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        f.flush()
        config_file = f.name

    try:
        config = KopiaSnapshotConfig()
        config.load_from_yaml(config_file)

        assert config.log_file == "/tmp/test.log"
        assert config.kopiasnapshotstatus_snapshots == [
            {"path": "/data", "max_age_hours": 24},
            {"path": "/backups", "max_age_hours": 48},
        ]
        assert config.kopiasnapshotstatus_max_age_hours == 24
        assert config.uptime_kuma_url == "http://localhost/api/push"
        assert config.heartbeat_token == "test_heartbeat"
        assert config.command_token == "test_kopia"
    finally:
        os.unlink(config_file)


def test_kopia_config_validation():
    """Test kopia configuration validation."""
    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"

    # Should not raise - kopia doesn't require snapshot_paths
    config.validate()


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


def test_kopia_config_load_heartbeat_token_from_env(monkeypatch):
    """Test loading heartbeat token from environment variable."""
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "env_heartbeat_token")

    config = KopiaSnapshotConfig()
    config.load_from_env()

    assert config.heartbeat_token == "env_heartbeat_token"


def test_kopia_config_load_kopia_token_from_env(monkeypatch):
    """Test loading kopia snapshot token from environment variable."""
    monkeypatch.setenv("KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN", "env_kopia_token")
    monkeypatch.setenv("KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS", "/data:24,/backups:48")

    config = KopiaSnapshotConfig()
    config.load_from_env()

    assert config.command_token == "env_kopia_token"
    assert config.kopiasnapshotstatus_snapshots == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]


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


def test_token_loading_priority_kopia(monkeypatch, tmp_path):
    """Test token loading priority: CLI > YAML > Env > Defaults for kopia."""
    # Set environment variables
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "env_heartbeat")
    monkeypatch.setenv("KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN", "env_kopia")

    # Create YAML file with tokens
    config_file = tmp_path / "config.yaml"
    yaml_data = {
        "heartbeat": {"uptime_kuma": {"token": "ini_heartbeat"}},
        "kopiasnapshotstatus": {"uptime_kuma": {"token": "ini_kopia"}},
    }
    with open(config_file, "w") as f:
        yaml.dump(yaml_data, f)

    config = KopiaSnapshotConfig()

    # Step 1: Load defaults (implicit in __init__)
    # Both tokens should be None

    # Step 2: Load from environment
    config.load_from_env()
    assert config.heartbeat_token == "env_heartbeat"
    assert config.command_token == "env_kopia"

    # Step 3: Load from YAML (overrides env)
    config.load_from_yaml(str(config_file))
    assert config.heartbeat_token == "ini_heartbeat"
    assert config.command_token == "ini_kopia"  # YAML overrides env

    # Step 4: Load from CLI args (overrides everything)
    config.load_from_args(
        {"heartbeat_token": "cli_heartbeat", "kopiasnapshotstatus_token": "cli_kopia"}
    )
    assert config.heartbeat_token == "cli_heartbeat"
    assert config.command_token == "cli_kopia"
