"""Abstract base class for scout checks."""

import subprocess
import time
from abc import ABC, abstractmethod
from logging import Logger
from typing import List, Optional, Tuple

from kuma_scout.core.config.base import ConfigBase
from kuma_scout.core.heartbeat import HeartbeatService
from kuma_scout.core.models import CheckResult
from kuma_scout.core.utils.sanitizer import DataSanitizer
from kuma_scout.core.utils.ssh_runner import SSHConnectionError, SSHRunner


class Checker(ABC):
    """Base class for all scout checks.

    Subclasses must implement the execute() method to perform the check
    and return a CheckResult. Heartbeat support is built-in and can be
    enabled via configuration for any check.

    Supports remote execution via SSH if configured.
    """

    name: str = ""  # e.g., "portscan"
    description: str = ""  # e.g., "Scans TCP ports on target ranges"

    def __init__(self, logger: Logger, config: ConfigBase):
        """Initialize the checker.

        Args:
            logger: Logger instance for output
            config: Configuration object for this check
        """
        if not self.name:
            raise ValueError(f"Checker {self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(
                f"Checker {self.__class__.__name__} must define 'description'"
            )
        self.logger = logger
        self.config = config
        self.heartbeat: Optional[HeartbeatService] = None
        self._ssh_runner: Optional[SSHRunner] = None
        self._initialize_heartbeat()
        self._initialize_ssh()

    def _initialize_ssh(self) -> None:
        """Initialize SSH runner if SSH is configured."""
        if self.config.ssh_host:
            # Get effective SSH settings, preferring command-specific over global
            command_name = self.config._get_command_name()

            def get_ssh_attr(attr_name: str):
                """Get SSH attribute, checking command-specific first."""
                if command_name:
                    cmd_attr = f"{command_name}_{attr_name}"
                    if hasattr(self.config, cmd_attr):
                        return getattr(self.config, cmd_attr)
                return getattr(self.config, attr_name)

            self._ssh_runner = SSHRunner(
                host=self.config.ssh_host,
                user=self.config.ssh_user,
                port=self.config.ssh_port or 22,
                key_file=get_ssh_attr("ssh_key_file"),
                password=get_ssh_attr("ssh_password"),
                strict_host_key_checking=get_ssh_attr("ssh_strict_host_key_checking"),
            )
            self.logger.debug(
                f"🔌 SSH runner initialized for {self.name}: "
                f"{self.config.ssh_user or 'current_user'}@{self.config.ssh_host}"
            )

    def run_command(
        self, cmd: List[str], timeout: Optional[int] = None
    ) -> Tuple[bool, str, str, int]:
        """Run a command locally or via SSH based on configuration.

        If SSH is configured (ssh_host is set), the command will be executed
        on the remote host. Otherwise, it runs locally.

        Args:
            cmd: Command to execute as list of arguments
            timeout: Timeout in seconds (overrides default if provided)

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str, returncode: int)
        """
        if self._ssh_runner:
            target = f"{self.config.ssh_user or 'current_user'}@{self.config.ssh_host}"
            if self.config.ssh_port != 22:
                target += f":{self.config.ssh_port}"
            self.logger.debug(f"🔌 Running command on {target}: {' '.join(cmd)}")
            try:
                success, stdout, stderr, exit_code = self._ssh_runner.run(cmd)
                # SSH returns success boolean and exit code
                return success, stdout, stderr, exit_code
            except SSHConnectionError as e:
                self.logger.error(f"🔌 SSH connection failed: {e.message}")
                return False, "", f"SSH connection failed: {e.message}", -1

        # Local execution
        self.logger.debug(f"🖥️  Running command locally: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or 30,
                shell=False,  # Explicitly disable shell for security
            )
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                result.returncode,
            )
        except subprocess.TimeoutExpired:
            self.logger.error(f"⏱️  Command timed out: {' '.join(cmd)}")
            raise  # Re-raise so checkers can handle it appropriately
        except FileNotFoundError:
            # Command not found - this is a common error that should be reported
            self.logger.error(f"❌ Command not found: {' '.join(cmd)}")
            return False, "", f"Command not found: {cmd[0]}", -1
        except PermissionError:
            # Permission denied - this is a common error that should be reported
            self.logger.error(f"❌ Permission denied: {' '.join(cmd)}")
            return False, "", f"Permission denied: {cmd[0]}", -1
        except Exception as e:
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(f"❌ Command failed: {sanitized_error}")
            return False, "", str(sanitized_error), -1

    def _initialize_heartbeat(self) -> None:
        """Initialize heartbeat service if enabled in config.

        Logs the status of heartbeat initialization including any missing
        configuration that would prevent heartbeat from running.
        """
        heartbeat_enabled = self.config.heartbeat_enabled
        heartbeat_token = self.config.heartbeat_token
        uptime_kuma_url = self.config.uptime_kuma_url
        heartbeat_interval = self.config.heartbeat_interval

        # Convert string "True"/"False" to boolean if needed
        if isinstance(heartbeat_enabled, str):
            heartbeat_enabled = heartbeat_enabled.lower() == "true"

        # Log heartbeat status
        if not heartbeat_enabled:
            self.logger.debug(
                f"ℹ️  Heartbeat disabled for {self.name} (heartbeat.enabled=false)"
            )
            return

        if not heartbeat_token:
            self.logger.warning(
                f"⚠️  Heartbeat enabled but token missing for {self.name} - "
                f"check will run without heartbeat notifications"
            )
            return

        if not uptime_kuma_url:
            self.logger.warning(
                f"⚠️  Heartbeat enabled but Uptime Kuma URL missing for {self.name} - "
                f"check will run without heartbeat notifications"
            )
            return

        if heartbeat_enabled and heartbeat_token and uptime_kuma_url:
            self.heartbeat = HeartbeatService(
                self.logger,
                str(uptime_kuma_url),
                str(heartbeat_token),
                heartbeat_interval,
                check_name=self.name,
            )
            self.logger.debug(
                f"✅ Heartbeat initialized for {self.name} (interval: {heartbeat_interval}s)"
            )

    @abstractmethod
    def execute(self) -> CheckResult:
        """Execute the check and return result.

        Returns:
            CheckResult with check outcome
        """
        pass

    def execute_with_heartbeat(self) -> CheckResult:
        """Execute check with automatic heartbeat management.

        Sends heartbeat at start and end (with duration), starts the service
        before execution and stops it afterward. Logs execution timeline and
        any errors that occur during execution.

        Returns:
            CheckResult from the check execution
        """
        try:
            self._start_heartbeat()
            result = self._execute_with_retry()
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

    def _execute_with_retry(self) -> CheckResult:
        """Execute the check with retry logic."""
        self.logger.info(f"▶️  Executing {self.name} check")
        self.logger.debug(
            f"🔄 Retry config: attempts={self.config.retry_attempts}, delay={self.config.retry_delay_seconds}s"
        )
        result = None
        for attempt in range(self.config.retry_attempts + 1):
            try:
                result = self.execute()
                if result.status == "up":
                    break
                else:
                    if attempt < self.config.retry_attempts:
                        self.logger.warning(
                            f"Check failed (status: {result.status}), retrying in {self.config.retry_delay_seconds}s "
                            f"(attempt {attempt + 1}/{self.config.retry_attempts + 1})"
                        )
                        time.sleep(self.config.retry_delay_seconds)
            except Exception as e:
                if attempt < self.config.retry_attempts:
                    sanitized_error = DataSanitizer.sanitize_error_message(e)
                    self.logger.warning(
                        f"Check failed with exception, retrying in {self.config.retry_delay_seconds}s "
                        f"(attempt {attempt + 1}/{self.config.retry_attempts + 1}): {sanitized_error}"
                    )
                    time.sleep(self.config.retry_delay_seconds)
                else:
                    raise
        if result is None:
            raise RuntimeError(
                f"{self.name} check failed after {self.config.retry_attempts + 1} attempts"
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
            self.logger.debug(f"Stopping heartbeat service for {self.name}")
            self.heartbeat.stop()
