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

        common_options = self.get_common_options()

        def kopiasnapshotstatus_cmd(
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
            config: Optional[str] = common_options["config"],
            uptime_kuma_url: Optional[str] = common_options["uptime_kuma_url"],
            heartbeat_token: Optional[str] = common_options["heartbeat_token"],
            token: Optional[str] = common_options["token"],
            ignore_file_permissions: bool = common_options["ignore_file_permissions"],
            ssh: Optional[str] = common_options["ssh"],
            ssh_key_file: Optional[str] = common_options["ssh_key_file"],
            ssh_password: Optional[str] = common_options["ssh_password"],
            ssh_strict_host_key_checking: bool = common_options[
                "ssh_strict_host_key_checking"
            ],
            retry_count: Optional[int] = common_options["retry_count"],
            retry_delay: Optional[int] = common_options["retry_delay"],
            log_file: Optional[str] = common_options["log_file"],
            log_level: Optional[str] = common_options["log_level"],
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

  Monitor other user and server snapshot location:
  $ kuma-scout kopiasnapshotstatus \\
      --snapshot "root@fileserver:/mnt/shares,24" \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-kopia-token

  Monitor snapshots, executing the command on a remote server via SSH:
  $ kuma-scout kopiasnapshotstatus \\
      --ssh user@remote-server:22 \\
      --ssh-key-file /path/to/ssh_key \\
      --snapshot /data,24 \\
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
                "log_level": log_level,
                "ignore_file_permissions": ignore_file_permissions,
                # SSH options
                "ssh": ssh,
                "ssh_key_file": ssh_key_file,
                "ssh_password": ssh_password,
                "ssh_strict_host_key_checking": ssh_strict_host_key_checking,
                "retry_count": retry_count,
                "retry_delay": retry_delay,
                "snapshots": snapshots_with_defaults,
                "max_age_hours": max_age_hours,
            }
            self.execute_with_orchestration(args)

        return kopiasnapshotstatus_cmd

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "🎯 Execution Target": {
                "Target": "execution_target",
            },
            "📋 Kopia Snapshot Configuration": {
                "Snapshots": "kopiasnapshotstatus_snapshots",
                "Default Max Age Hours": "kopiasnapshotstatus_max_age_hours_default",
            },
            "� Logging Configuration": {
                "Log File": "log_file",
                "Log Level": "log_level",
            },
            "�🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
