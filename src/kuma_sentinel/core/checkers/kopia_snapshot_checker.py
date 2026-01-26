"""Kopia snapshot status checker for sentinel."""

import json
import re
import subprocess
import time
from datetime import datetime
from logging import Logger
from typing import Optional, Tuple

from kuma_sentinel.core.checkers.base import Checker
from kuma_sentinel.core.models import CheckResult


def _validate_snapshot_path(path: str) -> None:
    """Validate snapshot path format to prevent path traversal attacks.

    Allows:
    - Local paths: /mnt/data, /backups, ./relative/path
    - SSH paths: user@host:/path, root@server.com:/data
    - Path components: alphanumerics, hyphens, underscores, dots, forward slashes

    Args:
        path: Path string to validate

    Raises:
        ValueError: If path contains invalid characters or suspicious patterns
    """
    if not path:
        raise ValueError("Snapshot path cannot be empty")

    # Pattern for local paths: /path or ./path or ~/path or relative/path
    # Components: alphanumerics, hyphens, underscores, dots, forward slashes, tildes
    local_path = r"^[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"

    # Pattern for SSH paths: user@host:/path
    # User: alphanumerics, hyphens, underscores, dots
    # Host: alphanumerics, hyphens, dots (domain names)
    # Path: alphanumerics, hyphens, underscores, dots, forward slashes
    ssh_path = (
        r"^[a-zA-Z0-9\-_.]+@[a-zA-Z0-9\-_.]+:[a-zA-Z0-9\-_.~/][a-zA-Z0-9\-_.~/]*$"
    )

    # Check against both patterns
    if not (re.match(local_path, path) or re.match(ssh_path, path)):
        raise ValueError(
            f"Invalid snapshot path format: {path}. "
            f"Path must be a local path (e.g., /mnt/data) or "
            f"SSH path (e.g., user@host:/path). "
            f"Only alphanumerics, hyphens, underscores, dots, slashes, and tildes allowed."
        )

    # Additional check: prevent path traversal attempts
    if ".." in path:
        raise ValueError(
            f"Invalid snapshot path: {path}. "
            f"Path traversal sequences (..) are not allowed."
        )

    # Prevent shell metacharacters
    dangerous_chars = ["$", "`", ";", "|", "&", "(", ")", "<", ">", "!", "*", "?"]
    for char in dangerous_chars:
        if char in path:
            raise ValueError(
                f"Invalid snapshot path: {path}. "
                f"Path contains dangerous character '{char}'. "
                f"Shell metacharacters are not allowed."
            )


def _run_kopia_command(
    logger: Logger, cmd: list, timeout: int = 30
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Run kopia snapshot list subprocess.

    Args:
        logger: Logger instance
        cmd: Kopia command list
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, stdout: Optional[str], stderr: Optional[str])
    """
    try:
        logger.debug(f"🔧 Running kopia command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        logger.error("❌ Kopia command timed out")
        return False, None, "Command timed out"
    except Exception as e:
        from kuma_sentinel.core.utils.sanitizer import DataSanitizer

        sanitized_error = DataSanitizer.sanitize_error_message(e)
        logger.error(f"❌ Error running kopia: {sanitized_error}")
        return False, None, sanitized_error


def _parse_snapshot_timestamp(snapshot_line: str) -> Optional[datetime]:
    """Parse kopia snapshot list output line to extract timestamp.

    Kopia output format: YYYY-MM-DD HH:MM:SS [rest of line]

    Args:
        snapshot_line: Single line from kopia snapshot list output

    Returns:
        datetime object or None if parsing fails
    """
    try:
        # Remove leading whitespace and get first two fields
        parts = snapshot_line.strip().split()
        if len(parts) < 2:
            return None

        date_str = parts[0]
        time_str = parts[1]
        timestamp_str = f"{date_str} {time_str}"

        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

    except (ValueError, IndexError):
        return None


def _parse_iso_timestamp(iso_timestamp: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp from JSON response.

    Args:
        iso_timestamp: ISO 8601 formatted timestamp string

    Returns:
        datetime object or None if parsing fails
    """
    try:
        return datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _get_latest_snapshot_age(
    logger: Logger, snapshot_path: str
) -> Tuple[Optional[float], Optional[dict]]:
    """Get age of latest snapshot in hours and its metadata.

    Args:
        logger: Logger instance
        snapshot_path: Path to snapshot in kopia

    Returns:
        Tuple of (age_hours: Optional[float], metadata: Optional[dict])
        metadata includes stats and retention reasons if available
    """
    cmd = [
        "kopia",
        "snapshot",
        "list",
        snapshot_path,
        "--json",
        "--all",
        "--max-results=1",
    ]

    success, stdout, stderr = _run_kopia_command(logger, cmd)

    if not success or not stdout:
        logger.error(f"❌ Failed to list snapshots for {snapshot_path}: {stderr}")
        return None, None

    try:
        # Parse JSON array response
        snapshots = json.loads(stdout)

        # Handle both single object and array responses
        if isinstance(snapshots, dict):
            snapshots = [snapshots]

        if not snapshots or len(snapshots) == 0:
            logger.warning(f"⚠️  No snapshots found for {snapshot_path}")
            return None, None

        # Get the first (most recent) snapshot
        latest_snapshot = snapshots[0]

        # Check for errors in snapshot stats
        stats = latest_snapshot.get("stats", {})
        error_count = stats.get("errorCount", 0)
        if error_count > 0:
            logger.error(f"❌ Snapshot for {snapshot_path} has {error_count} error(s)")
            return None, None

        # Extract endTime
        end_time_str = latest_snapshot.get("endTime")
        if not end_time_str:
            logger.error(f"❌ Missing endTime in snapshot data for {snapshot_path}")
            return None, None

        snap_datetime = _parse_iso_timestamp(end_time_str)
        if not snap_datetime:
            logger.error(f"❌ Failed to parse snapshot timestamp: {end_time_str}")
            return None, None

        # Calculate age (using UTC for comparison)
        # If snapshot datetime is aware (has timezone), convert to UTC-naive
        # Otherwise use naive datetime.now() for comparison
        if snap_datetime.tzinfo is not None:
            # Make it naive UTC for comparison
            snap_datetime = snap_datetime.replace(tzinfo=None)
        now = datetime.now()
        age = now - snap_datetime
        age_hours = age.total_seconds() / 3600

        # Extract metadata
        metadata = {
            "id": latest_snapshot.get("id"),
            "stats": stats,
            "retention_reason": latest_snapshot.get("retentionReason", []),
        }

        return age_hours, metadata

    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse JSON output for {snapshot_path}: {str(e)}")
        return None, None
    except KeyError as e:
        logger.error(f"❌ Missing required field in snapshot data: {str(e)}")
        return None, None


