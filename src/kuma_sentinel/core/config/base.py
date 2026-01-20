"""Base configuration management for kuma sentinel."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, get_type_hints

import yaml


# Declarative field mapping for config loading
@dataclass
class FieldMapping:
    """Declarative mapping for a config field across all loading sources."""

    env_var: Optional[str] = None  # Environment variable name
    arg_key: Optional[str] = None  # CLI argument key
    yaml_path: Optional[str] = None  # YAML path (dot-separated: "section.subsection.key")
    converter: Callable[[Any], Any] = str  # Type converter function (can take any type, returns Any)


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
        self.log_level = "INFO"
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
                yaml_path="logging.log_file",
            ),
            "log_level": FieldMapping(
                env_var="KUMA_SENTINEL_LOG_LEVEL",
                arg_key="log_level",
                yaml_path="logging.log_level",
            ),
            "uptime_kuma_url": FieldMapping(
                arg_key="uptime_kuma_url",
                yaml_path="uptime_kuma.url",
            ),
            "heartbeat_enabled": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_ENABLED",
                yaml_path="heartbeat.enabled",
                converter=self._parse_bool,
            ),
            "heartbeat_interval": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_INTERVAL",
                yaml_path="heartbeat.interval",
                converter=int,
            ),
            "heartbeat_token": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_TOKEN",
                arg_key="heartbeat_token",
                yaml_path="heartbeat.uptime_kuma.token",
            ),
        }

    def load_from_yaml(self, config_file: str) -> None:
        """Load configuration from YAML file.

        Args:
            config_file: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file not found
            RuntimeError: If config file parsing fails
        """
        try:
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
            self._apply_field_mappings_from_yaml(data)
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

        Loading priority: CLI args > YAML file > Environment variables > Defaults
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

    def _apply_field_mappings_from_yaml(self, data: dict) -> None:
        """Apply field mappings from YAML data dictionary."""
        mappings = self._get_field_mappings()
        for field_name, mapping in mappings.items():
            if not mapping.yaml_path:
                continue

            yaml_value = self._get_nested_value(data, mapping.yaml_path)
            if yaml_value is not None:
                converted = self._convert_value(yaml_value, mapping)
                setattr(self, field_name, converted)

    def _apply_field_mappings_from_args(self, args: dict) -> None:
        """Apply field mappings from command-line arguments with intelligent type handling.
        
        Handles:
        - List[str] fields: Converts tuples from Click's multiple=True to lists
        - Fields with converter: Applies the converter function
        - Simple fields: Uses value as-is
        """
        mappings = self._get_field_mappings()
        type_hints = get_type_hints(self.__class__)
        
        for field_name, mapping in mappings.items():
            if not mapping.arg_key:
                continue

            arg_value = args.get(mapping.arg_key)
            if arg_value is None:
                continue
            
            # Get the field's expected type from type hints
            field_type = type_hints.get(field_name)
            
            # Handle List[str] fields - convert tuple from Click to list
            if field_type == List[str]:
                value = list(arg_value) if arg_value else []
            
            # Handle converter function from mapping (if not default str converter)
            elif mapping.converter is not str:
                value = mapping.converter(arg_value)
            
            # For str type with no explicit converter, use value as-is
            else:
                value = arg_value
            
            setattr(self, field_name, value)

    @staticmethod
    def _get_nested_value(data: dict, path: str) -> Any:
        """Get value from nested dictionary using dot-separated path.

        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., "logging.log_file")

        Returns:
            Value at path, or None if not found
        """
        keys = path.split(".")
        current: Any = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def _convert_value(value: Any, mapping: FieldMapping) -> Any:
        """Convert a value using the mapping's converter.

        Handles type conversion appropriately based on YAML native types.
        """
        # If value is already the right type (from YAML parsing), return as-is
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return value

        # Convert strings using the mapping converter
        if isinstance(value, str):
            return mapping.converter(value)

        return value

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        """Parse a value as boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "on")
        return bool(value)

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
