"""
Configuration loading and validation for Kuma-Scout.

This module handles loading YAML configuration files, validating them against
Pydantic models, and providing filtering logic for check execution.
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml

from kuma_scout.plugins.base import CheckConfig
from kuma_scout.plugins.models import GlobalConfig


def load_config(
    config_path: str, ignore_file_permissions: bool = False
) -> Tuple[GlobalConfig, List[Tuple[str, dict]]]:
    """
    Load and validate configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file
        ignore_file_permissions: Whether to ignore file permission checks

    Returns:
        Tuple of (global_config, checks_list)
        where checks_list is [(plugin_type, config), ...]

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_file = _check_file_exists(config_path)

    if not ignore_file_permissions:
        _check_file_permissions(config_file, config_path)

    raw_config = _load_yaml_config(config_file)
    _parse_ssh_host(raw_config)

    global_config = _parse_global_config(raw_config)
    checks = _parse_checks(raw_config)

    return global_config, checks


def _check_file_exists(config_path: str) -> Path:
    """Check if configuration file exists and return Path object."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    return config_file


def _check_file_permissions(config_file: Path, config_path: str) -> None:
    """Check that configuration file has secure permissions."""
    import stat

    file_stat = config_file.stat()
    # Check if file is world-readable or group-readable when it shouldn't be
    if file_stat.st_mode & (stat.S_IRGRP | stat.S_IROTH):
        raise ValueError(
            f"Configuration file {config_path} has overly permissive permissions. "
            "Remove group/other read permissions (chmod 600) or use --ignore-file-permissions"
        )


def _load_yaml_config(config_file: Path) -> dict:
    """Load YAML configuration and expand environment variables."""
    with open(config_file, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        raw_config = {}

    # Expand environment variables in the raw config
    raw_config = _expand_env_vars(raw_config)
    return raw_config


def _parse_ssh_host(raw_config: dict) -> None:
    """Parse SSH host for user@host format."""
    if "ssh" in raw_config and "host" in raw_config["ssh"]:
        host = raw_config["ssh"]["host"]
        if "@" in host and "user" not in raw_config["ssh"]:
            user, host = host.split("@", 1)
            raw_config["ssh"]["user"] = user
            raw_config["ssh"]["host"] = host


def _parse_global_config(raw_config: dict) -> GlobalConfig:
    """Parse and validate global configuration."""
    try:
        return GlobalConfig(**raw_config)
    except Exception as e:
        raise ValueError(f"Invalid global configuration: {e}") from e


def _parse_checks(raw_config: dict) -> List[Tuple[str, dict]]:
    """Parse and validate checks configuration."""
    checks = []
    raw_checks = raw_config.get("checks", [])

    if not isinstance(raw_checks, list):
        raise ValueError("Configuration 'checks' must be a list")

    for i, raw_check in enumerate(raw_checks):
        if not isinstance(raw_check, dict):
            raise ValueError(f"Check {i} must be a dictionary")

        # Extract plugin type
        plugin_type = raw_check.get("type")
        if not plugin_type:
            raise ValueError(f"Check {i} missing required 'type' field")

        # Remove 'type' from check config
        check_config_data = {k: v for k, v in raw_check.items() if k != "type"}

        # Basic validation - ensure name is present
        if "name" not in check_config_data:
            raise ValueError(f"Check {i} missing required 'name' field")

        checks.append((plugin_type, check_config_data))

    return checks


def _expand_env_vars(data: Any) -> Any:
    """
    Recursively expand environment variables in configuration data.

    Supports ${VAR} and $VAR syntax.
    """
    if isinstance(data, str):
        return os.path.expandvars(data)
    elif isinstance(data, dict):
        return {k: _expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_expand_env_vars(item) for item in data]
    else:
        return data


def filter_checks(
    checks: List[Tuple[str, CheckConfig]],
    names: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    check_type: Optional[str] = None,
    exclude: Optional[List[str]] = None,
) -> List[Tuple[str, CheckConfig]]:
    """
    Filter checks based on name, tags, type, and exclusions.

    Matching logic:
    - If --name is specified, include checks matching those names
    - If --tag is specified, include checks having ANY of those tags
    - If --type is specified, include checks of that type
    - If both --name and --tag specified, include checks matching EITHER
    - --exclude removes checks regardless of other filters

    Args:
        checks: List of (plugin_type, config) tuples
        names: List of check names to include
        tags: List of tags to include
        check_type: Plugin type to include
        exclude: List of check names to exclude

    Returns:
        Filtered list of (plugin_type, config) tuples
    """
    result = []

    for plugin_type, config in checks:
        # Check exclusion first
        if exclude and config.name in exclude:
            continue

        # If no filters, include all
        if not names and not tags and not check_type:
            result.append((plugin_type, config))
            continue

        # Check --name filter
        if names and config.name in names:
            result.append((plugin_type, config))
            continue

        # Check --tag filter
        if tags and any(tag in config.tags for tag in tags):
            result.append((plugin_type, config))
            continue

        # Check --type filter
        if check_type and plugin_type == check_type:
            result.append((plugin_type, config))
            continue

    return result
