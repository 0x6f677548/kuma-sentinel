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

        common_options = self.get_common_options()

        def portscan_cmd(
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
            log_file: Optional[str] = common_options["log_file"],
            log_level: Optional[str] = common_options["log_level"],
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
                "log_level": log_level,
                "ignore_file_permissions": ignore_file_permissions,
                # SSH options
                "ssh": ssh,
                "ssh_key_file": ssh_key_file,
                "ssh_password": ssh_password,
                "ssh_strict_host_key_checking": ssh_strict_host_key_checking,
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
            "🎯 Execution Target": {
                "Target": "execution_target",
            },
            "📝 Nmap Configuration": {
                "Ports": "portscan_nmap_ports",
                "Timing": "portscan_nmap_timing",
                "Timeout": "portscan_nmap_timeout",
                "Arguments": "portscan_nmap_arguments",
                "Exclude IPs": "portscan_exclude",
            },
            "📍 Targets": {
                "IP Ranges": "portscan_ip_ranges",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
            "📂 Logging": {
                "Log File": "log_file",
                "Log Level": "log_level",
                "Keep XML Output": "portscan_nmap_keep_xmloutput",
            },
        }
