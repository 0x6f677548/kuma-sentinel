"""
Base classes for Kuma-Scout plugins.

This module defines the Plugin base class and CheckConfig model that all
monitoring plugins must inherit from.
"""

import subprocess
import time
from abc import ABC, abstractmethod
from functools import wraps
from typing import Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from kuma_scout.core.execution_context import (
    execution_context_manager,
    get_execution_context,
)
from kuma_scout.core.heartbeat import HeartbeatService
from kuma_scout.core.models import CheckResult
from kuma_scout.core.output_handler import OutputHandler
from kuma_scout.core.utils.sanitizer import DataSanitizer
from kuma_scout.core.utils.ssh_runner import SSHConnectionError, SSHRunner

from .models import GlobalConfig, RetryConfig, SSHConfig, UptimeKumaConfig


def execute_with_timing(func):
    """
    Decorator that provides standardized timing, config casting, and error handling for plugin execute methods.

    This decorator:
    - Casts the config to the plugin's specific config type
    - Measures execution time
    - Handles exceptions with standardized CheckResult creation
    - Ensures consistent error handling across all plugins
    - Enriches error context with execution context when available
    """

    @wraps(func)
    def wrapper(self, config: CheckConfig) -> CheckResult:
        # Cast config to the plugin's specific type
        if hasattr(self, "config_class"):
            config = self.config_class(**config.model_dump())

        start_time = time.time()

        try:
            # Call the actual execute logic
            return func(self, config)
        except Exception as e:
            duration = int(time.time() - start_time)
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            context = get_execution_context()

            # Build detailed error message with context
            error_details: dict[str, str | int | float] = {
                "error": sanitized_error,
                "error_type": type(e).__name__,
            }
            if context:
                error_details["timeout_seconds"] = int(config.timeout)
                error_details["elapsed_seconds"] = context.elapsed_seconds

            self.output_handler.error(
                f"Check execution failed: {sanitized_error}", echo=False
            )

            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Check execution failed: {sanitized_error}",
                duration_seconds=duration,
                details=error_details,
            )

    return wrapper


