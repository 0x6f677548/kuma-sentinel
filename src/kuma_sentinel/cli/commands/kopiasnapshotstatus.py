"""Kopia snapshot status monitoring command."""

from typing import Any, Dict, Optional

import click

from kuma_sentinel.cli.commands.executor import CommandExecutor, CommandMetadata
from kuma_sentinel.core.checkers.kopia_snapshot_checker import (
    KopiaSnapshotChecker,
)
from kuma_sentinel.core.config import Config


class KopiaSnapshotStatusCommand(CommandExecutor):
    """Kopia snapshot status monitoring command using unified executor."""

    def get_metadata(self) -> CommandMetadata:
        """Return metadata for kopiasnapshotstatus command."""
        return CommandMetadata(
            name="kopiasnapshotstatus",
            checker_class=KopiaSnapshotChecker,
            help_text="Check Kopia snapshot freshness",
        )

    def get_builtin_command(
        self, base_command: click.Command, metadata: CommandMetadata
    ) -> click.Command:
        """Build kopiasnapshotstatus command with arguments and options."""
        # Add arguments
        base_command = click.argument("snapshot_paths", nargs=-1, required=False)(
            base_command
        )
        base_command = click.argument("uptime_kuma_url", required=False)(
            base_command
        )
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

    def load_from_args(self, cfg: Config, args: Dict[str, Any]) -> None:
        """Load kopiasnapshotstatus-specific args into config."""
        # Create args-like object for Click arguments
        class Args:
            snapshot_paths: list
            uptime_kuma_url: Optional[str]
            kopiasnapshotstatus_token: Optional[str]
            max_age_hours: Optional[int]
            log_file: Optional[str]

        args_obj = Args()
        args_obj.snapshot_paths = list(args.get("snapshot_paths", [])) if args.get("snapshot_paths") else []
        args_obj.uptime_kuma_url = args.get("uptime_kuma_url")
        args_obj.kopiasnapshotstatus_token = args.get("kopiasnapshotstatus_token")
        args_obj.max_age_hours = args.get("max_age_hours")
        args_obj.log_file = args.get("log_file")

        # For kopia command, directly set config attributes from args
        if args_obj.snapshot_paths:
            cfg.kopiasnapshotstatus_snapshot_paths = args_obj.snapshot_paths
        if args_obj.uptime_kuma_url:
            cfg.uptime_kuma_url = args_obj.uptime_kuma_url
        if args_obj.kopiasnapshotstatus_token:
            cfg.kopiasnapshotstatus_token = args_obj.kopiasnapshotstatus_token
        if args_obj.max_age_hours is not None:
            cfg.kopiasnapshotstatus_max_age_hours = args_obj.max_age_hours
        if args_obj.log_file:
            cfg.log_file = args_obj.log_file

    def build_checker_config(self, cfg: Config) -> Dict[str, Any]:
        """Build checker configuration for KopiaSnapshotChecker."""
        return {
            "kopiasnapshotstatus_snapshot_paths": cfg.kopiasnapshotstatus_snapshot_paths,
            "kopiasnapshotstatus_max_age_hours": cfg.kopiasnapshotstatus_max_age_hours,
            "kopiasnapshotstatus_token": cfg.kopiasnapshotstatus_token,
            "heartbeat_enabled": cfg.heartbeat_enabled,
            "heartbeat_interval": cfg.heartbeat_interval,
            "uptime_kuma_url": cfg.uptime_kuma_url,
            "heartbeat_token": cfg.heartbeat_token,
        }

    def get_summary_fields(self, cfg: Config) -> Dict[str, Dict[str, str]]:
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

