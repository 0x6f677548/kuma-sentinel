"""Kopia snapshot status monitoring command."""

from typing import Dict

import click

from kuma_sentinel.cli.commands import register_command
from kuma_sentinel.cli.commands.executor import CommandExecutor
from kuma_sentinel.core.checkers.kopia_snapshot_checker import KopiaSnapshotChecker
from kuma_sentinel.core.config.kopia_snapshot_config import KopiaSnapshotConfig


@register_command(
    "kopiasnapshotstatus",
    checker_class=KopiaSnapshotChecker,
    config_class=KopiaSnapshotConfig,
    help_text="Checks Kopia snapshot freshness",
)
class KopiaSnapshotStatusCommand(CommandExecutor):
    """Kopia snapshot status monitoring command using unified executor."""

    def get_builtin_command(self, base_command: click.Command) -> click.Command:
        """Build kopiasnapshotstatus command with arguments and options."""
        # Add common arguments (uptime_kuma_url, heartbeat_token, token)
        base_command = self._add_common_arguments(base_command)

        # Add common options (--config, --log-file)
        base_command = self._add_common_options(base_command)

        base_command = click.option(
            "--snapshot",
            "snapshots",
            nargs=2,
            multiple=True,
            type=(str, int),
            help="Snapshot path and max age in hours (can be repeated)",
        )(base_command)

        base_command = click.option(
            "--max-age-hours",
            type=int,
            help="Global default maximum age in hours for snapshots",
        )(base_command)

        return base_command

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "📋 Kopia Snapshot Configuration": {
                "Snapshots": "kopiasnapshotstatus_snapshots",
                "Default Max Age Hours": "kopiasnapshotstatus_max_age_hours_default",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
