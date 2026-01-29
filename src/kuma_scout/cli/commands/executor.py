"""Unified command executor for Kuma Scout monitoring commands."""

import logging
import sys
import time
from abc import abstractmethod
from typing import Any, Callable, Dict

from kuma_scout.cli.commands.base import Command
from kuma_scout.core.config.base import ConfigBase
from kuma_scout.core.logger import setup_default_logging, setup_logging
from kuma_scout.core.uptime_kuma import PUSH_TIMEOUT_ALERT, send_push


class CommandExecutor(Command):
    """Base class for unified command execution with common orchestration logic.

    Encapsulates: config loading, validation, logging, checker execution,
    heartbeat management, and push notifications.

    Subclasses should implement:
    - get_builtin_command(): Build Typer-compatible command function with parameters
    - get_summary_fields() -> Dict: Get fields for config summary logging
    - _checker_class: Class attribute for the checker to instantiate
    """

    _command_name: str = ""
    _help_text: str = ""
    _checker_class: Any = None
    _config_class: Any = None

    def __init__(self):
        """Initialize the command executor with default logging."""
        setup_default_logging()

    def register_command(self) -> Callable:
        """Register and return a Typer-compatible command function.

        This method delegates to get_builtin_command() which subclasses override
        to define command with Typer parameters.
        """
        return self.get_builtin_command()

    def execute_with_orchestration(self, args: Dict[str, Any]) -> None:
        """Execute the monitoring command with unified orchestration.

        Handles: config loading, validation, logging, execution, error handling.
        """
        # Initialize configuration
        cfg = self._load_and_validate_config(self._command_name, args)

        # Setup logging
        logger = setup_logging(cfg.log_file, cfg.log_level)

        # Log configuration summary
        self._log_config_summary(logger, cfg, self._command_name)

        # Type assertions (validate() ensures these are not None)
        assert cfg.uptime_kuma_url is not None
        assert cfg.heartbeat_token is not None

        # Start check
        check_start = time.time()
        logger.info(f"🔍 Starting {self._command_name} check")

        try:
            # Create and execute checker with config object
            # Checker handles heartbeat messages via execute_with_heartbeat()
            checker = self._checker_class(logger, cfg)
            result = checker.execute_with_heartbeat()

            # Calculate check duration in milliseconds
            check_end = time.time()
            check_duration_ms = int((check_end - check_start) * 1000)
            check_minutes = check_duration_ms // 60000

            # Send alert based on result
            # (Heartbeat messages already sent by checker's execute_with_heartbeat())
            self._send_result_alert(
                logger, cfg, self._command_name, result, check_duration_ms
            )

            logger.info(f"✅ {self._command_name} check complete ({check_minutes}m)")
            sys.exit(0)

        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            # Calculate partial duration from error time in milliseconds
            error_end = time.time()
            error_duration_ms = int((error_end - check_start) * 1000)
            self._send_error_alert(
                logger, cfg, self._command_name, str(e), error_duration_ms
            )
            sys.exit(1)

    def _load_and_validate_config(
        self, command_name: str, args: Dict[str, Any]
    ) -> ConfigBase:
        """Load and validate configuration with correct precedence.

        Loading order: defaults (in __init__) -> env vars -> yaml file -> args.
        Later stages can override earlier stages.
        """
        # Create config instance using class attribute set by decorator
        self.config = self._config_class()

        # Load configuration in precedence order
        self._load_from_env()
        self._load_from_config_file(args)
        self._load_from_args(args)

        # Handle special argument mappings
        self._map_special_args(args)

        # Validate configuration
        self._validate_config(command_name)

        return self.config

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        self.config.load_from_env()

    def _load_from_config_file(self, args: Dict[str, Any]) -> None:
        """Load configuration from YAML file if it exists."""
        config_file = args.get("config") or "/etc/kuma-scout/config.yaml"
        if not config_file or not sys.modules.get("os"):
            return

        import os

        if not os.path.exists(config_file):
            return

        # Check file permissions unless user explicitly ignores them
        ignore_perms = args.get("ignore_file_permissions", False)
        from kuma_scout.core.logger import get_logger

        logger = get_logger()
        try:
            self.config.__class__.validate_config_file_permissions(
                config_file, logger=logger, ignore_warning=ignore_perms
            )
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

        try:
            logger.info(f"📂 Loading YAML config file: {config_file}")
            self.config.load_from_yaml(config_file)
            logger.info("✅ Config file loaded successfully")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            sys.exit(1)

    def _load_from_args(self, args: Dict[str, Any]) -> None:
        """Load configuration from command-line arguments."""
        self.config.load_from_args(args)

    def _map_special_args(self, args: Dict[str, Any]) -> None:
        """Map special command-line arguments to config fields."""
        # Map generic 'token' argument to command-specific token field
        token_cli = args.get("token")
        if token_cli and hasattr(self.config, "command_token"):
            self.config.command_token = token_cli

        # Handle --ssh shorthand (user@host format)
        ssh_shorthand = args.get("ssh")
        if ssh_shorthand:
            from kuma_scout.core.utils.ssh_runner import parse_ssh_shorthand

            host, user = parse_ssh_shorthand(ssh_shorthand)
            if host:
                self.config.ssh_host = host
            if user:
                self.config.ssh_user = user

    def _validate_config(self, command_name: str) -> None:
        """Validate SSH and overall configuration."""
        # Validate SSH configuration if SSH is enabled
        if self.config.ssh_host:
            try:
                self.config.validate_ssh_config()
            except RuntimeError as e:
                from kuma_scout.core.logger import get_logger

                logger = get_logger()
                logger.error(str(e))
                sys.exit(1)

        # Validate overall configuration
        try:
            self.config.validate()
        except ValueError as e:
            from kuma_scout.core.logger import get_logger

            logger = get_logger()
            logger.error(f"Configuration error: {e}")
            logger.info(f"Use 'kuma-scout {command_name} --help' for usage information")
            sys.exit(1)

    def _log_config_summary(
        self, logger: logging.Logger, cfg: ConfigBase, command_name: str
    ) -> None:
        """Log configuration summary. Delegates to subclass for format customization."""
        logger.info("=" * 70)
        logger.info(f"🔍 KUMA SCOUT - {command_name.upper()} CONFIGURATION")
        logger.info("=" * 70)

        config_summary = cfg.get_summary(mask_tokens=True)
        summary_fields = self.get_summary_fields()

        for section_name, section_fields in summary_fields.items():
            logger.info(f"{section_name}:")
            for field_label, field_key in section_fields.items():
                value = config_summary.get(field_key, "N/A")
                logger.info(f"   {field_label}: {value}")

        logger.info("=" * 70)

    def _send_result_alert(
        self,
        logger: logging.Logger,
        cfg: ConfigBase,
        command_name: str,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Send result alert. Delegates to subclass for command-specific alert formatting."""
        self.send_result_alert(logger, cfg, command_name, result, duration_ms)

    def _send_error_alert(
        self,
        logger: logging.Logger,
        cfg: ConfigBase,
        command_name: str,
        error_message: str,
        duration_ms: int = 0,
    ) -> None:
        """Send error alert. Delegates to subclass for command-specific error handling."""
        self.send_error_alert(logger, cfg, command_name, error_message, duration_ms)

    # === Abstract Methods (Subclasses Must Implement) ===

    @abstractmethod
    def get_builtin_command(self) -> Callable:
        """Build and return a Typer-compatible command function.

        Returns:
            A callable function that Typer can register as a command.
            The function should accept Typer parameters using type hints and default values.
        """
        pass

    @abstractmethod
    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging.

        Returns:
            Dict mapping section names to dicts of field_label -> config_key
            Example:
            {
                "📋 Kopia Configuration": {
                    "Snapshot Paths": "kopiasnapshotstatus_snapshot_paths",
                    "Max Age": "kopiasnapshotstatus_max_age_hours",
                }
            }
        """
        pass

    # === Default Hook Methods (Subclasses Can Override) ===

    def send_result_alert(
        self,
        logger: logging.Logger,
        cfg: ConfigBase,
        command_name: str,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Send result alert. Override in subclass for custom alert logic."""
        # Default: send generic alert based on result status and message
        if cfg.command_token:
            duration_minutes = duration_ms // 60000
            send_push(
                logger,
                cfg.uptime_kuma_url,
                cfg.command_token,
                f"{result.message} ({duration_minutes}m)",
                command=command_name,
                status=result.status,
                timeout=PUSH_TIMEOUT_ALERT,
                ping_ms=duration_ms,
            )

    def send_error_alert(
        self,
        logger: logging.Logger,
        cfg: ConfigBase,
        command_name: str,
        error_message: str,
        duration_ms: int = 0,
    ) -> None:
        """Send error alert. Override in subclass for custom error handling."""
        # Default: send error alert to command-specific token
        if cfg.command_token:
            send_push(
                logger,
                cfg.uptime_kuma_url,
                cfg.command_token,
                f"{command_name} error: {error_message}",
                command=command_name,
                status="down",
                timeout=PUSH_TIMEOUT_ALERT,
                ping_ms=duration_ms if duration_ms > 0 else None,
            )
