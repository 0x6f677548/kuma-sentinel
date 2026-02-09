"""
Command check plugin for Kuma-Scout.

Executes shell commands and reports results to Uptime Kuma.
"""

import re
import shlex
from typing import Optional

from pydantic import Field

from kuma_scout.core.logger import log_security_event
from kuma_scout.core.models import CheckResult
from kuma_scout.core.utils.sanitizer import DataSanitizer

from .base import CheckConfig, Plugin, execute_with_timing


class CmdCheckConfig(CheckConfig):
    """Configuration for command check plugin."""

    command: str = Field(description="Shell command to execute")
    expect_exit_code: int = Field(
        default=0, description="Expected exit code for success"
    )
    success_pattern: Optional[str] = Field(
        default=None, description="Regex pattern that indicates success"
    )
    failure_pattern: Optional[str] = Field(
        default=None, description="Regex pattern that indicates failure"
    )
    sanitize_output: bool = Field(
        default=True, description="Whether to sanitize sensitive data in output"
    )


class CmdCheckPlugin(Plugin):
    """Plugin for executing shell commands."""

    name = "cmdcheck"
    description = "Executes shell commands and reports results to Uptime Kuma"
    config_class = CmdCheckConfig

    @execute_with_timing
    def execute(self, config: CmdCheckConfig) -> CheckResult:
        """Execute the command check."""
        # Check for dangerous commands
        self._check_for_dangerous_commands(config.command)

        self.output_handler.info("CmdCheck: Executing...", echo=False)
        self.output_handler.debug(f"Command: {config.command}", echo=False)

        # Execute the command
        success, stdout, stderr, exit_code = self.run_command(
            shlex.split(config.command),
            timeout=config.timeout,
        )

        # Sanitize output if requested
        if config.sanitize_output:
            stdout = DataSanitizer.sanitize(stdout)
            stderr = DataSanitizer.sanitize(stderr)

        # Determine success based on exit code and patterns
        is_success = exit_code == config.expect_exit_code

        stdout_stripped = stdout.strip()
        if config.success_pattern and re.search(config.success_pattern, stdout_stripped):
            is_success = True
        elif config.failure_pattern and re.search(config.failure_pattern, stdout_stripped):
            is_success = False

        # Build message
        message_parts = []
        if stdout.strip():
            message_parts.append(f"stdout: {stdout.strip()}")
        if stderr.strip():
            message_parts.append(f"stderr: {stderr.strip()}")
        if not message_parts:
            message_parts.append(f"exit code: {exit_code}")

        message = "; ".join(message_parts)

        return CheckResult(
            check_name=config.name,
            status="up" if is_success else "down",
            message=message,
            duration_seconds=0,  # Will be set by decorator
            details={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
        )

    def _check_for_dangerous_commands(self, command: str) -> None:
        """Check for potentially dangerous commands and log security events."""
        dangerous_patterns = [
            r"\brm\s+-rf\s+/?",  # rm -rf /
            r"\brm\s+-rf\s+\*",  # rm -rf *
            r"\bdd\s+if=",  # dd commands that might overwrite disks
            r"\bformat\s+",  # format commands
            r"\bmkfs\.",  # filesystem creation commands
            r"\bfdisk\s+",  # disk partitioning
            r"\bwipefs\s+",  # wipe filesystem signatures
            r"\bshred\s+",  # secure file deletion
            r"\bsudo\s+.*\b(rm|dd|format|mkfs|fdisk|wipefs|shred)\b",  # sudo with dangerous commands
        ]

        command_lower = command.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, command_lower, re.IGNORECASE):
                log_security_event(
                    "dangerous_command_detected",
                    f"Potentially dangerous command detected: {command}",
                    level="warning",
                    echo=False,
                )
                break  # Only log once per command
