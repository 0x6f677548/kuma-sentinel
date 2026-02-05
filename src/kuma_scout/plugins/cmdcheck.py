"""
Command check plugin for Kuma-Scout.

Executes shell commands and reports results to Uptime Kuma.
"""

import re
import shlex
import time
from typing import Optional, cast

from pydantic import Field

from kuma_scout.core.models import CheckResult
from kuma_scout.core.utils.sanitizer import DataSanitizer

from .base import CheckConfig, Plugin


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

    def execute(self, config: CheckConfig) -> CheckResult:
        """Execute the command check."""
        # Cast to the specific config type
        config = cast(CmdCheckConfig, config)
        start_time = time.time()

        try:
            # Execute the command
            success, stdout, stderr, exit_code = self.run_command(
                shlex.split(config.command),
                timeout=config.timeout,
            )

            duration = time.time() - start_time

            # Sanitize output if requested
            sanitize_output = getattr(config, "sanitize_output", True)
            if sanitize_output:
                stdout = DataSanitizer.sanitize(stdout)
                stderr = DataSanitizer.sanitize(stderr)

            # Determine success based on exit code and patterns
            expect_exit_code = getattr(config, "expect_exit_code", 0)
            success_pattern = getattr(config, "success_pattern", None)
            failure_pattern = getattr(config, "failure_pattern", None)

            is_success = exit_code == expect_exit_code

            stdout_stripped = stdout.strip()
            if success_pattern and re.search(success_pattern, stdout_stripped):
                is_success = True
            elif failure_pattern and re.search(failure_pattern, stdout_stripped):
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
                duration_seconds=int(duration),
                details={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
            )

        except Exception as e:
            duration = time.time() - start_time
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Command execution failed: {str(e)}",
                duration_seconds=int(duration),
            )
