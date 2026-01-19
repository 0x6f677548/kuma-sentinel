"""Port scanning command for kuma sentinel."""

from typing import Any, Dict, Optional

import click

from kuma_sentinel.cli.commands.executor import CommandExecutor, CommandMetadata
from kuma_sentinel.core.checkers.port_checker import PortChecker
from kuma_sentinel.core.config import Config


class PortscanCommand(CommandExecutor):
    """Port scanning command using unified executor."""

    def get_metadata(self) -> CommandMetadata:
        """Return metadata for portscan command."""
        return CommandMetadata(
            name="portscan",
            checker_class=PortChecker,
            help_text="Scan TCP ports on target ranges",
        )

    def get_builtin_command(
        self, base_command: click.Command, metadata: CommandMetadata
    ) -> click.Command:
        """Build portscan command with arguments and options."""
        # Add arguments
        base_command = click.argument("ip_ranges", nargs=-1, required=False)(
            base_command
        )
        base_command = click.argument("uptime_kuma_url", required=False)(
            base_command
        )
        base_command = click.argument("heartbeat_token", required=False)(
            base_command
        )
        base_command = click.argument("portscan_token", required=False)(
            base_command
        )

        # Add options
        base_command = click.option(
            "--config",
            type=click.Path(exists=True),
            help="INI configuration file",
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

        base_command = click.option(
            "--exclude",
            help="Comma-separated IPs/ranges to exclude",
        )(base_command)

        base_command = click.option(
            "--log-file",
            type=click.Path(),
            help="Log file path",
        )(base_command)

        return base_command

    def load_from_args(self, cfg: Config, args: Dict[str, Any]) -> None:
        """Load portscan-specific args into config."""
        # Create args-like object for Click arguments
        class Args:
            ip_ranges: list
            uptime_kuma_url: Optional[str]
            heartbeat_token: Optional[str]
            portscan_token: Optional[str]
            ports: Optional[str]
            timing: Optional[str]
            exclude: Optional[str]
            log_file: Optional[str]

        args_obj = Args()
        args_obj.ip_ranges = list(args.get("ip_ranges", [])) if args.get("ip_ranges") else []
        args_obj.uptime_kuma_url = args.get("uptime_kuma_url")
        args_obj.heartbeat_token = args.get("heartbeat_token")
        args_obj.portscan_token = args.get("portscan_token")
        args_obj.ports = args.get("ports")
        args_obj.timing = args.get("timing")
        args_obj.exclude = args.get("exclude")
        args_obj.log_file = args.get("log_file")

        cfg.load_from_args(args_obj)

    def build_checker_config(self, cfg: Config) -> Dict[str, Any]:
        """Build checker configuration for PortChecker."""
        return {
            "portscan_nmap_ports": cfg.portscan_nmap_ports,
            "portscan_nmap_timing": cfg.portscan_nmap_timing,
            "portscan_exclude_ips": cfg.portscan_exclude_ips,
            "portscan_ip_ranges": cfg.portscan_ip_ranges,
            "portscan_nmap_arguments": cfg.portscan_nmap_arguments,
            "heartbeat_enabled": cfg.heartbeat_enabled,
            "heartbeat_interval": cfg.heartbeat_interval,
            "uptime_kuma_url": cfg.uptime_kuma_url,
            "heartbeat_token": cfg.heartbeat_token,
            "portscan_nmap_keep_xmloutput": cfg.portscan_nmap_keep_xmloutput,
        }

    def get_summary_fields(self, cfg: Config) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "📝 Nmap Configuration": {
                "Ports": "portscan_nmap_ports",
                "Timing": "portscan_nmap_timing",
                "Arguments": "portscan_nmap_arguments",
                "Exclude IPs": "portscan_exclude_ips",
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