class CheckConfig(BaseModel):
    """
    Base configuration for all checks.

    All plugins inherit these fields automatically.
    """

    model_config = ConfigDict(extra="allow")  # Allow plugin-specific fields

    name: str = Field(description="Unique check name")
    timeout: int = Field(default=30, ge=1, le=3600, description="Timeout in seconds")
    retry: RetryConfig = Field(
        default_factory=RetryConfig, description="Retry configuration"
    )
    uptime_kuma: Optional[UptimeKumaConfig] = Field(
        default=None, description="Override global Uptime Kuma settings"
    )
    ssh: Optional[SSHConfig] = Field(
        default=None, description="Override global SSH settings"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")


class Plugin(ABC):
    """
    Base class for all monitoring plugins.

    To create a new plugin:
    1. Create a config class extending CheckConfig
    2. Create a plugin class extending Plugin
    3. Set name, description, and config_class attributes
    4. Implement the execute() method
    """

    # Required class attributes - must be set by subclasses
    name: str  # Plugin type identifier (e.g., "cmdcheck")
    description: str  # Help text for CLI
    config_class: Type[CheckConfig]  # Pydantic model for this plugin

    def __init__(
        self,
        global_config: GlobalConfig,
        ssh_runner: Optional["SSHRunner"] = None,
        output_handler: Optional[OutputHandler] = None,
    ):
        self.global_config = global_config
        self.ssh_runner = ssh_runner
        self.output_handler = output_handler or OutputHandler()

        # Initialize heartbeat and SSH
        self.heartbeat: Optional[HeartbeatService] = None
        self._initialize_heartbeat()
        self._initialize_ssh()

        # Validate class attributes
        if not hasattr(self, "name") or not self.name:
            raise ValueError(
                f"Plugin {self.__class__.__name__} must define 'name' attribute"
            )
        if not hasattr(self, "description") or not self.description:
            raise ValueError(
                f"Plugin {self.__class__.__name__} must define 'description' attribute"
            )
        if not hasattr(self, "config_class"):
            raise ValueError(
                f"Plugin {self.__class__.__name__} must define 'config_class' attribute"
            )

    def _initialize_heartbeat(self) -> None:
        """Initialize heartbeat service if configured."""
        from kuma_scout.cli.config_merger import ConfigMerger

        heartbeat_config = self.global_config.heartbeat

        if not heartbeat_config.enabled:
            self.output_handler.debug(
                "Heartbeat disabled (heartbeat.enabled=false)", echo=False
            )
            return

        # Get merged URL and token from heartbeat + global config
        url, token = ConfigMerger.merge_heartbeat_uptime_kuma_config(self.global_config)

        if not token:
            self.output_handler.warning(
                "Heartbeat enabled but token missing - check will run without heartbeat notifications",
                echo=False,
            )
            return

        if not url:
            self.output_handler.warning(
                "Heartbeat enabled but Uptime Kuma URL missing - check will run without heartbeat notifications",
                echo=False,
            )
            return

        self.heartbeat = HeartbeatService(
            self.output_handler,
            str(url),
            str(token),
            heartbeat_config.interval,
            check_name=self.name,
        )
        self.output_handler.debug(
            f"Heartbeat initialized (interval: {heartbeat_config.interval}s)",
            echo=False,
        )

    def _initialize_ssh(self) -> None:
        """Initialize SSH runner if SSH is configured in global config."""
        if not self.global_config.ssh:
            return

        ssh_config = self.global_config.ssh
        self.ssh_runner = SSHRunner(
            host=ssh_config.host,
            user=ssh_config.user,
            port=ssh_config.port,
            key_file=ssh_config.key_file,
            password=ssh_config.password,
            strict_host_key_checking=ssh_config.strict_host_key_checking,
        )
        self.output_handler.debug(
            f"SSH runner initialized: {ssh_config.user or 'current_user'}@{ssh_config.host}",
            echo=False,
        )

    def execute_with_heartbeat(self, config: CheckConfig) -> CheckResult:
        """Execute check with automatic heartbeat management.

        Sends heartbeat at start and end (with duration), starts the service
        before execution and stops it afterward. Sets execution context for
        structured error logging throughout execution.

        Args:
            config: Plugin-specific configuration

        Returns:
            CheckResult from the check execution
        """
        # Create config snapshot for error context (without sensitive data)
        config_snapshot = {
            "name": config.name,
            "timeout": config.timeout,
            "retry_attempts": config.retry.attempts,
            "retry_delay_seconds": config.retry.delay_seconds,
        }

        with execution_context_manager(
            check_name=config.name,
            plugin_type=self.name,
            config_snapshot=config_snapshot,
        ):
            try:
                self._start_heartbeat()
                result = self._execute_with_retry(config)
                self._send_heartbeat_completion(result)
                return result
            except TimeoutError as e:
                sanitized_error = DataSanitizer.sanitize_error_message(e)
                self.output_handler.error(
                    f"Check timed out: {sanitized_error}", echo=False
                )
                raise
            except Exception as e:
                sanitized_error = DataSanitizer.sanitize_error_message(e)
                self.output_handler.error(
                    f"Check failed with unexpected error: {sanitized_error}",
                    echo=False,
                )
                raise
            finally:
                self._stop_heartbeat()

    def _start_heartbeat(self) -> None:
        """Initialize and start heartbeat service if configured."""
        if self.heartbeat:
            self.output_handler.debug(
                f"Sending heartbeat start message for {self.name}", echo=False
            )
            self.heartbeat.send_message(f"{self.name} check starting...")
            self.heartbeat.start()
            self.output_handler.debug(
                f"Heartbeat service started for {self.name}", echo=False
            )

    def _execute_with_retry(self, config: CheckConfig) -> CheckResult:
        """Execute the check with retry logic."""
        self.output_handler.info(f"Executing {self.name} check", echo=False)
        self.output_handler.debug(
            f"Retry config: attempts={config.retry.attempts}, delay={config.retry.delay_seconds}s",
            echo=False,
        )

        result = None
        for attempt in range(config.retry.attempts + 1):
            try:
                result = self.execute(config)
                if result.status == "up":
                    break
                else:
                    if attempt < config.retry.attempts:
                        self.output_handler.warning(
                            f"Check failed (status: {result.status}), retrying in {config.retry.delay_seconds}s "
                            f"(attempt {attempt + 1}/{config.retry.attempts + 1})",
                            echo=False,
                        )
                        time.sleep(config.retry.delay_seconds)
            except Exception as e:
                if attempt < config.retry.attempts:
                    sanitized_error = DataSanitizer.sanitize_error_message(e)
                    self.output_handler.warning(
                        f"Check failed with exception, retrying in {config.retry.delay_seconds}s "
                        f"(attempt {attempt + 1}/{config.retry.attempts + 1}): {sanitized_error}",
                        echo=False,
                    )
                    time.sleep(config.retry.delay_seconds)
                else:
                    raise

        if result is None:
            raise RuntimeError(
                f"{self.name} check failed after {config.retry.attempts + 1} attempts"
            )

        self.output_handler.info(
            f"{self.name} check completed with status: {result.status}", echo=False
        )
        return result

    def _send_heartbeat_completion(self, result: CheckResult) -> None:
        """Send heartbeat completion message."""
        if self.heartbeat:
            self.output_handler.debug(
                f"Sending heartbeat completion message for {self.name}", echo=False
            )
            self.heartbeat.send_message(
                f"{self.name} completed in {result.duration_seconds}s (status: {result.status})"
            )

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat service if running."""
        if self.heartbeat:
            self.output_handler.debug(
                f"Stopping heartbeat service for {self.name}", echo=False
            )
            self.heartbeat.stop()

    @abstractmethod
    def execute(self, config: CheckConfig) -> "CheckResult":
        """
        Execute the monitoring check.

        Args:
            config: Plugin-specific configuration

        Returns:
            CheckResult with status, message, and details
        """
        pass

    def run_command(
        self,
        cmd: list[str],
        timeout: Optional[int] = None,
    ) -> tuple[bool, str, str, int]:
        """
        Execute a command locally or via SSH.

        Returns:
            Tuple of (success, stdout, stderr, exit_code)
        """
        timeout = timeout or 30

        if self.ssh_runner:
            target = f"{self.ssh_runner.user or 'current_user'}@{self.ssh_runner.host}"
            if self.ssh_runner.port != 22:
                target += f":{self.ssh_runner.port}"
            self.output_handler.info(
                f"Running command via SSH on {target}...", echo=False
            )
            self.output_handler.debug(f"Command: {' '.join(cmd)}", echo=False)
            try:
                success, stdout, stderr, exit_code = self.ssh_runner.run(cmd, timeout)
                return success, stdout, stderr, exit_code
            except SSHConnectionError as e:
                self.output_handler.warning(
                    f"SSH connection failed: {e.message}", echo=True
                )
                return False, "", f"SSH connection failed: {e.message}", -1

        # Local execution
        self.output_handler.info("Running command locally...", echo=False)
        self.output_handler.debug(f"Command: {' '.join(cmd)}", echo=False)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                result.returncode,
            )
        except subprocess.TimeoutExpired:
            self.output_handler.warning(
                f"Command timed out after {timeout}s", echo=True
            )
            return False, "", f"Command timed out after {timeout}s", -1
        except FileNotFoundError:
            self.output_handler.warning(f"Command not found: {cmd[0]}", echo=True)
            return False, "", f"Command not found: {cmd[0]}", -1
        except Exception as e:
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.output_handler.warning(
                f"Command execution failed: {sanitized_error}", echo=True
            )
            return False, "", f"Command execution failed: {sanitized_error}", -1
