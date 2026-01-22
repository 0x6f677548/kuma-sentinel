"""Port scanning command for kuma sentinel."""

from typing import Dict

import click

from kuma_sentinel.cli.commands import register_command
from kuma_sentinel.cli.commands.executor import CommandExecutor
from kuma_sentinel.core.checkers.port_checker import PortChecker
from kuma_sentinel.core.config.portscan_config import PortscanConfig


@register_command(
    "portscan",
    checker_class=PortChecker,
    config_class=PortscanConfig,
    help_text="Scans for TCP open ports on target ranges",
)
class PortscanCommand(CommandExecutor):
    """Port scanning command using unified executor."""

    def get_builtin_command(self, base_command: click.Command) -> click.Command:
        """Build portscan command with arguments and options."""
        # Add common arguments (uptime_kuma_url, heartbeat_token, token)
        base_command = self._add_common_arguments(base_command)

        # Add common options (--config, --log-file)
        base_command = self._add_common_options(base_command)

        base_command = click.option(
            "--ip-range",
            "ip_ranges",
            multiple=True,
            help="IP ranges to scan (can be repeated)",
        )(base_command)

        base_command = click.option(
            "--exclude",
            "exclude",
            multiple=True,
            help="IP/range to exclude (can be repeated)",
        )(base_command)

        base_command = click.option(
            "--ports",
            help="Nmap port range (e.g., 1-1000, 22,80,443)",
        )(base_command)

        base_command = click.option(
            "--timing",
            type=click.Choice(["T0", "T1", "T2", "T3", "T4", "T5"]),
            help="Nmap timing level",
        )(base_command)

        return base_command

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
