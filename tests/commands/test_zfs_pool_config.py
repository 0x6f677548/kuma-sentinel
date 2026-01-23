"""Tests for ZFS pool status configuration."""

import os
import tempfile

import pytest
import yaml

from kuma_sentinel.core.config.zfs_pool_config import ZfsPoolStatusConfig


def test_zfs_pool_config_factory():
    """Test direct ZFS pool config instantiation."""
    config = ZfsPoolStatusConfig()
    assert isinstance(config, ZfsPoolStatusConfig)


def test_zfs_pool_config_defaults():
    """Test default configuration values."""
    config = ZfsPoolStatusConfig()

    assert config.zfspoolstatus_pools == []
    assert config.zfspoolstatus_free_space_percent_default == 10


def test_zfs_pool_config_load_from_yaml():
    """Test loading ZFS pool configuration from YAML file with per-pool thresholds."""
    yaml_content = {
        "logging": {"log_file": "/tmp/test.log"},
        "uptime_kuma": {"url": "http://localhost/api/push"},
        "heartbeat": {"uptime_kuma": {"token": "test_heartbeat"}},
        "zfspoolstatus": {
            "pools": [
                {"name": "tank", "free_space_percent_min": 10},
                {"name": "backup", "free_space_percent_min": 20},
            ],
            "free_space_percent_default": 15,
            "uptime_kuma": {"token": "test_zfs"},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(yaml_content, f)
        f.flush()
        config_file = f.name

    try:
        config = ZfsPoolStatusConfig()
        config.load_from_yaml(config_file)

        assert config.log_file == "/tmp/test.log"
        assert config.zfspoolstatus_pools == [
            {"name": "tank", "free_space_percent_min": 10},
            {"name": "backup", "free_space_percent_min": 20},
        ]
        assert config.zfspoolstatus_free_space_percent_default == 15
        assert config.uptime_kuma_url == "http://localhost/api/push"
        assert config.heartbeat_token == "test_heartbeat"
        assert config.command_token == "test_zfs"
    finally:
        os.unlink(config_file)


def test_zfs_pool_config_validation_no_pools():
    """Test validation fails when no pools configured."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = []

    with pytest.raises(ValueError, match="No ZFS pools configured"):
        config.validate()


def test_zfs_pool_config_validation_invalid_threshold():
    """Test validation fails with invalid free space threshold."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = [
        {"name": "tank", "free_space_percent_min": 150},  # Invalid: > 100
    ]
    config.zfspoolstatus_free_space_percent_default = 10

    with pytest.raises(ValueError, match="between 0 and 100"):
        config.validate()


def test_zfs_pool_config_validation_negative_threshold():
    """Test validation fails with negative threshold."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = [
        {"name": "tank", "free_space_percent_min": -5},  # Invalid: negative
    ]
    config.zfspoolstatus_free_space_percent_default = 10

    with pytest.raises(ValueError, match="between 0 and 100"):
        config.validate()


def test_zfs_pool_config_validation_invalid_default_threshold():
    """Test validation fails with invalid default threshold."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = [{"name": "tank"}]
    config.zfspoolstatus_free_space_percent_default = 101  # Invalid: > 100

    with pytest.raises(ValueError, match="between 0 and 100"):
        config.validate()


def test_zfs_pool_config_validation_success():
    """Test successful validation with valid configuration."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup"},  # No explicit threshold
    ]
    config.zfspoolstatus_free_space_percent_default = 15

    # Should not raise
    config.validate()


def test_zfs_pool_config_pool_converter_env_string():
    """Test _pool_converter with environment variable string format."""
    result = ZfsPoolStatusConfig._pool_converter("tank:10,backup:20")

    assert result == [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup", "free_space_percent_min": 20},
    ]


def test_zfs_pool_config_pool_converter_env_string_single():
    """Test _pool_converter with single pool string."""
    result = ZfsPoolStatusConfig._pool_converter("tank:10")

    assert result == [
        {"name": "tank", "free_space_percent_min": 10},
    ]


def test_zfs_pool_config_pool_converter_env_string_no_threshold():
    """Test _pool_converter with pool name only."""
    result = ZfsPoolStatusConfig._pool_converter("tank")

    assert result == [
        {"name": "tank"},
    ]


def test_zfs_pool_config_pool_converter_click_tuples():
    """Test _pool_converter with Click CLI tuples."""
    result = ZfsPoolStatusConfig._pool_converter((("tank", 10), ("backup", 20)))

    assert result == [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup", "free_space_percent_min": 20},
    ]


def test_zfs_pool_config_pool_converter_yaml_list():
    """Test _pool_converter with YAML list format."""
    result = ZfsPoolStatusConfig._pool_converter(
        [
            {"name": "tank", "free_space_percent_min": 10},
            {"name": "backup"},
        ]
    )

    assert result == [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup"},
    ]


def test_zfs_pool_config_pool_converter_empty_string():
    """Test _pool_converter with empty string."""
    result = ZfsPoolStatusConfig._pool_converter("")

    assert result == []


def test_zfs_pool_config_pool_converter_empty_list():
    """Test _pool_converter with empty list."""
    result = ZfsPoolStatusConfig._pool_converter([])

    assert result == []


def test_zfs_pool_config_pool_converter_invalid_type():
    """Test _pool_converter with invalid type."""
    result = ZfsPoolStatusConfig._pool_converter(None)

    assert result == []


def test_zfs_pool_config_get_summary():
    """Test get_summary generates correct summary."""
    config = ZfsPoolStatusConfig()
    config.log_file = "/var/log/test.log"
    config.log_level = "INFO"
    config.uptime_kuma_url = "http://localhost:3001"
    config.heartbeat_enabled = True
    config.heartbeat_interval = 300
    config.heartbeat_token = "secret_heartbeat_token"
    config.command_token = "secret_zfs_token"
    config.zfspoolstatus_pools = [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup", "free_space_percent_min": 20},
    ]
    config.zfspoolstatus_free_space_percent_default = 15

    summary = config.get_summary(mask_tokens=True)

    assert summary["log_file"] == "/var/log/test.log"
    assert summary["log_level"] == "INFO"
    assert summary["zfspoolstatus_pools"] == "tank:10%, backup:20%"
    assert summary["zfspoolstatus_free_space_percent_default"] == "15%"
    assert "***" in summary["heartbeat_token"]
    assert "***" in summary["zfspoolstatus_token"]


def test_zfs_pool_config_get_summary_unmasked_tokens():
    """Test get_summary with tokens unmasked."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost:3001"
    config.heartbeat_token = "secret_heartbeat"
    config.command_token = "secret_zfs"
    config.zfspoolstatus_pools = [{"name": "tank", "free_space_percent_min": 10}]
    config.zfspoolstatus_free_space_percent_default = 10

    summary = config.get_summary(mask_tokens=False)

    assert summary["heartbeat_token"] == "secret_heartbeat"
    assert summary["zfspoolstatus_token"] == "secret_zfs"


def test_zfs_pool_config_get_summary_no_pools():
    """Test get_summary when no pools configured."""
    config = ZfsPoolStatusConfig()
    config.uptime_kuma_url = "http://localhost:3001"
    config.heartbeat_token = "token1"
    config.command_token = "token2"
    config.zfspoolstatus_pools = []
    config.zfspoolstatus_free_space_percent_default = 10

    summary = config.get_summary(mask_tokens=True)

    assert summary["zfspoolstatus_pools"] == "none"


def test_zfs_pool_config_load_args_priority(tmp_path):
    """Test configuration loading priority: CLI args override YAML."""
    # Create YAML with values
    config_file = tmp_path / "config.yaml"
    yaml_content = {
        "zfspoolstatus": {
            "pools": [{"name": "yaml_tank", "free_space_percent_min": 20}],
            "free_space_percent_default": 20,
            "uptime_kuma": {"token": "yaml_token"},
        },
        "uptime_kuma": {"url": "http://localhost"},
        "heartbeat": {"uptime_kuma": {"token": "heartbeat"}},
    }
    with open(config_file, "w") as f:
        yaml.dump(yaml_content, f)

    config = ZfsPoolStatusConfig()
    config.load_from_yaml(str(config_file))

    # Load from args (simulating CLI arguments)
    args = {
        "free_space_percent": 30,
    }
    config.load_from_args(args)

    # CLI arg should override YAML
    assert config.zfspoolstatus_free_space_percent_default == 30
    # YAML pools should remain since not overridden by args
    assert config.zfspoolstatus_pools == [
        {"name": "yaml_tank", "free_space_percent_min": 20}
    ]


def test_zfs_pool_config_env_threshold_parsing():
    """Test environment variable pool string with spaces."""
    # Should handle spaces around pool names and thresholds
    result = ZfsPoolStatusConfig._pool_converter("tank : 10 , backup : 20")

    assert result == [
        {"name": "tank", "free_space_percent_min": 10},
        {"name": "backup", "free_space_percent_min": 20},
    ]
