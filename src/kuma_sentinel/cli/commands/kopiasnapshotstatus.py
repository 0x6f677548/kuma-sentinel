"""Kopia snapshot status monitoring command."""

import os
import sys
import time
from typing import Optional

import click

from kuma_sentinel.cli.commands.base import Command
from kuma_sentinel.core.checkers.kopia_snapshot_checker import (
    KopiaSnapshotChecker,
)
from kuma_sentinel.core.config import DEFAULT_CONFIG_PATH, Config
from kuma_sentinel.core.logger import setup_logging
from kuma_sentinel.core.uptime_kuma import PUSH_TIMEOUT_ALERT, send_push


class KopiaSnapshotStatusCommand(Command):
    """Kopia snapshot status monitoring command."""

    def register_command(self) -> click.Command:
        """Register the kopiasnapshotstatus command."""

        @click.command("kopiasnapshotstatus", help="Check Kopia snapshot freshness")
        @click.argument("snapshot_paths", nargs=-1, required=False)
        @click.argument("uptime_kuma_url", required=False)
        @click.argument("kopiasnapshotstatus_token", required=False)
        @click.option(
            "--config",
            type=click.Path(exists=True),
            help="INI configuration file",
        )
        @click.option(
            "--max-age-hours",
            type=int,
            help="Maximum age in hours for snapshots",
        )
        @click.option(
            "--log-file",
            type=click.Path(),
            help="Log file path",
        )
        @click.pass_context
        def kopiasnapshotstatus(
            ctx: click.Context,
            snapshot_paths,
            uptime_kuma_url: Optional[str],
            kopiasnapshotstatus_token: Optional[str],
            config: Optional[str],
            max_age_hours: Optional[int],
            log_file: Optional[str],
        ):
            """Check Kopia snapshot freshness and report to Uptime Kuma."""
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
                snapshot_paths: list
                uptime_kuma_url: Optional[str]
                kopiasnapshotstatus_token: Optional[str]
                max_age_hours: Optional[int]
                log_file: Optional[str]

            args = Args()
            args.snapshot_paths = list(snapshot_paths) if snapshot_paths else []
            args.uptime_kuma_url = uptime_kuma_url
            args.kopiasnapshotstatus_token = kopiasnapshotstatus_token
            args.max_age_hours = max_age_hours
            args.log_file = log_file

            # For kopia command, directly set config attributes
            if args.snapshot_paths:
                cfg.kopiasnapshotstatus_snapshot_paths = args.snapshot_paths
            if args.uptime_kuma_url:
                cfg.uptime_kuma_url = args.uptime_kuma_url
            if args.kopiasnapshotstatus_token:
                cfg.kopiasnapshotstatus_token = args.kopiasnapshotstatus_token
            if args.max_age_hours is not None:
                cfg.kopiasnapshotstatus_max_age_hours = args.max_age_hours
            if args.log_file:
                cfg.log_file = args.log_file

            cfg.load_from_env()

            # Setup logging
            logger = setup_logging(cfg.log_file)

            # Log configuration summary
            logger.info("=" * 70)
            logger.info("🔍 KUMA SENTINEL - KOPIA SNAPSHOT CONFIGURATION")
            logger.info("=" * 70)
            config_summary = cfg.get_summary(mask_tokens=True)
            logger.info("📋 Kopia Snapshot Configuration:")
            paths_summary = config_summary.get("kopiasnapshotstatus_snapshot_paths", [])
            logger.info(f"   Snapshot Paths: {paths_summary}")
            logger.info(
                f"   Max Age Hours: {config_summary.get('kopiasnapshotstatus_max_age_hours', 24)}"
            )
            logger.info("🔔 Uptime Kuma Integration:")
            logger.info(f"   URL: {config_summary.get('uptime_kuma_url', 'N/A')}")
            logger.info(
                f"   Heartbeat Enabled: {config_summary.get('heartbeat_enabled', False)}"
            )
            logger.info("=" * 70)

            # Execute check with heartbeat support
            try:
                check_start_time = time.time()

                # Create checker config dict from Config object
                checker_config = {
                    "kopiasnapshotstatus_snapshot_paths": cfg.kopiasnapshotstatus_snapshot_paths,
                    "kopiasnapshotstatus_max_age_hours": cfg.kopiasnapshotstatus_max_age_hours,
                    "kopiasnapshotstatus_token": cfg.kopiasnapshotstatus_token,
                    "heartbeat_enabled": cfg.heartbeat_enabled,
                    "heartbeat_interval": cfg.heartbeat_interval,
                    "uptime_kuma_url": cfg.uptime_kuma_url,
                    "heartbeat_token": cfg.heartbeat_token,
                }

                checker = KopiaSnapshotChecker(logger, checker_config)
                result = checker.execute_with_heartbeat()

                check_end_time = time.time()
                check_duration = int(check_end_time - check_start_time)
                check_minutes = check_duration // 60

                # Send final heartbeat if enabled
                if (
                    cfg.heartbeat_enabled
                    and cfg.heartbeat_token
                    and cfg.uptime_kuma_url
                ):
                    send_push(
                        logger,
                        cfg.uptime_kuma_url,
                        cfg.heartbeat_token,
                        f"kopiasnapshotstatus check complete after {check_minutes}m",
                        command="kopiasnapshotstatus",
                    )

                # Send snapshot check alert based on result
                send_push(
                    logger,
                    cfg.uptime_kuma_url,
                    cfg.kopiasnapshotstatus_token,
                    f"{result.message} ({check_duration}s)",
                    command="kopiasnapshotstatus",
                    status=result.status,
                    timeout=PUSH_TIMEOUT_ALERT,
                )

                # Log result
                logger.info(f"📊 Check complete: {result.status.upper()}")
                logger.info(f"   Duration: {check_duration}s")
                logger.info(f"   Message: {result.message}")

                # Exit with appropriate status code
                exit_code = 0 if result.status == "up" else 1
                sys.exit(exit_code)

            except Exception as e:
                logger.error(f"❌ Unexpected error: {str(e)}", exc_info=True)
                # Send error alert
                send_push(
                    logger,
                    cfg.uptime_kuma_url,
                    cfg.kopiasnapshotstatus_token,
                    f"Kopia snapshot check error: {str(e)}",
                    command="kopiasnapshotstatus",
                    status="down",
                    timeout=PUSH_TIMEOUT_ALERT,
                )
                sys.exit(1)

        return kopiasnapshotstatus
