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
    help_text="Check Kopia snapshot freshness",
)
class KopiaSnapshotStatusCommand(CommandExecutor):
    """Kopia snapshot status monitoring command using unified executor."""

    def get_builtin_command(self, base_command: click.Command) -> click.Command:
        """Build kopiasnapshotstatus command with arguments and options."""
        # Add arguments
        base_command = click.argument("snapshot_paths", nargs=-1, required=False)(
            base_command
        )
        base_command = click.argument("uptime_kuma_url", required=False)(base_command)
        base_command = click.argument("kopiasnapshotstatus_token", required=False)(
            base_command
        )

        # Add options
        base_command = click.option(
            "--config",
            type=click.Path(exists=True),
            help="INI configuration file",
        )(base_command)

        base_command = click.option(
            "--max-age-hours",
            type=int,
            help="Maximum age in hours for snapshots",
        )(base_command)

        base_command = click.option(
            "--log-file",
            type=click.Path(),
            help="Log file path",
        )(base_command)

        return base_command

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "📋 Kopia Snapshot Configuration": {
                "Snapshot Paths": "kopiasnapshotstatus_snapshot_paths",
                "Max Age Hours": "kopiasnapshotstatus_max_age_hours",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
