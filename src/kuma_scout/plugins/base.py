"""
Base classes for Kuma-Scout plugins.

This module defines the Plugin base class and CheckConfig model that all
monitoring plugins must inherit from.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import ClassVar, Optional, Type

from pydantic import BaseModel, ConfigDict, Field

from ..core.heartbeat import HeartbeatService
from ..core.models import CheckResult
from ..core.utils.sanitizer import DataSanitizer
from ..core.utils.ssh_runner import SSHConnectionError, SSHRunner
from .models import GlobalConfig, RetryConfig, UptimeKumaConfig


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
    name: ClassVar[str]  # Plugin type identifier (e.g., "cmdcheck")
    description: ClassVar[str]  # Help text for CLI
    config_class: ClassVar[Type[CheckConfig]]  # Pydantic model for this plugin

    def __init__(
        self,
        global_config: GlobalConfig,
        ssh_runner: Optional["SSHRunner"] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.global_config = global_config
        self.ssh_runner = ssh_runner
        self.logger = logger or logging.getLogger(f"kuma_scout.plugins.{self.name}")

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
        heartbeat_config = self.global_config.heartbeat
        uptime_config = self.global_config.uptime_kuma

        if not heartbeat_config.enabled:
            self.logger.debug("ℹ️  Heartbeat disabled (heartbeat.enabled=false)")
            return

        if not heartbeat_config.token:
            self.logger.warning(
                "⚠️  Heartbeat enabled but token missing - check will run without heartbeat notifications"
            )
            return

        if not uptime_config or not uptime_config.url:
            self.logger.warning(
                "⚠️  Heartbeat enabled but Uptime Kuma URL missing - check will run without heartbeat notifications"
            )
            return

        self.heartbeat = HeartbeatService(
            self.logger,
            str(uptime_config.url),
            str(heartbeat_config.token),
            heartbeat_config.interval,
            check_name=self.name,
        )
        self.logger.debug(
            f"✅ Heartbeat initialized (interval: {heartbeat_config.interval}s)"
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
        self.logger.debug(
            f"🔌 SSH runner initialized: {ssh_config.user or 'current_user'}@{ssh_config.host}"
        )

    def execute_with_heartbeat(self, config: CheckConfig) -> CheckResult:
        """Execute check with automatic heartbeat management.

        Sends heartbeat at start and end (with duration), starts the service
        before execution and stops it afterward.

        Args:
            config: Plugin-specific configuration

        Returns:
            CheckResult from the check execution
        """
        try:
            self._start_heartbeat()
            result = self._execute_with_retry(config)
            self._send_heartbeat_completion(result)
            return result
        except TimeoutError as e:
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(f"❌ {self.name} check timed out: {sanitized_error}")
            raise
        except Exception as e:
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(
                f"❌ {self.name} check failed with unexpected error: {sanitized_error}"
            )
            raise
        finally:
            self._stop_heartbeat()

    def _start_heartbeat(self) -> None:
        """Initialize and start heartbeat service if configured."""
        if self.heartbeat:
            self.logger.debug(f"📤 Sending heartbeat start message for {self.name}")
            self.heartbeat.send_message(f"{self.name} check starting...")
            self.heartbeat.start()
            self.logger.debug(f"✅ Heartbeat service started for {self.name}")

    def _execute_with_retry(self, config: CheckConfig) -> CheckResult:
        """Execute the check with retry logic."""
        self.logger.info(f"▶️  Executing {self.name} check")
        self.logger.debug(
            f"🔄 Retry config: attempts={config.retry.attempts}, delay={config.retry.delay_seconds}s"
        )

        result = None
        for attempt in range(config.retry.attempts + 1):
            try:
                result = self.execute(config)
                if result.status == "up":
                    break
                else:
                    if attempt < config.retry.attempts:
                        self.logger.warning(
                            f"Check failed (status: {result.status}), retrying in {config.retry.delay_seconds}s "
                            f"(attempt {attempt + 1}/{config.retry.attempts + 1})"
                        )
                        time.sleep(config.retry.delay_seconds)
            except Exception as e:
                if attempt < config.retry.attempts:
                    sanitized_error = DataSanitizer.sanitize_error_message(e)
                    self.logger.warning(
                        f"Check failed with exception, retrying in {config.retry.delay_seconds}s "
                        f"(attempt {attempt + 1}/{config.retry.attempts + 1}): {sanitized_error}"
                    )
                    time.sleep(config.retry.delay_seconds)
                else:
                    raise

        if result is None:
            raise RuntimeError(
                f"{self.name} check failed after {config.retry.attempts + 1} attempts"
            )

        self.logger.info(f"✅ {self.name} check completed with status: {result.status}")
        return result

    def _send_heartbeat_completion(self, result: CheckResult) -> None:
        """Send heartbeat completion message."""
        if self.heartbeat:
            status_emoji = "✅" if result.status == "up" else "❌"
            self.logger.debug(
                f"📤 Sending heartbeat completion message for {self.name}"
            )
            self.heartbeat.send_message(
                f"{status_emoji} {self.name} completed in {result.duration_seconds}s"
            )

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat service if running."""
        if self.heartbeat:
            self.logger.debug(f"🛑 Stopping heartbeat service for {self.name}")
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
            target = f"{self.global_config.ssh.user or 'current_user'}@{self.global_config.ssh.host}"
            if self.global_config.ssh.port != 22:
                target += f":{self.global_config.ssh.port}"
            self.logger.debug(f"🔌 Running command on {target}: {' '.join(cmd)}")
            try:
                success, stdout, stderr, exit_code = self.ssh_runner.run(cmd, timeout)
                return success, stdout, stderr, exit_code
            except SSHConnectionError as e:
                self.logger.error(f"🔌 SSH connection failed: {e.message}")
                return False, "", f"SSH connection failed: {e.message}", -1

        # Local execution
        import subprocess

        self.logger.debug(f"🔧 Running command: {' '.join(cmd)}")
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
            self.logger.error(f"❌ Command timed out after {timeout}s")
            return False, "", f"Command timed out after {timeout}s", -1
        except Exception as e:
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(f"❌ Command execution failed: {sanitized_error}")
            return False, "", f"Command execution failed: {sanitized_error}", -1

    def get_effective_config(self, check_config: CheckConfig) -> dict:
        """
        Merge global config with check-specific overrides.

        Returns effective configuration for this check.
        """
        # Start with global config
        effective = {
            "uptime_kuma": self.global_config.uptime_kuma.model_dump(),
            "ssh": (
                self.global_config.ssh.model_dump() if self.global_config.ssh else None
            ),
            "timeout": check_config.timeout,
            "retry": check_config.retry.model_dump(),
        }

        # Apply check-specific overrides
        if check_config.uptime_kuma:
            effective["uptime_kuma"].update(
                check_config.uptime_kuma.model_dump(exclude_unset=True)
            )

        # Note: SSH overrides would be handled here if needed

        return effective
