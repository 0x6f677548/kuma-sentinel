"""Kopia snapshot status monitoring command."""

from typing import Callable, Dict, List, Optional, Tuple

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.cli.utils import parse_tuples_from_list
from kuma_scout.core.checkers.kopia_snapshot_checker import KopiaSnapshotChecker
from kuma_scout.core.config.kopia_snapshot_config import KopiaSnapshotConfig


@register_command(
    "kopiasnapshotstatus",
    checker_class=KopiaSnapshotChecker,
    config_class=KopiaSnapshotConfig,
    help_text="Checks Kopia snapshot freshness",
)
class KopiaSnapshotStatusCommand(CommandExecutor):
    """Kopia snapshot status monitoring command using unified executor."""

    def get_builtin_command(self) -> Callable:
        """Build and return kopiasnapshotstatus command function with Typer parameters."""

        def kopiasnapshotstatus_cmd(
            config: Optional[str] = typer.Option(
                None,
                "--config",
                help="Configuration file path (e.g., /etc/kuma-scout/config.yaml)",
            ),
            log_file: Optional[str] = typer.Option(
                None, "--log-file", help="Log file path (e.g., /var/log/kuma-scout.log)"
            ),
            uptime_kuma_url: Optional[str] = typer.Option(
                None,
                "--uptime-kuma-url",
                help="Uptime Kuma API URL (e.g., http://uptimekuma:3001/api/push)",
            ),
            heartbeat_token: Optional[str] = typer.Option(
                None,
                "--heartbeat-token",
                help="Heartbeat token (env: KUMA_SCOUT_HEARTBEAT_TOKEN). Example: abc123xyz789",
            ),
            token: Optional[str] = typer.Option(
                None,
                "--token",
                help="Kopia snapshot status token (env: KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN). Example: def456uvw012",
            ),
            ignore_file_permissions: bool = typer.Option(
                False,
                "--ignore-file-permissions",
                help="Skip config file permission validation (use only in development)",
            ),
            snapshot: Optional[List[str]] = typer.Option(
                None,
                "--snapshot",
                help="Snapshot path and max age hours (format: --snapshot path[,hours]). Examples: /data or /data,24 or root@host:/path,48",
            ),
            max_age_hours: Optional[int] = typer.Option(
                None,
                "--max-age-hours",
                help="Global default maximum age in hours for snapshots (default: 24, range: 1-999, e.g., 24)",
            ),
        ):
            """Checks Kopia snapshot freshness.

Examples:

  Monitor with configuration file (recommended):
  $ kuma-scout kopiasnapshotstatus --config /etc/kuma-scout/config.yaml

  Override snapshots via CLI with hours (format: path,hours):
  $ kuma-scout kopiasnapshotstatus \\
      --snapshot /data,24 \\
      --snapshot /backups,48 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-kopia-token

  Override snapshots without hours (uses default 24 hours):
  $ kuma-scout kopiasnapshotstatus \\
      --snapshot /data \\
      --snapshot /backups \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-kopia-token

  Monitor SSH-based snapshot location:
  $ kuma-scout kopiasnapshotstatus \\
      --snapshot "root@fileserver:/mnt/shares,24" \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-kopia-token

  Using environment variable for token:
  $ KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN=your-token \\
    kuma-scout kopiasnapshotstatus --config /etc/kuma-scout/config.yaml

Note: Snapshot format is: --snapshot <path>[,<hours>]
Can be repeated multiple times for different snapshots.
If hours is omitted, uses --max-age-hours value or default 24 hours.
            """
            # Parse snapshot arguments: "path,hours" or just "path" (uses global max_age_hours)
            snapshots_tuples: List[Tuple[str, Optional[int]]] = []
            if snapshot:
                try:
                    snapshots_tuples = parse_tuples_from_list(snapshot, required=False)
                except ValueError as e:
                    typer.echo(f"Error parsing snapshot arguments: {e}", err=True)
                    raise typer.Exit(1) from None

            # Merge snapshots with max_age_hours: if snapshot has no hours, use global default
            snapshots_with_defaults: List[Tuple[str, int]] = []
            for path, hours in snapshots_tuples:
                effective_hours = hours if hours is not None else (max_age_hours or 24)
                snapshots_with_defaults.append((path, effective_hours))

            args = {
                "uptime_kuma_url": uptime_kuma_url,
                "heartbeat_token": heartbeat_token,
                "token": token,
                "config": config,
                "log_file": log_file,
                "ignore_file_permissions": ignore_file_permissions,
                "snapshots": snapshots_with_defaults,
                "max_age_hours": max_age_hours,
            }
            self.execute_with_orchestration(args)

        return kopiasnapshotstatus_cmd

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