class KopiaSnapshotChecker(Checker):
    """Kopia snapshot status checker for sentinel."""

    name = "kopiasnapshotstatus"
    description = "Checks Kopia snapshot freshness and reports to Uptime Kuma"

    def execute(self) -> CheckResult:
        """Execute snapshot status check and return result.

        Returns:
            CheckResult with check outcome
        """
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting Kopia snapshot status check")

            # Get snapshots from config - type: ignore since KopiaSnapshotChecker expects KopiaSnapshotConfig
            snapshots = self.config.kopiasnapshotstatus_snapshots or []  # type: ignore
            default_max_age_hours = self.config.kopiasnapshotstatus_max_age_hours  # type: ignore

            if not snapshots:
                self.logger.error("❌ No snapshots configured")
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=f"[{self.name}] ✗ No snapshots configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_snapshots"},
                )

            # Check each snapshot
            all_results: dict[str, tuple[bool, Optional[float], Optional[dict]]] = {}
            failed_paths: list[str] = []
            old_snapshots: list[tuple[str, float, int, Optional[dict]]] = []

            for snapshot_config in snapshots:
                path = snapshot_config.get("path")
                if not path:
                    self.logger.warning(
                        "⚠️  Snapshot config missing 'path' field, skipping"
                    )
                    continue

                # Validate path format to prevent path traversal attacks
                try:
                    _validate_snapshot_path(path)
                except ValueError as e:
                    self.logger.error(
                        f"❌ Invalid snapshot path configuration: {str(e)}"
                    )
                    failed_paths.append(path)
                    continue

                # Get per-path max_age_hours or use default
                max_age_hours = snapshot_config.get(
                    "max_age_hours", default_max_age_hours
                )

                self.logger.info(
                    f"📋 Checking snapshot path: {path} (max age: {max_age_hours}h)"
                )

                age_hours, metadata = _get_latest_snapshot_age(self.logger, path)

                if age_hours is None:
                    all_results[path] = (False, None, None)
                    failed_paths.append(path)
                    continue

                all_results[path] = (True, age_hours, metadata)

                # Check age threshold
                if age_hours <= max_age_hours:
                    self.logger.info(
                        f"✅ OK ({path}): {age_hours:.1f}h <= {max_age_hours}h"
                    )
                else:
                    self.logger.warning(
                        f"⚠️  TOO OLD ({path}): {age_hours:.1f}h > {max_age_hours}h"
                    )
                    old_snapshots.append((path, age_hours, max_age_hours, metadata))

            check_end = time.time()
            check_duration = int(check_end - check_start)

            # Determine overall status
            if failed_paths:
                msg = f"[{self.name}] ✗ Failed to check snapshots: {', '.join(failed_paths)}"
                self.logger.error(f"❌ {msg}")
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=msg,
                    duration_seconds=check_duration,
                    details={"failed_paths": failed_paths},
                )

            if old_snapshots:
                details = [
                    f"{path}: {age:.1f}h > {threshold}h"
                    for path, age, threshold, _ in old_snapshots
                ]
                msg = f"[{self.name}] ✗ Snapshots too old: {'; '.join(details)}"
                self.logger.warning(f"⚠️  {msg}")
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=msg,
                    duration_seconds=check_duration,
                    details={
                        "old_snapshots": [
                            {
                                "path": path,
                                "age_hours": age,
                                "max_age_hours": threshold,
                                "metadata": metadata,
                            }
                            for path, age, threshold, metadata in old_snapshots
                        ]
                    },
                )

            # All snapshots are fresh
            fresh_details = [
                f"{path}: {age:.1f}h"
                for path, (success, age, _) in all_results.items()
                if success
            ]
            msg = f"[{self.name}] ✓ All snapshots fresh: {'; '.join(fresh_details)}"
            self.logger.info(f"✅ {msg}")
            return CheckResult(
                check_name=self.name,
                status="up",
                message=msg,
                duration_seconds=check_duration,
                details={
                    "snapshots": {
                        path: {
                            "age_hours": age,
                            "metadata": metadata,
                        }
                        for path, (success, age, metadata) in all_results.items()
                        if success
                    }
                },
            )

        except Exception as e:
            from kuma_sentinel.core.utils.sanitizer import DataSanitizer

            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(
                f"❌ Unexpected error during snapshot check: {sanitized_error}"
            )
            check_end = time.time()
            check_duration = int(check_end - check_start)
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"[{self.name}] ✗ Snapshot check error: {sanitized_error}",
                duration_seconds=check_duration,
                details={"error": sanitized_error},
            )
