"""Unified command executor for Kuma Sentinel monitoring commands."""

import logging
import sys
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

import click

from kuma_sentinel.cli.commands.base import Command
from kuma_sentinel.core.config import DEFAULT_CONFIG_PATH, Config
from kuma_sentinel.core.logger import setup_logging
from kuma_sentinel.core.uptime_kuma import PUSH_TIMEOUT_ALERT, send_push


@dataclass
class CommandMetadata:
    """Metadata for a Kuma Sentinel command."""

    name: str
    checker_class: Any
    help_text: str


class CommandExecutor(Command):
    """Base class for unified command execution with common orchestration logic.

    Encapsulates: config loading, validation, logging, checker execution,
    heartbeat management, and push notifications.

    Subclasses should implement:
    - get_metadata(): Return CommandMetadata with command name and checker class
    - get_arguments(): Return list of Click arguments
    - get_options(): Return dict of Click options
    - build_checker_config(cfg: Config) -> Dict[str, Any]: Build checker config from Config
    - get_summary_fields(cfg: Config) -> Dict[str, Any]: Get fields for config summary logging
    """

    def register_command(self) -> click.Command:
        """Register and return a Click command using the executor pattern.

        This method creates a Click command that delegates execution to execute_with_orchestration().
        Subclasses should override get_builtin_command() to define full command with decorators.
        """
        metadata = self.get_metadata()

        @click.command(metadata.name, help=metadata.help_text)
        @click.pass_context
        def command(ctx: click.Context, **kwargs):
            """Execute the monitoring command with unified orchestration."""
            self.execute_with_orchestration(ctx, metadata, kwargs)

        # Allow subclass to build and decorate the command
        return self.get_builtin_command(command, metadata)

    def execute_with_orchestration(
        self, ctx: click.Context, metadata: CommandMetadata, args: Dict[str, Any]
    ) -> None:
        """Execute the monitoring command with unified orchestration.

        Handles: config loading, validation, logging, execution, error handling.
        """
        # Initialize configuration
        cfg = self._load_and_validate_config(args)

        # Setup logging
        logger = setup_logging(cfg.log_file)

        # Log configuration summary
        self._log_config_summary(logger, cfg, metadata.name)

        # Type assertions (validate() ensures these are not None)
        assert cfg.uptime_kuma_url is not None
        assert cfg.heartbeat_token is not None

        # Start check
        check_start = time.time()
        logger.info(f"🔍 Starting {metadata.name} check")

        # Send initial heartbeat
        send_push(
            logger,
            cfg.uptime_kuma_url,
            cfg.heartbeat_token,
            f"{metadata.name} starting...",
            command=metadata.name,
        )

        try:
            # Build checker config from Config object
            checker_config = self.build_checker_config(cfg)

            # Create and execute checker
            checker = metadata.checker_class(logger, checker_config)
            result = checker.execute_with_heartbeat()

            # Calculate check duration
            check_end = time.time()
            check_duration = int(check_end - check_start)
            check_minutes = check_duration // 60

            # Send final heartbeat
            send_push(
                logger,
                cfg.uptime_kuma_url,
                cfg.heartbeat_token,
                f"{metadata.name} complete after {check_minutes}m",
                command=metadata.name,
            )

            # Send alert based on result
            self._send_result_alert(logger, cfg, metadata.name, result, check_minutes)

            logger.info(f"✅ {metadata.name} check complete ({check_minutes}m)")
            sys.exit(0)

        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            self._send_error_alert(logger, cfg, metadata.name, str(e))
            sys.exit(1)

    def _load_and_validate_config(self, args: Dict[str, Any]) -> Config:
        """Load and validate configuration from file, args, and environment."""
        cfg = Config()

        # Load from config file if provided or if default exists
        config_file = args.get("config") or DEFAULT_CONFIG_PATH
        if config_file and sys.modules.get("os"):
            import os

            if os.path.exists(config_file):
                try:
                    click.secho(
                        f"📂 Loading INI config file: {config_file}",
                        fg="cyan",
                    )
                    cfg.load_from_ini(config_file)
                    click.secho(
                        "✅ Config file loaded successfully",
                        fg="green",
                    )
                except Exception as e:
                    click.secho(
                        f"Error loading config file: {e}",
                        fg="red",
                        err=True,
                    )
                    sys.exit(1)

        # Load from args (delegates to subclass)
        self._load_from_args(cfg, args)

        # Load from environment
        cfg.load_from_env()

        # Validate configuration
        try:
            cfg.validate()
        except ValueError as e:
            click.secho(f"Configuration error: {e}", fg="red", err=True)
            metadata = self.get_metadata()
            click.secho(
                f"\nUse 'kuma-sentinel {metadata.name} --help' for usage information",
                fg="yellow",
                err=True,
            )
            sys.exit(1)

        return cfg

    def _load_from_args(self, cfg: Config, args: Dict[str, Any]) -> None:
        """Load config from args. Delegates to subclass for command-specific loading."""
        self.load_from_args(cfg, args)

    def _log_config_summary(
        self, logger: logging.Logger, cfg: Config, command_name: str
    ) -> None:
        """Log configuration summary. Delegates to subclass for format customization."""
        logger.info("=" * 70)
        logger.info(f"🔍 KUMA SENTINEL - {command_name.upper()} CONFIGURATION")
        logger.info("=" * 70)

        config_summary = cfg.get_summary(mask_tokens=True)
        summary_fields = self.get_summary_fields(cfg)

        for section_name, section_fields in summary_fields.items():
            logger.info(f"{section_name}:")
            for field_label, field_key in section_fields.items():
                value = config_summary.get(field_key, "N/A")
                logger.info(f"   {field_label}: {value}")

        logger.info("=" * 70)

    def _send_result_alert(
        self, logger: logging.Logger, cfg: Config, command_name: str, result: Any, duration_minutes: int
    ) -> None:
        """Send result alert. Delegates to subclass for command-specific alert formatting."""
        self.send_result_alert(logger, cfg, command_name, result, duration_minutes)

    def _send_error_alert(
        self, logger: logging.Logger, cfg: Config, command_name: str, error_message: str
    ) -> None:
        """Send error alert. Delegates to subclass for command-specific error handling."""
        self.send_error_alert(logger, cfg, command_name, error_message)

    # === Abstract Methods (Subclasses Must Implement) ===

    @abstractmethod
    def get_metadata(self) -> CommandMetadata:
        """Return metadata for this command (name, checker class, help text)."""
        pass

    @abstractmethod
    def get_builtin_command(
        self, base_command: click.Command, metadata: CommandMetadata
    ) -> click.Command:
        """Build and decorate the Click command with arguments and options.

        Args:
            base_command: Base Click command with name and help
            metadata: Command metadata

        Returns:
            Fully decorated Click command with arguments and options applied
        """
        pass

    @abstractmethod
    def build_checker_config(self, cfg: Config) -> Dict[str, Any]:
        """Build checker configuration from Config object.

        Args:
            cfg: Loaded and validated Config object

        Returns:
            Dict with checker-specific configuration
        """
        pass

    @abstractmethod
    def get_summary_fields(self, cfg: Config) -> Dict[str, Dict[str, str]]:
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

    def load_from_args(self, cfg: Config, args: Dict[str, Any]) -> None:
        """Load command-specific args into config. Override in subclass if needed."""
        pass

    def send_result_alert(
        self, logger: logging.Logger, cfg: Config, command_name: str, result: Any, duration_minutes: int
    ) -> None:
        """Send result alert. Override in subclass for custom alert logic."""
        # Default: send generic alert based on result status and message
        alert_token = getattr(cfg, f"{command_name}_token", None)
        if alert_token:
            send_push(
                logger,
                cfg.uptime_kuma_url,
                alert_token,
                f"{result.message} ({duration_minutes}m)",
                command=command_name,
                status=result.status,
                timeout=PUSH_TIMEOUT_ALERT,
            )

    def send_error_alert(
        self, logger: logging.Logger, cfg: Config, command_name: str, error_message: str
    ) -> None:
        """Send error alert. Override in subclass for custom error handling."""
        # Default: send error alert to command-specific token
        alert_token = getattr(cfg, f"{command_name}_token", None)
        if alert_token:
            send_push(
                logger,
                cfg.uptime_kuma_url,
                alert_token,
                f"{command_name} error: {error_message}",
                command=command_name,
                status="down",
                timeout=PUSH_TIMEOUT_ALERT,
            )
