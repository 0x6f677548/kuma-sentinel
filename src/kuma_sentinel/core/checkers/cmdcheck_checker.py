"""Command check monitoring implementation."""

import re
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

        For single command:
        - Runs command with configured timeout
        - Applies pattern matching (failure > success > exit code)

        For multiple commands:
        - Runs all commands; ALL must succeed for UP status
        - Aggregates results

        Returns:
            CheckResult with status "up" or "down"
        """
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting command check")

            # Multiple commands mode
            if self.config.cmdcheck_multiple and self.config.cmdcheck_commands:
                return self._execute_multiple(check_start)

            # Single command mode
            if self.config.cmdcheck_command:
                return self._execute_single(check_start)

            # Should not reach here if validation passed
            duration = time.time() - check_start
            return CheckResult(
                check_name=self.name,
                status="down",
                message="No command configured",
                duration_seconds=duration,
                details=None,
            )

        except Exception as e:
            duration = time.time() - check_start
            self.logger.error(f"❌ Unexpected error: {e}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"Error: {str(e)}",
                duration_seconds=duration,
                details=None,
            )

    def _execute_single(self, check_start: float) -> CheckResult:
        """Execute single command and return result."""
        command = self.config.cmdcheck_command
        timeout = self.config.cmdcheck_timeout
        expect_exit_code = self.config.cmdcheck_expect_exit_code
        capture_output = self.config.cmdcheck_capture_output
        success_pattern = self.config.cmdcheck_success_pattern
        failure_pattern = self.config.cmdcheck_failure_pattern

        self.logger.debug(f"Running command: {command}")

        try:
            # Execute command with shell
            result = subprocess.run(
                command,
                shell=True,
                executable="/bin/bash",
                capture_output=capture_output,
                text=True,
                timeout=timeout,
            )

            # Combine stdout and stderr for pattern matching
            output = (result.stdout or "") + (result.stderr or "")

            # Truncate to last 500 chars
            output_truncated = output[-500:] if len(output) > 500 else output

            # Apply pattern matching logic
            status, reason = self._evaluate_result(
                exit_code=result.returncode,
                output=output_truncated,
                expect_exit_code=expect_exit_code,
                success_pattern=success_pattern,
                failure_pattern=failure_pattern,
            )

            duration = time.time() - check_start

            # Build detailed message for Uptime Kuma with visibility
            symbol = '✓' if status == 'up' else '✗'
            # Include command for clarity (truncate long commands to ~60 chars)
            cmd_display = (command or "")
            if len(cmd_display) > 60:
                cmd_display = cmd_display[:57] + "..."
            message = f"[{self.name}] {symbol} [{cmd_display}] {reason}"

            # Add output sample if available (truncate to keep URL param reasonable)
            if output_truncated and len(output_truncated) <= 100:
                message += f" | Output: {output_truncated[:100]}"

            self.logger.info(f"{'✅' if status == 'up' else '❌'} Single command check: {message}")

            return CheckResult(
                check_name=self.name,
                status=status,
                message=message,
                duration_seconds=int(duration),
                details={
                    "command": command,
                    "exit_code": result.returncode,
                    "output": output_truncated[:200]
                    if output_truncated
                    else "(no output)",
                    "reason": reason,
                },
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - check_start
            msg = f"[{self.name}] ✗ Command timed out after {timeout}s"
            self.logger.error(f"❌ {msg}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=msg,
                duration_seconds=int(duration),
                details={
                    "command": command,
                    "error": "timeout",
                    "timeout_seconds": timeout,
                },
            )

        except FileNotFoundError:
            duration = time.time() - check_start
            msg = f"[{self.name}] ✗ Command not found or /bin/bash not available"
            self.logger.error(f"❌ {msg}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=msg,
                duration_seconds=int(duration),
                details={
                    "command": command,
                    "error": "command_not_found",
                },
            )

        except Exception as e:
            duration = time.time() - check_start
            msg = f"[{self.name}] ✗ Command execution failed: {str(e)}"
            self.logger.error(f"❌ {msg}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=msg,
                duration_seconds=int(duration),
                details={
                    "command": command,
                    "error": str(e),
                },
            )

    def _execute_multiple(self, check_start: float) -> CheckResult:
        """Execute multiple commands - all must succeed for UP status."""
        commands = self.config.cmdcheck_commands
        results: List[Dict[str, Any]] = []
        failures = []

        timeout_default = self.config.cmdcheck_timeout
        expect_exit_code_default = self.config.cmdcheck_expect_exit_code
        success_pattern_default = self.config.cmdcheck_success_pattern
        failure_pattern_default = self.config.cmdcheck_failure_pattern
        capture_output_default = self.config.cmdcheck_capture_output

        for idx, cmd_config in enumerate(commands):
            cmd_start = time.time()
            command = cmd_config.get("command", "")

            # Get per-command overrides or use defaults
            timeout = cmd_config.get("timeout", timeout_default)
            expect_exit_code = cmd_config.get("expect_exit_code", expect_exit_code_default)
            success_pattern = cmd_config.get("success_pattern", success_pattern_default)
            failure_pattern = cmd_config.get("failure_pattern", failure_pattern_default)
            capture_output = cmd_config.get("capture_output", capture_output_default)
            name = cmd_config.get("name", f"cmd_{idx}")

            self.logger.debug(f"Running command {idx + 1}/{len(commands)}: {name}")

            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    executable="/bin/bash",
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
                    "output": output_truncated[:200] if output_truncated else "(no output)",
                    "duration_seconds": duration,
                }

                results.append(cmd_result)

                if status == "down":
                    failures.append(f"{name}[{command}] ({message})")

            except subprocess.TimeoutExpired:
                duration = time.time() - cmd_start
                results.append(
                    {
                        "name": name,
                        "command": command,
                        "status": "down",
                        "exit_code": None,
                        "output": f"Timeout after {timeout}s",
                        "duration_seconds": duration,
                    }
                )
                failures.append(f"{name}[{command}] (timeout)")

            except Exception as e:
                duration = time.time() - cmd_start
                results.append(
                    {
                        "name": name,
                        "command": command,
                        "status": "down",
                        "exit_code": None,
                        "output": str(e),
                        "duration_seconds": duration,
                    }
                )
                failures.append(f"{name}[{command}] ({str(e)})")

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
                    reason = failure[bracket_end + 2:-1]  # Skip "] ("
                    # Truncate command if too long
                    if len(cmd) > 30:
                        cmd = cmd[:27] + "..."
                    formatted_failures.append(f"{failure.split('[')[0]}[{cmd}] ({reason})")
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
        self.logger.info(f"✅ Multiple commands check completed: {message} | {status_breakdown}")

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
