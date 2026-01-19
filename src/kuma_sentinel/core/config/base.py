"""Base configuration management for kuma sentinel."""

import configparser
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


# Declarative field mapping for config loading
@dataclass
class FieldMapping:
    """Declarative mapping for a config field across all loading sources."""

    env_var: Optional[str] = None  # Environment variable name
    arg_key: Optional[str] = None  # CLI argument key
    ini_section: Optional[str] = None  # INI section name
    ini_option: Optional[str] = None  # INI option name
    converter: Callable[[str], Any] = str  # Type converter function
    list_converter: bool = False  # If True, split by comma
    bool_converter: bool = False  # If True, parse as boolean


# Hardcoded defaults are now inlined in field mappings and __init__ methods


class ConfigBase(ABC):
    """Abstract base class for command-specific configuration.

    Contains shared attributes for all commands:
    - log_file: Logging destination
    - uptime_kuma_url: API URL for all commands
    - heartbeat_enabled: Global heartbeat toggle
    - heartbeat_interval: Global heartbeat frequency
    - heartbeat_token: Token for heartbeat push notifications
    - command_token: Token for command-specific push notifications

    Subclasses should implement command-specific attributes and loading logic.
    """

    def __init__(self):
        """Initialize configuration with defaults."""
        # Shared attributes
        self.log_file = "/var/log/kuma-sentinel.log"
        self.uptime_kuma_url: Optional[str] = None
        self.heartbeat_enabled = True
        self.heartbeat_interval = 300
        self.heartbeat_token: Optional[str] = None
        self.command_token: Optional[str] = None

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for configuration.

        Base implementation returns shared field mappings.
        Subclasses should override and call super() to merge with command-specific fields.

        Returns:
            Dictionary mapping field names to FieldMapping definitions
        """
        return {
            "log_file": FieldMapping(
                env_var="KUMA_SENTINEL_LOG_FILE",
                arg_key="log_file",
                ini_section="logging",
                ini_option="log_file",
            ),
            "uptime_kuma_url": FieldMapping(
                arg_key="uptime_kuma_url",
                ini_section="uptime_kuma",
                ini_option="url",
            ),
            "heartbeat_enabled": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_ENABLED",
                ini_section="heartbeat",
                ini_option="enabled",
                bool_converter=True,
            ),
            "heartbeat_interval": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_INTERVAL",
                ini_section="heartbeat",
                ini_option="interval",
                converter=int,
            ),
            "heartbeat_token": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_TOKEN",
                arg_key="heartbeat_token",
                ini_section="heartbeat.uptime_kuma",
                ini_option="token",
            ),
        }

    def load_from_ini(self, config_file: str) -> None:
        """Load configuration from INI file.

        Args:
            config_file: Path to INI configuration file

        Raises:
            FileNotFoundError: If config file not found
            RuntimeError: If config file parsing fails
        """
        try:
            parser = configparser.ConfigParser()
            parser.read(config_file)
            self._apply_field_mappings_from_ini(parser)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse config file {config_file}: {str(e)}"
            ) from e

    def load_from_args(self, args) -> None:
        """Load configuration from command-line arguments."""
        self._apply_field_mappings_from_args(args)

    def load_from_env(self) -> None:
        """Load configuration from environment variables.

        Loading priority: CLI args > INI file > Environment variables > Defaults
        """
        self._apply_field_mappings_from_env()

    def validate(self) -> None:
        """Validate shared configuration common to all commands.

        Raises:
            ValueError: If shared configuration is invalid
        """
        errors = []

        if not self.uptime_kuma_url:
            errors.append("Uptime Kuma URL not provided")

        if not self.heartbeat_token:
            errors.append("Heartbeat push token not provided")

        if not self.command_token:
            errors.append("Command push token not provided")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def _apply_field_mappings_from_env(self) -> None:
        """Apply field mappings from environment variables."""
        mappings = self._get_field_mappings()
        for field_name, mapping in mappings.items():
            if not mapping.env_var:
                continue

            env_value = os.environ.get(mapping.env_var)
            if env_value:
                converted = self._convert_value(env_value, mapping)
                setattr(self, field_name, converted)

    def _apply_field_mappings_from_ini(self, parser: configparser.ConfigParser) -> None:
        """Apply field mappings from INI file."""
        mappings = self._get_field_mappings()
        for field_name, mapping in mappings.items():
            if not mapping.ini_section or not mapping.ini_option:
                continue

            if not parser.has_section(mapping.ini_section):
                continue
            if not parser.has_option(mapping.ini_section, mapping.ini_option):
                continue

            ini_value = parser.get(mapping.ini_section, mapping.ini_option)
            converted = self._convert_value(ini_value, mapping)
            setattr(self, field_name, converted)

    def _apply_field_mappings_from_args(self, args: dict) -> None:
        """Apply field mappings from command-line arguments."""
        mappings = self._get_field_mappings()
        for field_name, mapping in mappings.items():
            if not mapping.arg_key:
                continue

            arg_value = args.get(mapping.arg_key)
            if arg_value:
                converted = self._convert_value(arg_value, mapping)
                setattr(self, field_name, converted)

    @staticmethod
    def _convert_value(value: str, mapping: FieldMapping) -> Any:
        """Convert a string value using the mapping's converter.

        Handles bool and list conversions specially.
        """
        if mapping.bool_converter:
            return value.lower() in ("true", "yes", "1", "on")

        if mapping.list_converter:
            items = [item.strip() for item in value.split(",")]
            return [mapping.converter(item) for item in items]

        return mapping.converter(value)

    @abstractmethod
    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get configuration summary for logging.

        Args:
            mask_tokens: If True, mask security tokens in output

        Returns:
            Dictionary with configuration summary
        """

    @staticmethod
    def _mask_token(token: Optional[str], mask: bool) -> Optional[str]:
        """Mask token if requested."""
        return "***" if mask and token else token
