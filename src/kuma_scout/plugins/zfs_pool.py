"""
ZFS pool plugin for Kuma-Scout.

Checks ZFS pool health status and free space percentage.
"""

from typing import Optional, Tuple

from pydantic import Field

from kuma_scout.core.models import CheckResult

from .base import CheckConfig, Plugin, execute_with_timing


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

    @execute_with_timing
    def execute(self, config: ZfsPoolConfig) -> CheckResult:
        """Execute ZFS pool status check."""
        self.output_handler.info(
            "ZfsPoolStatus: Starting ZFS pool status check", echo=False
        )

        if not config.pool:
            self.output_handler.error(
                "ZfsPoolStatus: No ZFS pool configured", echo=False
            )
            return CheckResult(
                check_name=config.name,
                status="down",
                message="No ZFS pool configured",
                details={"error": "no_pool"},
            )

        self.output_handler.info(
            f"ZfsPoolStatus: Checking pool '{config.pool}' (min free space: {config.min_free_percent}%)",
            echo=False,
        )

        health, free_percent = self._get_pool_status(config.pool, config.timeout)

        if health is None or free_percent is None:
            self.output_handler.error(
                f"Failed to get status for pool '{config.pool}'", echo=False
            )
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Failed to get status for pool '{config.pool}'",
                details={"error": "status_unavailable", "pool": config.pool},
            )

        # Check health status
        if health != "ONLINE":
            self.output_handler.warning(
                f"ZfsPoolStatus: Pool '{config.pool}' health is {health} (not ONLINE)",
                echo=False,
            )
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Pool '{config.pool}' is not healthy (status: {health})",
                details={
                    "health": health,
                    "free_percent": free_percent,
                    "pool": config.pool,
                },
            )

        # Check free space threshold
        if free_percent < config.min_free_percent:
            self.output_handler.warning(
                f"ZfsPoolStatus: Pool '{config.pool}' low on space: {free_percent:.1f}% free < {config.min_free_percent}% threshold",
                echo=False,
            )
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Pool '{config.pool}' low on space ({free_percent:.1f}% free < {config.min_free_percent}%)",
                details={
                    "health": health,
                    "free_percent": free_percent,
                    "min_free_percent": config.min_free_percent,
                    "pool": config.pool,
                },
            )
        else:
            self.output_handler.info(
                f"ZfsPoolStatus: Pool '{config.pool}' is healthy: {free_percent:.1f}% free >= {config.min_free_percent}%",
                echo=False,
            )
            return CheckResult(
                check_name=config.name,
                status="up",
                message=f"Pool '{config.pool}' is healthy ({free_percent:.1f}% free)",
                details={
                    "health": health,
                    "free_percent": free_percent,
                    "min_free_percent": config.min_free_percent,
                    "pool": config.pool,
                },
            )

    def _get_pool_status(
        self, pool_name: str, timeout: Optional[int] = None
    ) -> Tuple[Optional[str], Optional[float]]:
        """Get ZFS pool health and free space percentage."""
        cmd = [
            "zpool",
            "list",
            "-H",
            "-o",
            "name,cap,health",
            pool_name,
        ]

        try:
            success, stdout, stderr, exit_code = self.run_command(cmd, timeout=timeout)

            if not success:
                self.output_handler.error(
                    f"ZfsPoolStatus: zpool list failed for pool '{pool_name}': {stderr}",
                    echo=False,
                )
                return None, None

            output = stdout.strip()
            if not output:
                self.output_handler.error(
                    f"ZfsPoolStatus: No output from zpool list for pool '{pool_name}'",
                    echo=False,
                )
                return None, None

            # Parse output: name\tcap\thealth
            parts = output.split("\t")
            if len(parts) != 3:
                self.output_handler.error(
                    f"ZfsPoolStatus: Unexpected zpool output format for '{pool_name}': {output}",
                    echo=False,
                )
                return None, None

            name, cap, health = parts

            if name != pool_name:
                self.output_handler.error(
                    f"ZfsPoolStatus: Pool name mismatch: expected '{pool_name}', got '{name}'",
                    echo=False,
                )
                return None, None

            # Parse capacity percentage (remove %)
            cap_str = cap.rstrip("%")
            try:
                cap_percent = float(cap_str)
                free_percent = 100.0 - cap_percent
            except ValueError:
                self.output_handler.error(
                    f"ZfsPoolStatus: Could not parse capacity percentage: '{cap}'",
                    echo=False,
                )
                return None, None

            return health, free_percent

        except Exception as e:
            self.output_handler.error(
                f"ZfsPoolStatus: Error getting pool status for '{pool_name}': {str(e)}",
                echo=False,
            )
            return None, None
