"""Port scanning command for kuma sentinel."""

import os
import sys
import time
from typing import Optional

import click

from kuma_sentinel.cli.commands.base import Command
from kuma_sentinel.core.checkers.port_checker import PortChecker
from kuma_sentinel.core.config import DEFAULT_CONFIG_PATH, Config
from kuma_sentinel.core.logger import setup_logging
from kuma_sentinel.core.uptime_kuma import send_heartbeat, send_port_alert


class PortscanCommand(Command):
    """Port scanning command."""

    def register_command(self) -> click.Command:
        """Register the portscan command."""

        @click.command("portscan", help="Scan TCP ports on target ranges")
        @click.argument("ip_ranges", nargs=-1, required=False)
        @click.argument("uptime_kuma_url", required=False)
        @click.argument("heartbeat_token", required=False)
        @click.argument("portscan_token", required=False)
        @click.option(
            "--config",
            type=click.Path(exists=True),
            help="INI configuration file",
        )
        @click.option(
            "--ports",
            help="Nmap port range (e.g., 1-1000, 22,80,443)",
        )
        @click.option(
            "--timing",
            type=click.Choice(["T0", "T1", "T2", "T3", "T4", "T5"]),
            help="Nmap timing level",
        )
        @click.option(
            "--exclude",
            help="Comma-separated IPs/ranges to exclude",
        )
        @click.option(
            "--log-file",
            type=click.Path(),
            help="Log file path",
        )
        @click.pass_context
        def portscan(
            ctx: click.Context,
            ip_ranges,
            uptime_kuma_url: Optional[str],
            heartbeat_token: Optional[str],
            portscan_token: Optional[str],
            config: Optional[str],
            ports: Optional[str],
            timing: Optional[str],
            exclude: Optional[str],
            log_file: Optional[str],
        ):
            """Scan TCP ports on target ranges and report to Uptime Kuma."""
            # Initialize configuration
            cfg = Config()

            # Load from config file if provided or if default exists
            config_file = config or DEFAULT_CONFIG_PATH
            if os.path.exists(config_file):
                try:
                    click.secho(
                        f"📂 Loading INI config file: {config_file}",
                        fg="cyan",
                    )
                    cfg.load_from_ini(config_file)
                    click.secho(
                        "✅ Config file loaded successfully",
                        fg="green",
                    )
                except Exception as e:
                    click.secho(
                        f"Error loading config file: {e}",
                        fg="red",
                        err=True,
                    )
                    sys.exit(1)

            # Create args-like object for load_from_args
            class Args:
                ip_ranges: list
                uptime_kuma_url: Optional[str]
                heartbeat_token: Optional[str]
                portscan_token: Optional[str]
                ports: Optional[str]
                timing: Optional[str]
                exclude: Optional[str]
                log_file: Optional[str]

            args = Args()
            args.ip_ranges = list(ip_ranges) if ip_ranges else []
            args.uptime_kuma_url = uptime_kuma_url
            args.heartbeat_token = heartbeat_token
            args.portscan_token = portscan_token
            args.ports = ports
            args.timing = timing
            args.exclude = exclude
            args.log_file = log_file

            cfg.load_from_args(args)
            cfg.load_from_env()

            # Validate configuration
            try:
                cfg.validate()
            except ValueError as e:
                click.secho(f"Configuration error: {e}", fg="red", err=True)
                click.secho(
                    "\nUse 'kuma-sentinel portscan --help' for usage information",
                    fg="yellow",
                    err=True,
                )
                sys.exit(1)

            # Setup logging
            logger = setup_logging(cfg.log_file)

            # Log configuration summary
            logger.info("=" * 70)
            logger.info("🔍 KUMA SENTINEL - PORT SCAN CONFIGURATION")
            logger.info("=" * 70)
            config_summary = cfg.get_summary(mask_tokens=True)
            logger.info("📝 Nmap Configuration:")
            logger.info(f"   Ports: {config_summary['portscan_nmap_ports']}")
            logger.info(f"   Timing: {config_summary['portscan_nmap_timing']}")
            logger.info(f"   Arguments: {config_summary['portscan_nmap_arguments']}")
            logger.info(f"   Exclude IPs: {config_summary['portscan_exclude_ips']}")
            logger.info("📍 Targets:")
            logger.info(f"   IP Ranges: {config_summary['portscan_ip_ranges']}")
            logger.info("🔔 Uptime Kuma Integration:")
            logger.info(f"   URL: {config_summary['uptime_kuma_url']}")
            logger.info(f"   Heartbeat Enabled: {config_summary['heartbeat_enabled']}")
            logger.info(
                f"   Heartbeat Interval: {config_summary['heartbeat_interval']}"
            )
            logger.info(
                f"   Heartbeat Token: {config_summary['heartbeat_token']} (masked)"
            )
            logger.info(
                f"   Port-Scan Token: {config_summary['portscan_token']} (masked)"
            )
            logger.info("📂 Logging:")
            logger.info(f"   Log File: {config_summary['log_file']}")
            logger.info(
                f"   Keep XML Output: {config_summary['portscan_nmap_keep_xmloutput']}"
            )
            logger.info("=" * 70)

            # Type assertions (validate() ensures these are not None)
            assert cfg.uptime_kuma_url is not None
            assert cfg.heartbeat_token is not None
            assert cfg.portscan_token is not None

            # Start scan
            scan_start = time.time()

            logger.info("🔍 Starting port scan")

            # Send initial heartbeat
            send_heartbeat(
                logger,
                cfg.uptime_kuma_url,
                cfg.heartbeat_token,
                f"Port scan starting for ranges: {', '.join(cfg.portscan_ip_ranges)}",
            )

            try:
                # Create and execute port checker
                checker_config = {
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
                checker = PortChecker(logger, checker_config)
                result = checker.execute()

                # Calculate scan duration
                scan_end = time.time()
                scan_duration = int(scan_end - scan_start)
                scan_minutes = scan_duration // 60

                # Send final heartbeat
                send_heartbeat(
                    logger,
                    cfg.uptime_kuma_url,
                    cfg.heartbeat_token,
                    f"Scan complete after {scan_minutes} minutes",
                )

                # Send port alert based on result
                send_port_alert(
                    logger,
                    cfg.uptime_kuma_url,
                    cfg.portscan_token,
                    result.status,
                    f"{result.message} ({scan_minutes}m)",
                )

                logger.info(f"✅ Port scan complete ({scan_minutes}m)")
                sys.exit(0)

            except Exception as e:
                logger.error(f"❌ Unexpected error: {str(e)}")
                send_port_alert(
                    logger,
                    cfg.uptime_kuma_url,
                    cfg.portscan_token,
                    "down",
                    f"Port scan error: {str(e)}",
                )
                sys.exit(1)

        return portscan
