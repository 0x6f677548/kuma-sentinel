"""
ZFS pool plugin for Kuma-Scout.

Checks ZFS pool health status and free space percentage.
"""

import time
from typing import Optional, Tuple

from pydantic import Field

from ..core.models import CheckResult
from .base import CheckConfig, Plugin


class ZfsPoolConfig(CheckConfig):
    """Configuration for ZFS pool plugin."""

    pool: str = Field(..., description="Name of the ZFS pool to check")
    min_free_percent: int = Field(
        default=10, ge=1, le=99, description="Minimum free space percentage of the pool"
    )


class ZfsPoolPlugin(Plugin):
    """Plugin for checking ZFS pool status."""

    name = "zfspoolstatus"
    description = "Checks ZFS pool health status and free space percentage"
    config_class = ZfsPoolConfig

    def execute(self, config: ZfsPoolConfig) -> CheckResult:
        """Execute ZFS pool status check."""
        check_start = time.time()

        try:
            self.logger.info("🔍 Starting ZFS pool status check")

            if not config.pool:
                self.logger.error("❌ No ZFS pool configured")
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message="No ZFS pool configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_pool"},
                )

            self.logger.info(
                f"📋 Checking pool '{config.pool}' (min free space: {config.min_free_percent}%)"
            )

            health, free_percent = self._get_pool_status(config.pool)

            if health is None or free_percent is None:
                self.logger.error(f"❌ Failed to get status for pool '{config.pool}'")
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Failed to get status for pool '{config.pool}'",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "status_unavailable", "pool": config.pool},
                )

            check_duration = int(time.time() - check_start)

            # Check health status
            if health != "ONLINE":
                self.logger.warning(
                    f"⚠️  Pool '{config.pool}' health is {health} (not ONLINE)"
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Pool '{config.pool}' is not healthy (status: {health})",
                    duration_seconds=check_duration,
                    details={
                        "health": health,
                        "free_percent": free_percent,
                        "pool": config.pool,
                    },
                )

            # Check free space threshold
            if free_percent < config.min_free_percent:
                self.logger.warning(
                    f"⚠️  Pool '{config.pool}' low on space: {free_percent:.1f}% free < {config.min_free_percent}% threshold"
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Pool '{config.pool}' low on space ({free_percent:.1f}% free < {config.min_free_percent}%)",
                    duration_seconds=check_duration,
                    details={
                        "health": health,
                        "free_percent": free_percent,
                        "min_free_percent": config.min_free_percent,
                        "pool": config.pool,
                    },
                )
            else:
                self.logger.info(
                    f"✅ Pool '{config.pool}' is healthy: {free_percent:.1f}% free >= {config.min_free_percent}%"
                )
                return CheckResult(
                    check_name=config.name,
                    status="up",
                    message=f"Pool '{config.pool}' is healthy ({free_percent:.1f}% free)",
                    duration_seconds=check_duration,
                    details={
                        "health": health,
                        "free_percent": free_percent,
                        "min_free_percent": config.min_free_percent,
                        "pool": config.pool,
                    },
                )

        except Exception as e:
            duration = int(time.time() - check_start)
            self.logger.error(f"❌ Unexpected error during ZFS pool check: {str(e)}")
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"ZFS pool check error: {str(e)}",
                duration_seconds=duration,
                details={"error": str(e)},
            )

    def _get_pool_status(self, pool_name: str) -> Tuple[Optional[str], Optional[float]]:
        """Get ZFS pool health and free space percentage."""
        cmd = [
            "zpool",
            "list",
            "-H",
            "-o",
            "name,size,alloc,free,cap,health",
            pool_name,
        ]

        try:
            success, stdout, stderr, exit_code = self.run_command(cmd, timeout=30)

            if not success:
                self.logger.error(
                    f"❌ zpool list failed for pool '{pool_name}': {stderr}"
                )
                return None, None

            output = stdout.strip()
            if not output:
                self.logger.error(
                    f"❌ No output from zpool list for pool '{pool_name}'"
                )
                return None, None

            # Parse output: name\tsize\talloc\tfree\tcap\thealth
            parts = output.split("\t")
            if len(parts) != 6:
                self.logger.error(
                    f"❌ Unexpected zpool output format for '{pool_name}': {output}"
                )
                return None, None

            name, size, alloc, free, cap, health = parts

            if name != pool_name:
                self.logger.error(
                    f"❌ Pool name mismatch: expected '{pool_name}', got '{name}'"
                )
                return None, None

            # Parse capacity percentage (remove %)
            cap_str = cap.rstrip("%")
            try:
                cap_percent = float(cap_str)
                free_percent = 100.0 - cap_percent
            except ValueError:
                self.logger.error(f"❌ Could not parse capacity percentage: '{cap}'")
                return None, None

            return health, free_percent

        except Exception as e:
            self.logger.error(
                f"❌ Error getting pool status for '{pool_name}': {str(e)}"
            )
            return None, None
