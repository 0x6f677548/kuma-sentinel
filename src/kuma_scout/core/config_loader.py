"""
Configuration loading and validation for Kuma-Scout.

This module handles loading YAML configuration files, validating them against
Pydantic models, and parsing check configurations.
"""

import os
from pathlib import Path
from typing import Any, List, Tuple

import yaml

from kuma_scout.core.logger import log_security_event
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
    else:
        # Log security event when permission checks are bypassed
        log_security_event(
            "config_file_permissions_ignored",
            f"Config file permission checks bypassed for {config_path} - file may contain sensitive data with overly permissive access",
            level="warning",
        )

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
        log_security_event(
            "config_file_overly_permissive",
            f"Config file {config_path} has overly permissive permissions (readable by group/other) - contains sensitive data",
            level="error",
        )
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
