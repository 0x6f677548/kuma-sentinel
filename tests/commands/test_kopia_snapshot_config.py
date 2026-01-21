"""Tests for kopia snapshot configuration."""

import os
import tempfile

import yaml

from kuma_sentinel.core.config.kopia_snapshot_config import KopiaSnapshotConfig


def test_kopia_config_factory():
    """Test direct kopia snapshot config instantiation."""
    config = KopiaSnapshotConfig()
    assert isinstance(config, KopiaSnapshotConfig)


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
