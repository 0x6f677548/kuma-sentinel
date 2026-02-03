"""
Kopia snapshot plugin for Kuma-Scout.

Checks Kopia snapshot freshness and reports results to Uptime Kuma.
"""

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from ..core.models import CheckResult
from .base import CheckConfig, Plugin


class KopiaSnapshotConfig(CheckConfig):
    """Configuration for kopia snapshot plugin."""

    snapshots: List[Dict[str, Any]] = Field(default_factory=list, description="List of snapshots to check")
    max_age_hours: int = Field(default=24, ge=1, description="Default maximum age in hours")


class KopiaSnapshotPlugin(Plugin):
    """Plugin for checking Kopia snapshot status."""

    name = "kopiasnapshotstatus"
    description = "Checks Kopia snapshot freshness and reports to Uptime Kuma"
    config_class = KopiaSnapshotConfig

    def execute(self, config: KopiaSnapshotConfig) -> CheckResult:
        """Execute the snapshot status check."""
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting Kopia snapshot status check")

            if not config.snapshots:
                self.logger.error("❌ No snapshots configured")
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message="No snapshots configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_snapshots"},
                )

            # Check each snapshot
            all_results: Dict[str, tuple[bool, Optional[float], Optional[Dict]]] = {}
            failed_paths: List[str] = []
            old_snapshots: List[tuple[str, float, int, Optional[Dict]]] = []

            for snapshot_config in config.snapshots:
                path = snapshot_config.get("path")
                if not path:
                    self.logger.warning("⚠️  Snapshot config missing 'path' field, skipping")
                    continue

                # Validate path format
                try:
                    self._validate_snapshot_path(path)
                except ValueError as e:
                    self.logger.error(f"❌ Invalid snapshot path configuration: {str(e)}")
                    failed_paths.append(path)
                    continue

                # Get per-path max_age_hours or use default
                max_age_hours = snapshot_config.get("max_age_hours", config.max_age_hours)

                self.logger.info(f"📋 Checking snapshot path: {path} (max age: {max_age_hours}h)")

                # Get snapshot info
                age_hours, metadata = self._get_snapshot_info(path)

                if age_hours is None:
                    failed_paths.append(path)
                    continue

                all_results[path] = (True, age_hours, metadata)

                # Check if snapshot is too old
                if age_hours <= max_age_hours:
                    self.logger.info(f"✅ OK ({path}): {age_hours:.1f}h <= {max_age_hours}h")
                else:
                    self.logger.warning(f"⚠️  TOO OLD ({path}): {age_hours:.1f}h > {max_age_hours}h")
                    old_snapshots.append((path, age_hours, max_age_hours, metadata))

            # Determine overall result
            check_duration = int(time.time() - check_start)

            if failed_paths:
                failed_str = ", ".join(failed_paths)
                self.logger.error(f"❌ Failed to check snapshots: {failed_str}")
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Failed to check snapshots: {failed_str}",
                    duration_seconds=check_duration,
                    details={"failed_paths": failed_paths},
                )
            elif old_snapshots:
                old_info = []
                for path, age, max_age, _metadata in old_snapshots:
                    old_info.append(f"{path} ({age:.1f}h old, max {max_age}h)")
                    self.logger.warning(f"⚠️  Old snapshot: {path} is {age:.1f}h old (max {max_age}h)")

                old_str = "; ".join(old_info)
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Old snapshots found: {old_str}",
                    duration_seconds=check_duration,
                    details={"old_snapshots": old_snapshots},
                )
            else:
                self.logger.info("✅ All snapshots are fresh")
                return CheckResult(
                    check_name=config.name,
                    status="up",
                    message="All snapshots are fresh",
                    duration_seconds=check_duration,
                    details={"checked_snapshots": len(all_results)},
                )

        except Exception as e:
            check_duration = int(time.time() - check_start)
            self.logger.error(f"❌ Unexpected error during snapshot check: {str(e)}")
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Snapshot check error: {str(e)}",
                duration_seconds=check_duration,
                details={"error": str(e)},
            )

    def _validate_snapshot_path(self, path: str) -> None:
        """Validate snapshot path format."""
        if not path:
            raise ValueError("Snapshot path cannot be empty")

        # Pattern for local paths
        local_path = r"^[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"

        # Pattern for SSH paths
        ssh_path = r"^[a-zA-Z0-9\-_.]+@[a-zA-Z0-9\-_.]+:[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"

        if not (re.match(local_path, path) or re.match(ssh_path, path)):
            raise ValueError(f"Invalid snapshot path format: {path}")

    def _get_snapshot_info(self, snapshot_path: str) -> tuple[Optional[float], Optional[Dict]]:
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
            self.logger.error(f"❌ Failed to list snapshots for {snapshot_path}: {stderr}")
            return None, None

        try:
            snapshots = json.loads(stdout)

            if isinstance(snapshots, dict):
                snapshots = [snapshots]

            if not snapshots:
                self.logger.warning(f"⚠️  No snapshots found for {snapshot_path}")
                return None, None

            latest_snapshot = snapshots[0]

            # Check for errors
            stats = latest_snapshot.get("stats", {})
            error_count = stats.get("errorCount", 0)
            if error_count > 0:
                self.logger.error(f"❌ Snapshot for {snapshot_path} has {error_count} error(s)")
                return None, None

            # Extract endTime
            end_time_str = latest_snapshot.get("endTime")
            if not end_time_str:
                self.logger.error(f"❌ Missing endTime in snapshot data for {snapshot_path}")
                return None, None

            # Parse timestamp
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            now = datetime.now(end_time.tzinfo)
            age_hours = (now - end_time).total_seconds() / 3600

            metadata = {
                "id": latest_snapshot.get("id"),
                "stats": stats,
                "retention_reason": latest_snapshot.get("retentionReason", []),
            }

            return age_hours, metadata

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"❌ Failed to parse snapshot data for {snapshot_path}: {str(e)}")
            return None, None
