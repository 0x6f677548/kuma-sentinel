"""ZFS pool status monitoring command."""

from typing import Callable, Dict, List, Optional, Tuple

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.cli.utils import parse_tuples_from_list
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

    def get_builtin_command(self) -> Callable:
        """Build and return zfspoolstatus command function with Typer parameters."""

        common_options = self.get_common_options()

        def zfspoolstatus_cmd(
            pool: Optional[List[str]] = typer.Option(
                None,
                "--pool",
                help="Pool name and minimum free space percent (format: --pool name[,percent]). Examples: tank or tank,10 or backup,20",
            ),
            min_free_percent: Optional[int] = typer.Option(
                None,
                "--min-free-percent",
                help="Global minimum free space percentage (default: 10, range: 1-99, e.g., 10)",
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
            """Checks ZFS pool health and free space percentage.

Examples:

  Monitor with configuration file (recommended):
  $ kuma-scout zfspoolstatus --config /etc/kuma-scout/config.yaml

  Monitor single pool with percent (alert if free space below 10%):
  $ kuma-scout zfspoolstatus \\
      --pool tank,10 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-zfs-token

  Monitor single pool without percent (uses default 10%):
  $ kuma-scout zfspoolstatus \\
      --pool tank \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-zfs-token

  Monitor multiple pools with different thresholds (mixed format):
  $ kuma-scout zfspoolstatus \\
      --pool tank,10 \\
      --pool backup \\
      --pool archive,30 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-zfs-token

Note: Pool format is: --pool <name>[,<min-free-space-percent>]
Can be repeated multiple times for different pools.
If percent is omitted, uses --min-free-percent value or default 10%.
            """
            # Parse pool arguments: "name,percent" or just "name" (uses global min_free_percent)
            pools_tuples: List[Tuple[str, Optional[int]]] = []
            if pool:
                try:
                    pools_tuples = parse_tuples_from_list(pool, required=False)
                except ValueError as e:
                    typer.echo(f"Error parsing pool arguments: {e}", err=True)
                    raise typer.Exit(1) from None

            # Merge pools with min_free_percent: if pool has no percent, use global default
            pools_with_defaults: List[Tuple[str, int]] = []
            for name, percent in pools_tuples:
                effective_percent = (
                    percent if percent is not None else (min_free_percent or 10)
                )
                pools_with_defaults.append((name, effective_percent))

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
                "pools": pools_with_defaults,
                "min_free_percent": min_free_percent,
            }
            self.execute_with_orchestration(args)

        return zfspoolstatus_cmd

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "🎯 Execution Target": {
                "Target": "execution_target",
            },
            "📋 ZFS Pool Configuration": {
                "Pools": "zfspoolstatus_pools",
                "Default Min Free Space": "zfspoolstatus_free_space_percent_default",
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
