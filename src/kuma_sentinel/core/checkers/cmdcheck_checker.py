"""Command check monitoring implementation."""

import re
import shlex
import subprocess
import time
from logging import Logger
from typing import Any, Dict, List, Optional, Tuple

from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig
from kuma_sentinel.core.logger import log_security_event
from kuma_sentinel.core.models import CheckResult
from kuma_sentinel.core.utils.sanitizer import DataSanitizer

from .base import Checker


class CmdCheckChecker(Checker):
    """Checker for monitoring arbitrary shell commands."""

    name = "cmdcheck"
    description = "Executes shell commands and reports results to Uptime Kuma"

    # Dangerous command patterns that should be executed only with read-only intent
    # Maps tool names to configuration with trigger pattern and dangerous arguments
    DANGEROUS_PATTERNS: Dict[str, Dict[str, Any]] = {
        # System service management
        "systemctl": {
            "trigger": "systemctl",
            "dangerous_args": [
                "start",
                "stop",
                "restart",
                "reload",
                "enable",
                "disable",
                "reenable",
                "reset-failed",
            ],
            "warning": "may modify system state",
        },
        "service": {
            "trigger": "service",
            "dangerous_args": [
                "start",
                "stop",
                "restart",
                "reload",
                "enable",
                "disable",
            ],
            "warning": "may modify system services",
        },
        # Package managers
        "apt": {
            "trigger": "apt",
            "dangerous_args": [
                "install",
                "remove",
                "purge",
                "autoremove",
                "autoclean",
                "upgrade",
                "full-upgrade",
            ],
            "warning": "may install/remove packages",
        },
        "apt-get": {
            "trigger": "apt-get",
            "dangerous_args": [
                "install",
                "remove",
                "purge",
                "autoremove",
                "autoclean",
                "upgrade",
                "dist-upgrade",
            ],
            "warning": "may install/remove packages",
        },
        "yum": {
            "trigger": "yum",
            "dangerous_args": [
                "install",
                "remove",
                "erase",
                "update",
                "upgrade",
                "downgrade",
                "autoremove",
            ],
            "warning": "may install/remove packages",
        },
        "dnf": {
            "trigger": "dnf",
            "dangerous_args": [
                "install",
                "remove",
                "erase",
                "upgrade",
                "downgrade",
                "autoremove",
            ],
            "warning": "may install/remove packages",
        },
        "pacman": {
            "trigger": "pacman",
            "dangerous_args": [
                "-s",  # sync (install)
                "--sync",
                "-r",  # remove
                "--remove",
                "-u",  # upgrade
                "--upgrade",
            ],
            "warning": "may install/remove packages",
        },
        "brew": {
            "trigger": "brew",
            "dangerous_args": [
                "install",
                "remove",
                "uninstall",
                "upgrade",
                "update",
            ],
            "warning": "may install/remove packages",
        },
        "pip": {
            "trigger": "pip",
            "dangerous_args": [
                "install",
                "uninstall",
                "upgrade",
            ],
            "warning": "may install/remove Python packages",
        },
        "npm": {
            "trigger": "npm",
            "dangerous_args": [
                "install",
                "remove",
                "uninstall",
                "update",
                "upgrade",
            ],
            "warning": "may install/remove Node packages",
        },
        "gem": {
            "trigger": "gem",
            "dangerous_args": [
                "install",
                "uninstall",
                "update",
                "upgrade",
            ],
            "warning": "may install/remove Ruby gems",
        },
        "cargo": {
            "trigger": "cargo",
            "dangerous_args": [
                "install",
                "uninstall",
                "update",
            ],
            "warning": "may install/remove Rust packages",
        },
        # File system modification
        "rm": {
            "trigger": "rm",
            "dangerous_args": [""],  # rm itself is dangerous, any usage is flagged
            "warning": "may delete files",
        },
        "mkfs": {
            "trigger": "mkfs",
            "dangerous_args": [""],  # mkfs itself is dangerous
            "warning": "may format file systems",
        },
        "dd": {
            "trigger": "dd",
            "dangerous_args": [""],  # dd itself is dangerous
            "warning": "may overwrite disk data",
        },
        "fdisk": {
            "trigger": "fdisk",
            "dangerous_args": [""],  # fdisk itself is dangerous
            "warning": "may modify disk partitions",
        },
        "parted": {
            "trigger": "parted",
            "dangerous_args": [""],  # parted itself is dangerous
            "warning": "may modify disk partitions",
        },
        # ZFS storage
        "zpool": {
            "trigger": "zpool",
            "dangerous_args": [
                "create",
                "destroy",
                "remove",
                "clear",
                "export",
                "import",
                "attach",
                "detach",
                "replace",
            ],
            "warning": "may modify ZFS pools",
        },
        "zfs": {
            "trigger": "zfs",
            "dangerous_args": [
                "create",
                "destroy",
                "set",
                "inherit",
                "rollback",
                "snapshot",
                "clone",
                "promote",
                "rename",
            ],
            "warning": "may modify ZFS datasets",
        },
        # User and permission management
        "useradd": {
            "trigger": "useradd",
            "dangerous_args": [""],  # useradd itself is dangerous
            "warning": "may create user accounts",
        },
        "userdel": {
            "trigger": "userdel",
            "dangerous_args": [""],  # userdel itself is dangerous
            "warning": "may delete user accounts",
        },
        "usermod": {
            "trigger": "usermod",
            "dangerous_args": [""],  # usermod itself is dangerous
            "warning": "may modify user accounts",
        },
        "passwd": {
            "trigger": "passwd",
            "dangerous_args": [""],  # passwd itself is dangerous
            "warning": "may change passwords",
        },
        "chmod": {
            "trigger": "chmod",
            "dangerous_args": [""],  # chmod itself is dangerous
            "warning": "may modify file permissions",
        },
        "chown": {
            "trigger": "chown",
            "dangerous_args": [""],  # chown itself is dangerous
            "warning": "may change file ownership",
        },
        # System shutdown/reboot
        "reboot": {
            "trigger": "reboot",
            "dangerous_args": [""],  # reboot itself is dangerous
            "warning": "may reboot the system",
        },
        "shutdown": {
            "trigger": "shutdown",
            "dangerous_args": [""],  # shutdown itself is dangerous
            "warning": "may shut down the system",
        },
        "halt": {
            "trigger": "halt",
            "dangerous_args": [""],  # halt itself is dangerous
            "warning": "may halt the system",
        },
        "poweroff": {
            "trigger": "poweroff",
            "dangerous_args": [""],  # poweroff itself is dangerous
            "warning": "may power off the system",
        },
        # Process management
        "kill": {
            "trigger": "kill",
            "dangerous_args": [""],  # kill itself is dangerous
            "warning": "may terminate processes",
        },
        "killall": {
            "trigger": "killall",
            "dangerous_args": [""],  # killall itself is dangerous
            "warning": "may terminate multiple processes",
        },
    }

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
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(f"❌ Unexpected error: {sanitized_error}")
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"Error: {sanitized_error}",
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

        # Warn about potentially dangerous command patterns
        self._check_dangerous_patterns(command, name)

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
                sanitized_error = DataSanitizer.sanitize_error_message(e)
                return (
                    {
                        "name": name,
                        "command": command,
                        "status": "down",
                        "exit_code": None,
                        "output": f"Invalid command syntax: {sanitized_error}",
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

            # Sanitize output if configured
            if self.config.cmdcheck_sanitize_output:
                output_truncated = DataSanitizer.sanitize_output(output_truncated)

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
            sanitized_error = DataSanitizer.sanitize_error_message(e)
            return (
                {
                    "name": name,
                    "command": command,
                    "status": "down",
                    "exit_code": None,
                    "output": sanitized_error,
                    "duration_seconds": duration,
                },
                f"{name}[{command}] ({sanitized_error})",
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

    def _check_dangerous_patterns(self, command: str, name: str) -> None:
        """Check for dangerous command patterns and log warnings.

        Warns about commands that appear to modify system state when running
        with elevated privileges. This helps prevent accidental or malicious
        system modifications via compromised monitoring scripts.

        Uses a dynamic pattern matching system that checks tool names and their
        dangerous arguments without requiring code changes for new tools.

        Args:
            command: Command string to check
            name: Command name for logging
        """
        command_lower = command.lower()

        # Check all registered dangerous patterns
        for tool_name, pattern_config in self.DANGEROUS_PATTERNS.items():
            trigger = pattern_config["trigger"]
            dangerous_args = pattern_config["dangerous_args"]
            warning_msg = pattern_config["warning"]

            # Build a pattern that matches the tool as a command (word boundary)
            # This prevents false positives like "service" matching in "myservice"
            if trigger == "zfs":
                # Special handling for zfs: check "zfs " or start with "zfs"
                trigger_found = "zfs " in command_lower or command_lower.startswith(
                    "zfs"
                )
            else:
                # For other tools, use regex word boundary to match as command
                # Match at start of command or after whitespace
                trigger_found = bool(
                    re.search(rf"(^|\s){re.escape(trigger)}(\s|$)", command_lower)
                )

            if not trigger_found:
                continue

            # Some tools are inherently dangerous (empty string in dangerous_args)
            # These don't require specific arguments to trigger a warning
            if "" in dangerous_args:
                log_security_event(
                    self.logger,
                    "dangerous_command_warning",
                    f"Command '{name}' contains dangerous tool '{tool_name}': {warning_msg}. "
                    f"Ensure this is authorized and runs with read-only intent.",
                )
                break  # Only warn once per tool

            # Check if any dangerous argument is used with this tool
            for dangerous_arg in dangerous_args:
                if dangerous_arg in command_lower:
                    log_security_event(
                        self.logger,
                        "dangerous_command_warning",
                        f"Command '{name}' contains dangerous pattern '{tool_name} {dangerous_arg}': {warning_msg}. "
                        f"Ensure this is authorized and runs with read-only intent.",
                    )
                    break  # Only warn once per tool

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
