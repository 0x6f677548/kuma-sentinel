"""Command check monitoring command."""

from typing import Dict

import click

from kuma_sentinel.cli.commands import register_command
from kuma_sentinel.cli.commands.executor import CommandExecutor
from kuma_sentinel.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig


@register_command(
    "cmdcheck",
    checker_class=CmdCheckChecker,
    config_class=CmdCheckConfig,
    help_text="Execute arbitrary shell commands and report results to Uptime Kuma",
)
class CmdCheckCommand(CommandExecutor):
    """Command check monitoring using unified executor."""

    def get_builtin_command(self, base_command: click.Command) -> click.Command:
        """Build cmdcheck command with arguments and options.

        Note: CLI supports single command only. For multiple commands,
        use YAML configuration with cmdcheck.commands list.
        """
        # Add common arguments (uptime_kuma_url, heartbeat_token, token)
        base_command = self._add_common_arguments(base_command)

        # Add common options (--config, --log-file)
        base_command = self._add_common_options(base_command)

        # Single command option (CLI only supports single command)
        base_command = click.option(
            "--command",
            "command",
            multiple=False,
            help="Shell command to execute (single command only; use --config for multiple)",
        )(base_command)

        # Timeout option
        base_command = click.option(
            "--timeout",
            type=int,
            help="Command timeout in seconds (1-300)",
        )(base_command)

        # Exit code expectation
        base_command = click.option(
            "--expect-exit-code",
            type=int,
            help="Expected exit code for success (0-255)",
        )(base_command)

        # Success pattern
        base_command = click.option(
            "--success-pattern",
            help="Regex pattern indicating success",
        )(base_command)

        # Failure pattern
        base_command = click.option(
            "--failure-pattern",
            help="Regex pattern indicating failure (takes precedence)",
        )(base_command)

        # Capture output option
        base_command = click.option(
            "--capture-output/--no-capture-output",
            default=None,
            help="Capture command output (default: true)",
        )(base_command)

        return base_command

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "🔧 Command Configuration": {
                "Total Commands": str(len(self.config.cmdcheck_commands)),
                "Timeout": "cmdcheck_timeout",
                "Expected Exit Code": "cmdcheck_expect_exit_code",
                "Capture Output": "cmdcheck_capture_output",
                "Success Pattern": "cmdcheck_success_pattern",
                "Failure Pattern": "cmdcheck_failure_pattern",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
