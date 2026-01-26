"""Tests for kopia snapshot configuration."""

import os
import tempfile

import pytest
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


# ============================================================================
# Error Path & Edge Case Tests - Missing Coverage
# ============================================================================


def test_snapshot_converter_empty_input():
    """Test _snapshot_converter with empty/None input."""
    converter = KopiaSnapshotConfig._snapshot_converter

    assert converter(None) == []
    assert converter("") == []
    assert converter([]) == []
    assert converter(()) == []


def test_snapshot_converter_string_format_valid():
    """Test _snapshot_converter with valid string format."""
    converter = KopiaSnapshotConfig._snapshot_converter

    result = converter("/data:24,/backups:48")
    assert result == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]


def test_snapshot_converter_string_format_with_spaces():
    """Test _snapshot_converter handles whitespace in string format."""
    converter = KopiaSnapshotConfig._snapshot_converter

    result = converter("  /data:24  ,  /backups:48  ")
    assert result == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]


def test_snapshot_converter_string_format_invalid_age():
    """Test _snapshot_converter skips entries with invalid age."""
    converter = KopiaSnapshotConfig._snapshot_converter

    # String with invalid age values - should skip those entries
    result = converter("/data:24,/backups:invalid,/logs:48")
    assert result == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/logs", "max_age_hours": 48},
    ]


def test_snapshot_converter_string_format_path_without_age():
    """Test _snapshot_converter handles paths without age specification."""
    converter = KopiaSnapshotConfig._snapshot_converter

    result = converter("/data,/backups:48")
    assert result == [
        {"path": "/data"},
        {"path": "/backups", "max_age_hours": 48},
    ]


def test_snapshot_converter_string_format_colon_in_path():
    """Test _snapshot_converter handles colons in paths (e.g., Windows paths)."""
    converter = KopiaSnapshotConfig._snapshot_converter

    # Splits from right, so C:data:24 becomes C:data as path and 24 as age
    result = converter("C:data:24")
    assert result == [
        {"path": "C:data", "max_age_hours": 24},
    ]


def test_snapshot_converter_list_of_dicts():
    """Test _snapshot_converter with already-converted list of dicts (YAML)."""
    converter = KopiaSnapshotConfig._snapshot_converter

    input_list = [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]
    result = converter(input_list)
    assert result == input_list


def test_snapshot_converter_click_tuples():
    """Test _snapshot_converter with Click tuple format."""
    converter = KopiaSnapshotConfig._snapshot_converter

    input_tuples = (("/data", 24), ("/backups", 48))
    result = converter(input_tuples)
    assert result == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]


def test_snapshot_converter_invalid_tuple_format():
    """Test _snapshot_converter with invalid tuple format returns empty list."""
    converter = KopiaSnapshotConfig._snapshot_converter

    # Invalid tuple format (wrong number of elements, non-numeric age, etc.)
    result = converter((("/data",),))  # Only one element per tuple
    assert result == []


def test_snapshot_converter_empty_string_items():
    """Test _snapshot_converter handles empty items in comma-separated string."""
    converter = KopiaSnapshotConfig._snapshot_converter

    result = converter("/data:24,,/backups:48,")
    assert result == [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]


def test_kopia_config_load_snapshots_from_env_with_defaults():
    """Test loading snapshots from env and using default max_age_hours."""
    config = KopiaSnapshotConfig()
    config.kopiasnapshotstatus_max_age_hours = 36
    config.load_from_args({"snapshots": (("/data", 24), ("/backups", None))})

    assert config.kopiasnapshotstatus_snapshots[0] == {
        "path": "/data",
        "max_age_hours": 24,
    }


def test_kopia_config_get_summary_with_snapshots():
    """Test get_summary includes formatted snapshot information."""
    config = KopiaSnapshotConfig()
    config.kopiasnapshotstatus_snapshots = [
        {"path": "/data", "max_age_hours": 24},
        {"path": "/backups", "max_age_hours": 48},
    ]
    config.kopiasnapshotstatus_max_age_hours = 24
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary(mask_tokens=True)

    assert "/data@24h" in summary["kopiasnapshotstatus_snapshots"]
    assert "/backups@48h" in summary["kopiasnapshotstatus_snapshots"]
    assert summary["heartbeat_token"] == "***"
    assert summary["kopiasnapshotstatus_token"] == "***"


def test_kopia_config_get_summary_without_snapshots():
    """Test get_summary shows defaults message when no snapshots configured."""
    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "hb_token"
    config.command_token = "cmd_token"

    summary = config.get_summary()

    assert "(using defaults)" in summary["kopiasnapshotstatus_snapshots"]


def test_kopia_config_validation_success(monkeypatch):
    """Test validation succeeds with all required fields."""
    monkeypatch.setenv("KUMA_SENTINEL_HEARTBEAT_TOKEN", "heartbeat_token_123")
    monkeypatch.setenv("KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN", "command_token_456")

    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = (
        "http://kuma:3001/api/push"  # Set directly since not in env vars
    )
    config.load_from_env()

    # Should not raise
    config.validate()


def test_kopia_config_validation_missing_url():
    """Test validation fails when URL is missing."""
    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = None
    config.heartbeat_token = "token"
    config.command_token = "token"

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Uptime Kuma URL" in str(exc_info.value)


def test_kopia_config_validation_missing_heartbeat_token():
    """Test validation fails when heartbeat token is missing."""
    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = "http://kuma"
    config.heartbeat_token = None
    config.command_token = "token"

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Heartbeat push token" in str(exc_info.value)


def test_kopia_config_validation_missing_command_token():
    """Test validation fails when command token is missing."""
    config = KopiaSnapshotConfig()
    config.uptime_kuma_url = "http://kuma"
    config.heartbeat_token = "token"
    config.command_token = None

    with pytest.raises(ValueError) as exc_info:
        config.validate()

    assert "Command push token" in str(exc_info.value)


def test_kopia_config_yaml_file_not_found():
    """Test loading from non-existent YAML file raises FileNotFoundError."""
    config = KopiaSnapshotConfig()

    with pytest.raises(FileNotFoundError) as exc_info:
        config.load_from_yaml("/nonexistent/path/config.yaml")

    assert "Configuration file not found" in str(exc_info.value)


def test_kopia_config_yaml_invalid_format():
    """Test loading from invalid YAML file raises RuntimeError."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("{ invalid: yaml: content:")
        f.flush()
        config_file = f.name

    try:
        config = KopiaSnapshotConfig()
        with pytest.raises(RuntimeError) as exc_info:
            config.load_from_yaml(config_file)

        assert "Failed to parse config file" in str(exc_info.value)
    finally:
        os.unlink(config_file)
