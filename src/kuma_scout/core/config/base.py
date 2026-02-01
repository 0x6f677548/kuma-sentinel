"""Base configuration management for kuma scout."""

import os
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
    expand_env_vars: bool = False  # Enable ${VAR} expansion in YAML values


# Hardcoded defaults are now inlined in field mappings and __init__ methods


class ConfigBase:
    """Base class for command-specific configuration.

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
        from kuma_scout.core.logger import get_logger

        # Shared attributes
        self.log_file = "/var/log/kuma-scout.log"
        self.log_level = "INFO"
        self.uptime_kuma_url: Optional[str] = None
        self.heartbeat_enabled = True
        self.heartbeat_interval = 300
        self.heartbeat_token: Optional[str] = None
        self.command_token: Optional[str] = None
        self.ignore_file_permissions = False  # Skip file permission checks if True
        self.logger = logger or get_logger()

        # SSH configuration for remote execution
        self.ssh_host: Optional[str] = None
        self.ssh_user: Optional[str] = None
        self.ssh_port: int = 22
        self.ssh_key_file: Optional[str] = None
        self.ssh_password: Optional[str] = None
        self.ssh_strict_host_key_checking: bool = True

    def _get_command_name(self) -> str:
        """Get the command name for command-specific configuration.

        Subclasses should override this to return their command name
        for command-specific SSH and other overrides.

        Returns:
            Command name (e.g., 'portscan', 'cmdcheck')
        """
        return ""

    def _get_ssh_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get SSH field mappings including command-specific overrides.

        Returns:
            Dictionary of SSH field mappings
        """
        command_name = self._get_command_name()
        mappings = {
            # Global SSH configuration
            "ssh_connection_string": FieldMapping(
                yaml_path="ssh.connection",
            ),
            "ssh_key_file": FieldMapping(
                arg_key="ssh_key_file",
                yaml_path="ssh.key_file",
            ),
            "ssh_password": FieldMapping(
                arg_key="ssh_password",
                yaml_path="ssh.password",
            ),
            "ssh_strict_host_key_checking": FieldMapping(
                arg_key="ssh_strict_host_key_checking",
                yaml_path="ssh.strict_host_key_checking",
                converter=self._parse_bool,
            ),
        }

        # Add command-specific SSH overrides if command name is available
        if command_name:
            command_ssh_mappings = {
                f"{command_name}_ssh_connection_string": FieldMapping(
                    yaml_path=f"{command_name}.ssh.connection",
                ),
                f"{command_name}_ssh_key_file": FieldMapping(
                    yaml_path=f"{command_name}.ssh.key_file",
                ),
                f"{command_name}_ssh_password": FieldMapping(
                    yaml_path=f"{command_name}.ssh.password",
                ),
                f"{command_name}_ssh_strict_host_key_checking": FieldMapping(
                    yaml_path=f"{command_name}.ssh.strict_host_key_checking",
                    converter=self._parse_bool,
                ),
            }
            mappings.update(command_ssh_mappings)

        return mappings

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for configuration.

        Base implementation returns shared field mappings.
        Subclasses should override and call super() to merge with command-specific fields.

        Returns:
            Dictionary mapping field names to FieldMapping definitions
        """
        mappings = {
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
                env_var="KUMA_SCOUT_HEARTBEAT_TOKEN",
                arg_key="heartbeat_token",
                yaml_path="heartbeat.uptime_kuma.token",
                expand_env_vars=True,
            ),
            "ignore_file_permissions": FieldMapping(
                arg_key="ignore_file_permissions",
                yaml_path="logging.ignore_file_permissions",
                converter=self._parse_bool,
            ),
        }

        # Add SSH field mappings (global and command-specific)
        mappings.update(self._get_ssh_field_mappings())

        return mappings

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
            # Process SSH connection strings after loading
            self._process_ssh_config_from_yaml(data)
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

    def _process_ssh_config_from_yaml(self, data: Dict[str, Any]) -> None:
        """Process SSH connection strings from YAML configuration.

        Handles both global and command-specific SSH connection strings.
        Connection strings are parsed and individual SSH fields are set
        only if they haven't been set by explicit YAML fields.

        Args:
            data: Parsed YAML data
        """
        from kuma_scout.core.utils.ssh_runner import SSHConfig

        # Process global SSH connection string
        global_connection = self._get_nested_value(data, "ssh.connection")
        if global_connection:
            ssh_config = SSHConfig.from_connection_string(global_connection)
            if ssh_config.host and self.ssh_host is None:
                self.ssh_host = ssh_config.host
            if ssh_config.user and self.ssh_user is None:
                self.ssh_user = ssh_config.user
            if ssh_config.port and self.ssh_port == 22:  # Only override default
                self.ssh_port = ssh_config.port

        # Process command-specific SSH connection string
        command_name = self._get_command_name()
        if command_name:
            command_connection = self._get_nested_value(
                data, f"{command_name}.ssh.connection"
            )
            if command_connection:
                ssh_config = SSHConfig.from_connection_string(command_connection)
                # Command-specific overrides global settings
                if ssh_config.host:
                    self.ssh_host = ssh_config.host
                if ssh_config.user:
                    self.ssh_user = ssh_config.user
                if ssh_config.port:
                    self.ssh_port = ssh_config.port

    def _process_ssh_config_from_args(self, args: Dict[str, Any]) -> None:
        """Process SSH connection string from CLI arguments.

        CLI arguments always take precedence over YAML configuration.

        Args:
            args: CLI arguments dictionary
        """
        from kuma_scout.core.utils.ssh_runner import SSHConfig

        # Process SSH connection string from CLI - this always overrides YAML
        connection_string = args.get("ssh")
        if connection_string:
            ssh_config = SSHConfig.from_connection_string(connection_string)
            # CLI always overrides any previous values
            if ssh_config.host:
                self.ssh_host = ssh_config.host
            if ssh_config.user:
                self.ssh_user = ssh_config.user
            if ssh_config.port:
                self.ssh_port = ssh_config.port

    def load_from_args(self, args) -> None:
        """Load configuration from command-line arguments."""
        self._apply_field_mappings_from_args(args)
        # Process SSH connection string from CLI args
        self._process_ssh_config_from_args(args)

    def load_from_env(self) -> None:
        """Load configuration from environment variables.

        Loading priority: CLI args > YAML file > Environment variables > Defaults
        """
        self._apply_field_mappings_from_env()

    def validate(self, validate_tokens: bool = True, validate_heartbeat_token: bool = True) -> None:
        """Validate shared configuration common to all commands.

        Logs validation failures and missing values for debugging.

        Args:
            validate_tokens: Whether to validate command tokens (default: True)
            validate_heartbeat_token: Whether to validate heartbeat token (default: True)

        Raises:
            ValueError: If shared configuration is invalid
        """
        errors = []

        # Validate URL
        url_errors = self._validate_and_log_url()
        errors.extend(url_errors)

        # Validate tokens (conditionally)
        if validate_tokens:
            token_errors = self._validate_and_log_tokens(validate_heartbeat_token)
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
            error_msg = "Uptime Kuma URL not provided (use --uptime-kuma-url)"
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

    def _validate_and_log_tokens(self, validate_heartbeat_token: bool = True) -> List[str]:
        """Validate heartbeat and command tokens and log results.

        Args:
            validate_heartbeat_token: Whether to validate heartbeat token (default: True)

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if validate_heartbeat_token and not self.heartbeat_token:
            error_msg = "Heartbeat push token not provided (use --heartbeat-token)"
            errors.append(error_msg)

        if not self.command_token:
            error_msg = "Command push token not provided (use --token)"
            errors.append(error_msg)

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
        - List[str] fields: Converts tuples from Typer's List[] to lists
        - Fields with converter: Applies the converter function
        - Simple fields: Uses value as-is

        Note: Empty lists/tuples from Typer's List[] are treated as "not provided"
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

            # Skip empty collections - these come from Typer's List[] when no args provided
            # We don't want empty tuples/lists to override YAML or env var values
            if isinstance(arg_value, (list, tuple)) and not arg_value:
                continue

            # Get the field's expected type from type hints
            field_type = type_hints.get(field_name)

            # Handle List[str] fields - convert tuple from Typer to list
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
        Supports environment variable expansion for string values when enabled.
        """
        # Handle environment variable expansion first
        if mapping.expand_env_vars:
            value = ConfigBase._expand_env_vars_in_value(value)

        # Return native YAML types as-is
        if ConfigBase._is_native_yaml_type(value):
            return value

        # Apply converter only to strings
        if isinstance(value, str):
            return mapping.converter(value)
        return value

    @staticmethod
    def _expand_env_vars_in_value(value: Any) -> Any:
        """Expand environment variables in a value, handling nested structures."""
        if isinstance(value, dict):
            return ConfigBase._expand_env_vars_in_dict(value)
        elif isinstance(value, list):
            return ConfigBase._expand_env_vars_in_list(value)
        elif isinstance(value, str):
            return ConfigBase._expand_env_vars_in_string(value)
        return value

    @staticmethod
    def _expand_env_vars_in_string(value: str) -> str:
        """Expand environment variables in a string with error checking."""
        expanded_value = os.path.expandvars(value)
        # Check if there are still unexpanded variables (missing env vars)
        if "${" in expanded_value or "$" in expanded_value and expanded_value != value:
            # Find any remaining ${VAR} patterns
            import re

            remaining_vars = re.findall(r"\$\{([^}]+)\}", expanded_value)
            if remaining_vars:
                raise ValueError(
                    f"Environment variable expansion failed: variables {remaining_vars} are not set"
                )
        return expanded_value

    @staticmethod
    def _is_native_yaml_type(value: Any) -> bool:
        """Check if value is a native YAML type that doesn't need conversion."""
        return isinstance(value, (bool, int, list))

    @staticmethod
    def _expand_env_vars_in_dict(data: dict) -> dict:
        """Recursively expand environment variables in a dictionary."""
        result: Dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str):
                # Skip expansion for command fields (security)
                if k == "command":
                    result[k] = v
                else:
                    expanded_v = os.path.expandvars(v)
                    # Check if there are still unexpanded variables (missing env vars)
                    if "${" in expanded_v:
                        import re

                        remaining_vars = re.findall(r"\$\{([^}]+)\}", expanded_v)
                        if remaining_vars:
                            raise ValueError(
                                f"Environment variable expansion failed: variables {remaining_vars} are not set"
                            )
                    result[k] = expanded_v
            elif isinstance(v, dict):
                result[k] = ConfigBase._expand_env_vars_in_dict(v)
            elif isinstance(v, list):
                result[k] = ConfigBase._expand_env_vars_in_list(v)
            else:
                result[k] = v
        return result

    @staticmethod
    def _expand_env_vars_in_list(data: list) -> list:
        """Recursively expand environment variables in a list."""
        result: List[Any] = []
        for item in data:
            if isinstance(item, str):
                expanded_item = os.path.expandvars(item)
                # Check if there are still unexpanded variables (missing env vars)
                if "${" in expanded_item:
                    import re

                    remaining_vars = re.findall(r"\$\{([^}]+)\}", expanded_item)
                    if remaining_vars:
                        raise ValueError(
                            f"Environment variable expansion failed: variables {remaining_vars} are not set"
                        )
                result.append(expanded_item)
            elif isinstance(item, dict):
                result.append(ConfigBase._expand_env_vars_in_dict(item))
            elif isinstance(item, list):
                result.append(ConfigBase._expand_env_vars_in_list(item))
            else:
                result.append(item)
        return result

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
                        from kuma_scout.core.logger import log_security_event

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

    def get_summary(self) -> dict:
        """Get configuration summary for logging.

        Returns:
            Dictionary with configuration summary
        """
        # Determine execution target
        if self.ssh_host:
            execution_target = f"SSH: {self.ssh_user or 'current_user'}@{self.ssh_host}"
            if self.ssh_port != 22:
                execution_target += f":{self.ssh_port}"
        else:
            execution_target = "Local execution"

        return {
            "log_file": self.log_file,
            "log_level": self.log_level,
            "execution_target": execution_target,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "uptime_kuma_url": self.uptime_kuma_url,
        }

    @staticmethod
    def validate_ssh_key_permissions(
        key_file: str, logger=None, ignore_warning: bool = False
    ) -> bool:
        """Validate that SSH key file has restricted permissions (0o600).

        Args:
            key_file: Path to SSH private key file
            logger: Logger instance (optional, for warning messages)
            ignore_warning: If True, warn but don't raise; if False, raise exception

        Returns:
            True if permissions are secure (0o600)

        Raises:
            RuntimeError: If permissions are not 0o600 and ignore_warning is False
        """
        try:
            file_stat = os.stat(key_file)
            mode = file_stat.st_mode & 0o777

            if mode & (0o040 | 0o020 | 0o004 | 0o002 | 0o001):
                # File has group or other permissions - insecure
                error_msg = (
                    f"SSH key file {key_file} has overly permissive mode {oct(mode)}. "
                    f"Recommended: 0o600. Run: chmod 600 {key_file}"
                )

                if ignore_warning:
                    if logger:
                        from kuma_scout.core.logger import log_security_event

                        logger.warning(f"⚠️  {error_msg}")
                        log_security_event(
                            logger,
                            "ssh_key_permission_bypass",
                            f"SSH key file permissions check bypassed for {key_file} (mode {oct(mode)})",
                            level="warning",
                        )
                    return False
                else:
                    # Production mode: fail hard
                    if logger:
                        logger.error(f"❌ {error_msg}")
                    raise RuntimeError(
                        f"Security check failed: {error_msg} "
                        f"To bypass this check, use --ignore-file-permissions flag."
                    )
            return True
        except OSError as e:
            error_msg = f"Failed to check SSH key file permissions: {str(e)}"
            if logger:
                logger.error(error_msg)
            if not ignore_warning:
                raise RuntimeError(error_msg) from e
            return False

    def validate_ssh_config(self) -> None:
        """Validate SSH configuration if SSH is enabled.

        Checks SSH key file permissions if a key file is specified.

        Raises:
            RuntimeError: If SSH key file has insecure permissions
        """
        if self.ssh_key_file and not self.ignore_file_permissions:
            self.validate_ssh_key_permissions(
                self.ssh_key_file, logger=self.logger, ignore_warning=False
            )
