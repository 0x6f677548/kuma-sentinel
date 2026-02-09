"""
Kopia snapshot plugin for Kuma-Scout.

Checks Kopia snapshot freshness and reports results to Uptime Kuma.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional, cast

from pydantic import Field

from kuma_scout.core.models import CheckResult

from .base import CheckConfig, Plugin


class KopiaSnapshotConfig(CheckConfig):
    """Configuration for kopia snapshot plugin."""

    path: str = Field(..., description="Snapshot path to check")
    max_age_hours: int = Field(
        default=24, ge=1, description="Maximum age of the snapshot in hours"
    )


class KopiaSnapshotPlugin(Plugin):
    """Plugin for checking Kopia snapshot status."""

    name = "kopiasnapshotstatus"
    description = "Checks Kopia snapshot freshness and reports to Uptime Kuma"
    config_class = KopiaSnapshotConfig

    def execute(self, config: CheckConfig) -> CheckResult:
        """Execute the snapshot status check."""
        # Cast to the specific config type
        config = cast(KopiaSnapshotConfig, config)
        check_start = time.time()

        try:
            self.output_handler.info("KopiaSnapshotStatus: Starting check", echo=False)

            if not config.path:
                self.output_handler.error("No snapshot path configured", echo=False)
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message="No snapshot path configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_path"},
                )

            # Validate path format
            try:
                self._validate_snapshot_path(config.path)
            except ValueError as e:
                self.output_handler.error(
                    f"KopiaSnapshotStatus: Invalid snapshot path configuration: {str(e)}",
                    echo=False,
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Invalid snapshot path: {str(e)}",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": str(e), "path": config.path},
                )

            self.output_handler.info(
                f"KopiaSnapshotStatus: Checking snapshot path {config.path} (max age: {config.max_age_hours}h)",
                echo=False,
            )

            # Get snapshot info
            age_hours = self._get_snapshot_info(config.path)

            if age_hours is None:
                self.output_handler.error(
                    f"KopiaSnapshotStatus: Failed to get snapshot info for {config.path}",
                    echo=False,
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Failed to get snapshot info for {config.path}",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "failed_to_get_info", "path": config.path},
                )

            # Check if snapshot is too old
            check_duration = int(time.time() - check_start)

            if age_hours <= config.max_age_hours:
                self.output_handler.info(
                    f"KopiaSnapshotStatus: OK ({config.path}): {age_hours:.1f}h <= {config.max_age_hours}h",
                    echo=False,
                )
                return CheckResult(
                    check_name=config.name,
                    status="up",
                    message=f"Snapshot is fresh ({age_hours:.1f}h old)",
                    duration_seconds=check_duration,
                    details={
                        "age_hours": age_hours,
                        "max_age_hours": config.max_age_hours,
                        "path": config.path,
                    },
                )
            else:
                self.output_handler.warning(
                    f"KopiaSnapshotStatus: TOO OLD ({config.path}): {age_hours:.1f}h > {config.max_age_hours}h",
                    echo=False,
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Snapshot is too old ({age_hours:.1f}h > {config.max_age_hours}h)",
                    duration_seconds=check_duration,
                    details={
                        "age_hours": age_hours,
                        "max_age_hours": config.max_age_hours,
                        "path": config.path,
                    },
                )

        except Exception as e:
            check_duration = int(time.time() - check_start)
            self.output_handler.error(
                "KopiaSnapshotStatus: Unexpected error during snapshot check",
                echo=False,
            )
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Snapshot check error: {str(e)}",
                duration_seconds=check_duration,
                details={"error": str(e), "path": config.path},
            )

    def _validate_snapshot_path(self, path: str) -> None:
        """Validate snapshot path format."""
        if not path:
            raise ValueError("Snapshot path cannot be empty")

        # Pattern for local paths
        local_path = r"^[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"

        # Pattern for SSH paths
        ssh_path = (
            r"^[a-zA-Z0-9\-_.]+@[a-zA-Z0-9\-_.]+:[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"
        )

        if not (re.match(local_path, path) or re.match(ssh_path, path)):
            raise ValueError(f"Invalid snapshot path format: {path}")

    def _get_snapshot_info(self, snapshot_path: str) -> Optional[float]:
        """Get snapshot information for a path."""
        cmd = [
            "kopia",
            "snapshot",
            "list",
            snapshot_path,
            "--json",
            "--all",
            "--max-results=1",
        ]

        success, stdout, stderr, exit_code = self.run_command(cmd)

        if not success or not stdout:
            self.output_handler.error(
                f"KopiaSnapshotStatus: Failed to list snapshots for {snapshot_path}: {stderr}",
                echo=False,
            )
            return None

        try:
            snapshots = json.loads(stdout)

            if isinstance(snapshots, dict):
                snapshots = [snapshots]

            if not snapshots:
                self.output_handler.warning(
                    f"KopiaSnapshotStatus: No snapshots found for {snapshot_path}",
                    echo=False,
                )
                return None

            latest_snapshot = snapshots[0]

            # Check for errors
            stats = latest_snapshot.get("stats", {})
            error_count = stats.get("errorCount", 0)
            if error_count > 0:
                self.output_handler.error(
                    f"KopiaSnapshotStatus: Snapshot for {snapshot_path} has {error_count} error(s)",
                    echo=False,
                )
                return None

            # Extract endTime
            end_time_str = latest_snapshot.get("endTime")
            if not end_time_str:
                self.output_handler.error(
                    f"KopiaSnapshotStatus: Missing endTime in snapshot data for {snapshot_path}",
                    echo=False,
                )
                return None

            # Parse timestamp
            end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
            now = datetime.now(end_time.tzinfo)
            age_hours = (now - end_time).total_seconds() / 3600

            return age_hours

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.output_handler.error(
                f"KopiaSnapshotStatus: Failed to parse snapshot data for {snapshot_path}: {str(e)}",
                echo=False,
            )
            return None
