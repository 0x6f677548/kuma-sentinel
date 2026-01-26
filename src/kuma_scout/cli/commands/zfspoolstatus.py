"""ZFS pool status monitoring command."""

from typing import Dict

import click

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.zfs_pool_checker import ZfsPoolStatusChecker
from kuma_scout.core.config.zfs_pool_config import ZfsPoolStatusConfig


@register_command(
    "zfspoolstatus",
    checker_class=ZfsPoolStatusChecker,
    config_class=ZfsPoolStatusConfig,
    help_text="Checks ZFS pool health and free space percentage",
)
class ZfsPoolStatusCommand(CommandExecutor):
    """ZFS pool status monitoring command using unified executor."""

    def get_builtin_command(self, base_command: click.Command) -> click.Command:
        """Build zfspoolstatus command with arguments and options."""
        # Add common arguments (uptime_kuma_url, heartbeat_token, token)
        base_command = self._add_common_arguments(base_command)

        # Add common options (--config, --log-file)
        base_command = self._add_common_options(base_command)

        base_command = click.option(
            "--pool",
            "pools",
            nargs=2,
            multiple=True,
            type=(str, int),
            help="Pool name and minimum free space percent (can be repeated)",
        )(base_command)

        base_command = click.option(
            "--free-space-percent",
            type=int,
            help="Default minimum free space percent threshold",
        )(base_command)

        return base_command

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "📋 ZFS Pool Configuration": {
                "Pools": "zfspoolstatus_pools",
                "Default Min Free Space": "zfspoolstatus_free_space_percent_default",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
