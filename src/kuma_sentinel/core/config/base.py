"""Base configuration management for kuma sentinel."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable, Dict, List, Optional, get_type_hints

import yaml


# Declarative field mapping for config loading
@dataclass
class FieldMapping:
    """Declarative mapping for a config field across all loading sources."""

    env_var: Optional[str] = None  # Environment variable name
    arg_key: Optional[str] = None  # CLI argument key
    yaml_path: Optional[str] = (
        None  # YAML path (dot-separated: "section.subsection.key")
    )
    converter: Callable[[Any], Any] = (
        str  # Type converter function (can take any type, returns Any)
    )


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

    def __init__(self, logger: Optional[Logger] = None):
        """Initialize configuration with defaults.

        Args:
            logger: Optional logger for configuration operations.
                   If not provided, will use the default logger.
        """
        from kuma_sentinel.core.logger import get_logger

        # Shared attributes
        self.log_file = "/var/log/kuma-sentinel.log"
        self.log_level = "INFO"
        self.uptime_kuma_url: Optional[str] = None
        self.heartbeat_enabled = True
        self.heartbeat_interval = 300
        self.heartbeat_token: Optional[str] = None
        self.command_token: Optional[str] = None
        self.ignore_file_permissions = False  # Skip file permission checks if True
        self.logger = logger or get_logger()

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for configuration.

        Base implementation returns shared field mappings.
        Subclasses should override and call super() to merge with command-specific fields.

        Returns:
            Dictionary mapping field names to FieldMapping definitions
        """
        return {
            "log_file": FieldMapping(
                arg_key="log_file",
                yaml_path="logging.log_file",
            ),
            "log_level": FieldMapping(
                arg_key="log_level",
                yaml_path="logging.log_level",
            ),
            "uptime_kuma_url": FieldMapping(
                arg_key="uptime_kuma_url",
                yaml_path="uptime_kuma.url",
            ),
            "heartbeat_enabled": FieldMapping(
                yaml_path="heartbeat.enabled",
                converter=self._parse_bool,
            ),
            "heartbeat_interval": FieldMapping(
                yaml_path="heartbeat.interval",
                converter=int,
            ),
            "heartbeat_token": FieldMapping(
                env_var="KUMA_SENTINEL_HEARTBEAT_TOKEN",
                arg_key="heartbeat_token",
                yaml_path="heartbeat.uptime_kuma.token",
            ),
            "ignore_file_permissions": FieldMapping(
                arg_key="ignore_file_permissions",
                yaml_path="logging.ignore_file_permissions",
                converter=self._parse_bool,
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
            if self.logger:
                self.logger.debug(f"Loading YAML configuration from: {config_file}")

            with open(config_file) as f:
                data = yaml.safe_load(f) or {}

            if self.logger:
                self.logger.debug("Successfully parsed YAML configuration file")

            self._apply_field_mappings_from_yaml(data)
        except FileNotFoundError as e:
            error_msg = f"Configuration file not found: {config_file}"
            if self.logger:
                self.logger.error(f"❌ {error_msg}")
            raise FileNotFoundError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to parse config file {config_file}: {str(e)}"
            if self.logger:
                self.logger.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg) from e

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

        Logs validation failures and missing values for debugging.

        Raises:
            ValueError: If shared configuration is invalid
        """
        errors = []

        # Validate URL
        url_errors = self._validate_and_log_url()
        errors.extend(url_errors)

        # Validate tokens
        token_errors = self._validate_and_log_tokens()
        errors.extend(token_errors)

        if errors:
            error_message = "Configuration validation failed:\n  " + "\n  ".join(errors)
            if self.logger:
                self.logger.error(
                    f"❌ Configuration validation failed with {len(errors)} error(s)"
                )
                for error in errors:
                    self.logger.error(f"   - {error}")
            raise ValueError(error_message)

    def _validate_and_log_url(self) -> List[str]:
        """Validate Uptime Kuma URL and log results.

        Returns:
            List of error messages (empty if valid)
        """
        if not self.uptime_kuma_url:
            error_msg = "Uptime Kuma URL not provided"
            if self.logger:
                self.logger.warning(f"⚠️  {error_msg}")
            return [error_msg]

        try:
            self.validate_uptime_kuma_url(self.uptime_kuma_url)
            if self.logger:
                self.logger.debug("✅ Uptime Kuma URL validation passed")
            return []
        except ValueError as e:
            error_msg = f"Invalid Uptime Kuma URL: {str(e)}"
            if self.logger:
                self.logger.error(f"❌ {error_msg}")
            return [error_msg]

    def _validate_and_log_tokens(self) -> List[str]:
        """Validate heartbeat and command tokens and log results.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not self.heartbeat_token:
            error_msg = "Heartbeat push token not provided"
            errors.append(error_msg)
            if self.logger:
                self.logger.warning(f"⚠️  {error_msg}")
        else:
            if self.logger:
                self.logger.debug("✅ Heartbeat push token configured")

        if not self.command_token:
            error_msg = "Command push token not provided"
            errors.append(error_msg)
            if self.logger:
                self.logger.warning(f"⚠️  {error_msg}")
        else:
            if self.logger:
                self.logger.debug("✅ Command push token configured")

        return errors

    def _apply_field_mappings_from_env(self) -> None:
        """Apply field mappings from environment variables.

        Logs when environment variables are detected and applied.
        """
        mappings = self._get_field_mappings()
        env_vars_loaded = []

        for field_name, mapping in mappings.items():
            if not mapping.env_var:
                continue

            env_value = os.environ.get(mapping.env_var)
            if env_value:
                converted = self._convert_value(env_value, mapping)
                setattr(self, field_name, converted)
                env_vars_loaded.append(mapping.env_var)

        if env_vars_loaded and self.logger:
            self.logger.debug(
                f"Loaded {len(env_vars_loaded)} configuration field(s) from environment variables"
            )

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

        Note: Empty lists/tuples from Click's multiple=True are treated as "not provided"
        and don't override YAML or environment configurations.
        """
        mappings = self._get_field_mappings()
        type_hints = get_type_hints(self.__class__)

        for field_name, mapping in mappings.items():
            if not mapping.arg_key:
                continue

            arg_value = args.get(mapping.arg_key)
            if arg_value is None:
                continue

            # Skip empty collections - these come from Click's multiple=True when no args provided
            # We don't want empty tuples/lists to override YAML or env var values
            if isinstance(arg_value, (list, tuple)) and not arg_value:
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

    @staticmethod
    def validate_config_file_permissions(
        file_path: str, logger=None, ignore_warning: bool = False
    ) -> bool:
        """Validate that config file has restricted permissions (0o600).

        Args:
            file_path: Path to config file
            logger: Logger instance (optional, for warning messages)
            ignore_warning: If True, warn but don't raise; if False, raise exception

        Returns:
            True if permissions are secure (0o600)

        Raises:
            RuntimeError: If permissions are not 0o600 and ignore_warning is False
        """
        try:
            file_stat = os.stat(file_path)
            mode = file_stat.st_mode & 0o777

            if mode != 0o600:
                error_msg = (
                    f"Config file {file_path} has overly permissive mode {oct(mode)}. "
                    f"Recommended: 0o600. Run: chmod 600 {file_path}"
                )

                if ignore_warning:
                    if logger:
                        from kuma_sentinel.core.logger import log_security_event

                        logger.warning(f"⚠️  {error_msg}")
                        log_security_event(
                            logger,
                            "permission_bypass",
                            f"Config file permissions check bypassed for {file_path} (mode {oct(mode)})",
                            level="warning",
                        )
                    return False
                else:
                    # Production mode: fail hard
                    if logger:
                        logger.error(f"❌ {error_msg}")
                    raise RuntimeError(
                        f"Security check failed: {error_msg} "
                        f"To bypass this check, use --ignore-file-permissions flag or "
                        f"set logging.ignore_file_permissions: true in config."
                    )
            return True
        except OSError as e:
            error_msg = f"Failed to check config file permissions: {str(e)}"
            if logger:
                logger.error(error_msg)
            if not ignore_warning:
                raise RuntimeError(error_msg) from e
            return False

    @staticmethod
    def validate_uptime_kuma_url(url: Optional[str]) -> None:
        """Validate Uptime Kuma API URL format.

        Args:
            url: URL string to validate

        Raises:
            ValueError: If URL format is invalid
        """
        from urllib.parse import urlparse

        if not url:
            raise ValueError("Uptime Kuma URL cannot be empty")

        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"URL scheme must be 'http' or 'https', got '{parsed.scheme}'"
                )

            # Check netloc (domain/host)
            if not parsed.netloc:
                raise ValueError(
                    "URL must include a hostname (e.g., http://uptimekuma:3001)"
                )

            # Check for common issues
            if " " in url:
                raise ValueError("URL contains spaces")

            if url.endswith("/"):
                raise ValueError("URL should not end with trailing slash")

            return None

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Invalid URL format: {str(e)}") from e

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
