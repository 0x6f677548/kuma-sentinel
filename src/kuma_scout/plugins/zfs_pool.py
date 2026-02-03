"""
ZFS pool plugin for Kuma-Scout.

Checks ZFS pool health status and free space percentage.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from ..core.models import CheckResult
from .base import CheckConfig, Plugin


class ZfsPoolConfig(CheckConfig):
    """Configuration for ZFS pool plugin."""

    pools: List[Dict[str, Any]] = Field(default_factory=list, description="List of ZFS pools to check")
    free_space_percent_default: float = Field(default=10.0, ge=0, le=100, description="Default free space threshold")


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

            if not config.pools:
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message="No ZFS pools configured",
                    duration_seconds=int(time.time() - check_start),
                    details={"error": "no_pools"},
                )

            # Track pool statuses
            pool_details: Dict[str, Dict] = {}
            unhealthy_pools: List[str] = []
            low_space_pools: List[Tuple[str, float, float]] = []
            failed_pools: List[Tuple[str, str]] = []

            # Check each pool
            for pool_config in config.pools:
                pool_name: str = pool_config.get("name", "unknown")
                threshold: float = pool_config.get("free_space_percent_min", config.free_space_percent_default)

                self.logger.info(f"📋 Checking pool '{pool_name}' (min free space: {threshold}%)")

                health, free_percent = self._get_pool_status(pool_name)

                if health is None or free_percent is None:
                    failed_pools.append((pool_name, "Could not retrieve pool status"))
                    pool_details[pool_name] = {
                        "status": "unknown",
                        "free_percent": None,
                        "threshold": threshold,
                        "error": "status_unavailable",
                    }
                    continue

                # Store pool details
                pool_details[pool_name] = {
                    "status": health,
                    "free_percent": free_percent,
                    "threshold": threshold,
                }

                # Check health status
                if health != "ONLINE":
                    unhealthy_pools.append(pool_name)
                    self.logger.warning(f"⚠️  Pool '{pool_name}' health is {health} (not ONLINE)")
                    continue

                # Check free space threshold
                if free_percent < threshold:
                    low_space_pools.append((pool_name, free_percent, threshold))
                    self.logger.warning(
                        f"⚠️  Pool '{pool_name}' low on space: {free_percent:.1f}% free < {threshold}% threshold"
                    )
                else:
                    self.logger.info(
                        f"✅ Pool '{pool_name}': {health} with {free_percent:.1f}% free (threshold: {threshold}%)"
                    )

            # Determine overall result
            duration = int(time.time() - check_start)

            if failed_pools:
                failed_names = [name for name, _ in failed_pools]
                message = f"Failed to check pools: {', '.join(failed_names)}"
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={"failed_pools": failed_names, "pool_details": pool_details},
                )

            if unhealthy_pools:
                message = f"Unhealthy pools: {', '.join(unhealthy_pools)}"
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={"unhealthy_pools": unhealthy_pools, "pool_details": pool_details},
                )

            if low_space_pools:
                low_info = []
                for pool_name, free_pct, thresh in low_space_pools:
                    low_info.append(f"{pool_name} ({free_pct:.1f}% < {thresh}%)")
                message = f"Low space pools: {', '.join(low_info)}"
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=message,
                    duration_seconds=duration,
                    details={"low_space_pools": low_space_pools, "pool_details": pool_details},
                )

            # All pools healthy
            self.logger.info("✅ All ZFS pools are healthy")
            return CheckResult(
                check_name=config.name,
                status="up",
                message="All ZFS pools are healthy",
                duration_seconds=duration,
                details={"pool_details": pool_details},
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
        cmd = ["zpool", "list", "-H", "-o", "name,size,alloc,free,cap,health", pool_name]

        try:
            success, stdout, stderr, exit_code = self.run_command(cmd, timeout=30)

            if not success:
                self.logger.error(f"❌ zpool list failed for pool '{pool_name}': {stderr}")
                return None, None

            output = stdout.strip()
            if not output:
                self.logger.error(f"❌ No output from zpool list for pool '{pool_name}'")
                return None, None

            # Parse output: name\tsize\talloc\tfree\tcap\thealth
            parts = output.split('\t')
            if len(parts) != 6:
                self.logger.error(f"❌ Unexpected zpool output format for '{pool_name}': {output}")
                return None, None

            name, size, alloc, free, cap, health = parts

            if name != pool_name:
                self.logger.error(f"❌ Pool name mismatch: expected '{pool_name}', got '{name}'")
                return None, None

            # Parse capacity percentage (remove %)
            cap_str = cap.rstrip('%')
            try:
                cap_percent = float(cap_str)
                free_percent = 100.0 - cap_percent
            except ValueError:
                self.logger.error(f"❌ Could not parse capacity percentage: '{cap}'")
                return None, None

            return health, free_percent

        except Exception as e:
            self.logger.error(f"❌ Error getting pool status for '{pool_name}': {str(e)}")
            return None, None
