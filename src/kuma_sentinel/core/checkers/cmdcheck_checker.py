"""Command check monitoring implementation."""

import re
import shlex
import subprocess
import time
from logging import Logger
from typing import Any, Dict, List, Optional, Tuple

from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig
from kuma_sentinel.core.models import CheckResult

from .base import Checker


class CmdCheckChecker(Checker):
    """Checker for monitoring arbitrary shell commands."""

    name = "cmdcheck"
    description = "Executes shell commands and reports results to Uptime Kuma"

    def __init__(self, logger: Logger, config: CmdCheckConfig):
        """Initialize command check checker.

        Args:
            logger: Logger instance
            config: CmdCheckConfig instance
        """
        super().__init__(logger, config)
        self.config: CmdCheckConfig = config

    def execute(self) -> CheckResult:
        """Execute command check(s) and return result.

        Commands are always stored as a list, even for single commands.
        - Runs all commands; ALL must succeed for UP status
        - Applies pattern matching (failure > success > exit code)

        Returns:
            CheckResult with status "up" or "down"
        """
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting command check")

            # Always use list-based execution
            if not self.config.cmdcheck_commands:
                # Should not reach here if validation passed
                duration = time.time() - check_start
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message="No commands configured",
                    duration_seconds=int(duration),
                    details={},
                )

            return self._execute_commands(check_start)

        except Exception as e:
            duration = time.time() - check_start
            self.logger.error(f"❌ Unexpected error: {e}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"Error: {str(e)}",
                duration_seconds=int(duration),
                details={},
            )

    def _execute_single_command(
        self, cmd_config: Dict[str, Any], idx: int
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a single command and return its result and optional failure message.

        Returns:
            Tuple of (result_dict, failure_message_or_none)
        """
        cmd_start = time.time()
        command = cmd_config.get("command", "")
        name = cmd_config.get("name", f"cmd_{idx}")

        # Get per-command overrides or use defaults
        timeout = cmd_config.get("timeout", self.config.cmdcheck_timeout)
        expect_exit_code = cmd_config.get(
            "expect_exit_code", self.config.cmdcheck_expect_exit_code
        )
        success_pattern = cmd_config.get(
            "success_pattern", self.config.cmdcheck_success_pattern
        )
        failure_pattern = cmd_config.get(
            "failure_pattern", self.config.cmdcheck_failure_pattern
        )
        capture_output = cmd_config.get(
            "capture_output", self.config.cmdcheck_capture_output
        )

        self.logger.debug(f"Running command {idx + 1}: {name}")

        try:
            # Parse command string into argument list for safe execution
            # shell=False prevents shell metacharacter interpretation (security)
            try:
                args = shlex.split(command)
            except ValueError as e:
                # shlex.split() raises ValueError for unclosed quotes
                duration = time.time() - cmd_start
                return (
                    {
                        "name": name,
                        "command": command,
                        "status": "down",
                        "exit_code": None,
                        "output": f"Invalid command syntax: {str(e)}",
                        "duration_seconds": duration,
                    },
                    f"{name}[{command}] (Invalid command syntax)",
                )

            result = subprocess.run(
                args,
                shell=False,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
            )

            output = (result.stdout or "") + (result.stderr or "")
            output_truncated = output[-500:] if len(output) > 500 else output

            status, message = self._evaluate_result(
                exit_code=result.returncode,
                output=output_truncated,
                expect_exit_code=expect_exit_code,
                success_pattern=success_pattern,
                failure_pattern=failure_pattern,
            )

            duration = time.time() - cmd_start

            cmd_result = {
                "name": name,
                "command": command,
                "status": status,
                "exit_code": result.returncode,
                "output": (
                    output_truncated[:200] if output_truncated else "(no output)"
                ),
                "duration_seconds": duration,
            }

            failure_msg = None
            if status == "down":
                failure_msg = f"{name}[{command}] ({message})"

            return cmd_result, failure_msg

        except subprocess.TimeoutExpired:
            duration = time.time() - cmd_start
            return (
                {
                    "name": name,
                    "command": command,
                    "status": "down",
                    "exit_code": None,
                    "output": f"Timeout after {timeout}s",
                    "duration_seconds": duration,
                },
                f"{name}[{command}] (timeout)",
            )

        except Exception as e:
            duration = time.time() - cmd_start
            return (
                {
                    "name": name,
                    "command": command,
                    "status": "down",
                    "exit_code": None,
                    "output": str(e),
                    "duration_seconds": duration,
                },
                f"{name}[{command}] ({str(e)})",
            )

    def _execute_commands(self, check_start: float) -> CheckResult:
        """Execute all commands - all must succeed for UP status.

        Even for a single command, it's treated as a list for consistency.
        """
        commands = self.config.cmdcheck_commands
        results: List[Dict[str, Any]] = []
        failures = []

        for idx, cmd_config in enumerate(commands):
            cmd_result, failure_msg = self._execute_single_command(cmd_config, idx)
            results.append(cmd_result)
            if failure_msg:
                failures.append(failure_msg)

        # Determine overall status and message
        duration = time.time() - check_start

        # Build summary for Uptime Kuma with per-command visibility
        passed_count = len([r for r in results if r["status"] == "up"])
        failed_count = len(failures)

        if failures:
            status = "down"
            # Format: "✗ 1/3 passed, 2/3 failed: nginx[systemctl...] (exit 1); redis[redis-cli...] (timeout); +2 more"
            # Truncate commands to ~30 chars to keep message reasonable for URL limits
            formatted_failures = []
            for failure in failures[:3]:
                # Extract command from format "name[command] (reason)"
                if "[" in failure and "]" in failure:
                    bracket_start = failure.index("[") + 1
                    bracket_end = failure.index("]")
                    cmd = failure[bracket_start:bracket_end]
                    reason = failure[bracket_end + 2 : -1]  # Skip "] ("
                    # Truncate command if too long
                    if len(cmd) > 30:
                        cmd = cmd[:27] + "..."
                    formatted_failures.append(
                        f"{failure.split('[')[0]}[{cmd}] ({reason})"
                    )
                else:
                    formatted_failures.append(failure)

            failure_summary = "; ".join(formatted_failures)
            if failed_count > 3:
                failure_summary += f"; +{failed_count - 3} more"
            message = f"[{self.name}] ✗ {passed_count}/{len(commands)} passed, {failed_count}/{len(commands)} failed: {failure_summary}"
        else:
            status = "up"
            # List all passed commands
            cmd_list = ", ".join([r["name"] for r in results])
            message = f"[{self.name}] ✓ All {len(commands)}/{len(commands)} commands passed: {cmd_list}"

        # Log detailed breakdown for debugging
        status_breakdown = "; ".join(
            [f"[{r['name']}: {'✓' if r['status'] == 'up' else '✗'}]" for r in results]
        )
        self.logger.info(f"✅ Commands check completed: {message} | {status_breakdown}")

        return CheckResult(
            check_name=self.name,
            status=status,
            message=message,
            duration_seconds=int(duration),
            details={
                "commands": results,
                "summary": {
                    "total": len(commands),
                    "passed": passed_count,
                    "failed": failed_count,
                },
            },
        )

    @staticmethod
    def _evaluate_result(
        exit_code: int,
        output: str,
        expect_exit_code: int,
        success_pattern: Optional[str],
        failure_pattern: Optional[str],
    ) -> Tuple[str, str]:
        """Evaluate command result using pattern matching or exit code.

        Logic:
        1. failure_pattern: If matches → "down"
        2. success_pattern: If matches → "up"
        3. Both patterns provided but neither matches → "down"
        4. No patterns → use exit code comparison

        Args:
            exit_code: Command exit code
            output: Combined stdout/stderr
            expect_exit_code: Expected exit code for success
            success_pattern: Regex pattern for success
            failure_pattern: Regex pattern for failure

        Returns:
            Tuple of (status, message)
        """
        # Check failure pattern first (highest priority)
        if failure_pattern:
            if re.search(failure_pattern, output):
                return "down", f"Failure pattern detected: {failure_pattern}"

        # Check success pattern
        if success_pattern:
            if re.search(success_pattern, output):
                return "up", f"Success pattern detected: {success_pattern}"
            # If success pattern provided but doesn't match, it's a failure
            return "down", f"Success pattern not found: {success_pattern}"

        # Fall back to exit code
        if exit_code == expect_exit_code:
            return "up", f"Command succeeded (exit {exit_code})"

        return "down", f"Command failed (exit {exit_code}, expected {expect_exit_code})"
