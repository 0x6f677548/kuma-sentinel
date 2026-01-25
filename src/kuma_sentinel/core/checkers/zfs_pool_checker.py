"""ZFS pool status monitoring implementation."""

import re
import subprocess
import time
from logging import Logger
from typing import Dict, List, Optional, Tuple

from kuma_sentinel.core.config.zfs_pool_config import ZfsPoolStatusConfig
from kuma_sentinel.core.models import CheckResult

from .base import Checker


def _get_pool_status(
    logger: Logger, pool_name: str
) -> Tuple[Optional[str], Optional[float]]:
    """Get ZFS pool health and free space percentage.

    Runs: zpool list -H -o name,size,alloc,free,cap,health <pool_name>

    Returns:
        Tuple of (health_status, free_space_percent) or (None, None) if pool not found
        health_status: "ONLINE", "OFFLINE", "FAULTED", "DEGRADED", etc.
        free_space_percent: float between 0-100 representing free space percentage

    Raises:
        subprocess.CalledProcessError: If zpool command fails
    """
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,size,alloc,free,cap,health", pool_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        # Output format: name\tsize\talloc\tfree\tcap\thealth
        # Example: tank\t1.81T\t1.00T\t828G\t55%\tONLINE
        output = result.stdout.strip()

        if not output:
            logger.warning(
                f"⚠️  Pool '{pool_name}' not found or no output from zpool list"
            )
            return None, None

        fields = output.split("\t")

        if len(fields) < 6:
            logger.warning(
                f"⚠️  Unexpected zpool output format for '{pool_name}': {output}"
            )
            return None, None

        health = fields[5].strip()
        cap_str = fields[4].strip()

        # Extract percentage from cap field (e.g., "55%" -> 55.0)
        cap_match = re.search(r"(\d+(?:\.\d+)?)", cap_str)
        if not cap_match:
            logger.warning(
                f"⚠️  Could not parse capacity from '{cap_str}' for pool '{pool_name}'"
            )
            return None, None

        cap_percent = float(cap_match.group(1))
        # Free space percent = 100 - capacity percent
        free_percent = 100.0 - cap_percent

        return health, free_percent

    except subprocess.TimeoutExpired:
        logger.error(f"❌ zpool list timeout for pool '{pool_name}'")
        return None, None
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ zpool list failed for pool '{pool_name}': {e.stderr.strip()}")
        return None, None
    except FileNotFoundError:
        logger.error("❌ zpool command not found - is ZFS installed?")
        return None, None


class ZfsPoolStatusChecker(Checker):
    """Checker for monitoring ZFS pool health and free space."""

    name = "zfspoolstatus"
    description = "Checks ZFS pool health status and free space percentage"

    def __init__(self, logger: Logger, config):
        """Initialize ZFS pool status checker.

        Args:
            logger: Logger instance
            config: ZfsPoolStatusConfig instance
        """
        super().__init__(logger, config)
        self.config: ZfsPoolStatusConfig = config

    def execute(self) -> CheckResult:
        """Execute ZFS pool status check and return result.

        Checks each configured pool for:
        - Health status (only ONLINE is acceptable; any other status triggers DOWN)
        - Free space percentage (must be >= configured threshold)

        Returns:
            CheckResult with status "up" if all pools healthy and have sufficient free space,
            status "down" if any pool is unhealthy or low on space
        """
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting ZFS pool status check")

            pools = self.config.zfspoolstatus_pools or []
            default_threshold = self.config.zfspoolstatus_free_space_percent_default

            if not pools:
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=f"[{self.name}] ✗ No ZFS pools configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_pools"},
                )

            # Track pool statuses for detailed reporting
            pool_details: Dict[str, Dict] = {}
            unhealthy_pools: List[str] = []
            low_space_pools: List[Tuple[str, float, float]] = []
            failed_pools: List[Tuple[str, str]] = []

            # Check each configured pool
            for pool_config in pools:
                pool_name: str = pool_config.get("name", "unknown")
                threshold: float = pool_config.get(
                    "free_space_percent_min",
                    default_threshold,
                )

                self.logger.info(
                    f"📋 Checking pool '{pool_name}' " f"(min free space: {threshold}%)"
                )

                health, free_percent = _get_pool_status(self.logger, pool_name)

                if health is None or free_percent is None:
                    failed_pools.append((pool_name, "Could not retrieve pool status"))
                    pool_details[pool_name] = {
                        "status": "unknown",
                        "free_percent": None,
                        "threshold": threshold,
                        "error": "status_unavailable",
                    }
                    continue

                # Store pool details for summary
                pool_details[pool_name] = {
                    "status": health,
                    "free_percent": free_percent,
                    "threshold": threshold,
                }

                # Check health status (only ONLINE is acceptable)
                if health != "ONLINE":
                    unhealthy_pools.append(pool_name)
                    self.logger.warning(
                        f"⚠️  Pool '{pool_name}' health is {health} (not ONLINE)"
                    )
                    continue

                # Check free space threshold
                if free_percent < threshold:
                    low_space_pools.append((pool_name, free_percent, threshold))
                    self.logger.warning(
                        f"⚠️  Pool '{pool_name}' low on space: "
                        f"{free_percent:.1f}% free < {threshold}% threshold"
                    )
                else:
                    self.logger.info(
                        f"✅ Pool '{pool_name}': {health} with "
                        f"{free_percent:.1f}% free (threshold: {threshold}%)"
                    )

            # Determine overall check status and message
            duration = int(time.time() - check_start)

            if failed_pools:
                failed_names = [name for name, _ in failed_pools]
                message = (
                    f"[{self.name}] ✗ Failed to check pools: {', '.join(failed_names)}"
                )
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={
                        "failed_pools": failed_names,
                        "pool_details": pool_details,
                    },
                )

            if unhealthy_pools:
                message = (
                    f"[{self.name}] ✗ Unhealthy pools: {', '.join(unhealthy_pools)}"
                )
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={
                        "unhealthy_pools": unhealthy_pools,
                        "pool_details": pool_details,
                    },
                )

            if low_space_pools:
                details_list = [
                    f"{pool}: {free:.1f}% < {threshold}%"
                    for pool, free, threshold in low_space_pools
                ]
                message = f"[{self.name}] ✗ Low free space: {'; '.join(details_list)}"
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={
                        "low_space_pools": [(p, f, t) for p, f, t in low_space_pools],
                        "pool_details": pool_details,
                    },
                )

            # All pools healthy and have sufficient free space
            pool_summary = [
                f"{name}: {data['free_percent']:.1f}% free"
                for name, data in pool_details.items()
            ]
            message = f"[{self.name}] ✓ All pools healthy: {'; '.join(pool_summary)}"
            return CheckResult(
                check_name=self.name,
                status="up",
                message=message,
                duration_seconds=duration,
                details={"pool_details": pool_details},
            )

        except Exception as e:
            from kuma_sentinel.core.utils.sanitizer import DataSanitizer

            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(
                f"❌ Unexpected error during ZFS pool check: {sanitized_error}"
            )
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"[{self.name}] ✗ ZFS pool check error: {sanitized_error}",
                duration_seconds=int(time.time() - check_start),
                details={"error": sanitized_error},
            )
