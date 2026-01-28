"""Port scanning command for kuma scout."""

from typing import Callable, Dict, List, Optional

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.port_checker import PortChecker
from kuma_scout.core.config.portscan_config import PortscanConfig


@register_command(
    "portscan",
    checker_class=PortChecker,
    config_class=PortscanConfig,
    help_text="Scans for TCP open ports on target ranges",
)
class PortscanCommand(CommandExecutor):
    """Port scanning command using unified executor."""

    def get_builtin_command(self) -> Callable:
        """Build and return portscan command function with Typer parameters."""

        def portscan_cmd(
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
                help="Port scan token (env: KUMA_SCOUT_PORTSCAN_TOKEN). Example: def456uvw012",
            ),
            ignore_file_permissions: bool = typer.Option(
                False,
                "--ignore-file-permissions",
                help="Skip config file permission validation (use only in development)",
            ),
            ip_ranges: Optional[List[str]] = typer.Option(
                None,
                "--ip-range",
                help="IP ranges to scan (e.g., 192.168.1.0/24, repeatable)",
            ),
            exclude: Optional[List[str]] = typer.Option(
                None,
                "--exclude",
                help="IP addresses to exclude (e.g., 192.168.1.1, repeatable)",
            ),
            ports: Optional[str] = typer.Option(
                None,
                "--ports",
                help="Port ranges or list (e.g., 1-1000 or 22,80,443,3389)",
            ),
            timing: Optional[str] = typer.Option(
                None,
                "--timing",
                help="Nmap timing profile (T0-T5, e.g., T3 for default or T4 for aggressive)",
            ),
        ):
            """Scans for TCP open ports on target ranges.

Examples:

  Scan with configuration file (recommended):
  $ kuma-scout portscan --config /etc/kuma-scout/config.yaml

  Scan single IP range with CLI options:
  $ kuma-scout portscan \\
      --ip-range 192.168.1.0/24 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-portscan-token

  Scan multiple IP ranges:
  $ kuma-scout portscan \\
      --ip-range 192.168.1.0/24 \\
      --ip-range 10.0.0.0/8 \\
      --ip-range 172.16.0.0/12 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-portscan-token

  Scan with exclusions and custom ports:
  $ kuma-scout portscan \\
      --ip-range 192.168.1.0/24 \\
      --exclude 192.168.1.1 \\
      --exclude 192.168.1.254 \\
      --ports 22,80,443 \\
      --timing T4 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-portscan-token

Nmap Timing Profiles (--timing):
  T0=Paranoid, T1=Sneaky, T2=Polite, T3=Normal (default),
  T4=Aggressive, T5=Insane
            """
            args = {
                "uptime_kuma_url": uptime_kuma_url,
                "heartbeat_token": heartbeat_token,
                "token": token,
                "config": config,
                "log_file": log_file,
                "ignore_file_permissions": ignore_file_permissions,
                "ip_ranges": ip_ranges,
                "exclude": exclude,
                "ports": ports,
                "timing": timing,
            }
            self.execute_with_orchestration(args)

        return portscan_cmd

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "📝 Nmap Configuration": {
                "Ports": "portscan_nmap_ports",
                "Timing": "portscan_nmap_timing",
                "Arguments": "portscan_nmap_arguments",
                "Exclude IPs": "portscan_exclude",
            },
            "📍 Targets": {
                "IP Ranges": "portscan_ip_ranges",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
                "Heartbeat Interval": "heartbeat_interval",
                "Heartbeat Token": "heartbeat_token",
                "Port-Scan Token": "portscan_token",
            },
            "📂 Logging": {
                "Log File": "log_file",
                "Keep XML Output": "portscan_nmap_keep_xmloutput",
            },
        }
