"""ZFS pool status command configuration."""

from typing import Any, Dict, List

from .base import ConfigBase, FieldMapping


class ZfsPoolStatusConfig(ConfigBase):
    """Configuration for zfspoolstatus command."""

    def __init__(self):
        """Initialize ZFS pool configuration with defaults."""
        super().__init__()

        # ZFS pool-specific attributes
        self.zfspoolstatus_pools: List[Dict[str, Any]] = []
        self.zfspoolstatus_free_space_percent_default = 10

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for ZFS pool configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "zfspoolstatus_pools": FieldMapping(
                    arg_key="pools",
                    yaml_path="zfspoolstatus.pools",
                    converter=self._pool_converter,
                ),
                "zfspoolstatus_free_space_percent_default": FieldMapping(
                    arg_key="free_space_percent",
                    yaml_path="zfspoolstatus.free_space_percent_default",
                    converter=int,
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN",
                    arg_key="zfspoolstatus_token",
                    yaml_path="zfspoolstatus.uptime_kuma.token",
                ),
            }
        )
        return mappings

    @staticmethod
    def _pool_converter(pools_input: Any) -> List[Dict[str, Any]]:
        """Convert multiple input formats to normalized pool structure.

        Handles:
        - Environment variable string format: "pool1:10,pool2:15"
        - Click tuples from CLI: ((pool1, 10), (pool2, 15), ...)
        - YAML lists: [{"name": "pool1", "free_space_percent_min": 10}, ...]
        - Already converted lists

        Args:
            pools_input: Input in one of the formats above

        Returns:
            Normalized list of dicts with "name" and optional "free_space_percent_min"
        """
        if isinstance(pools_input, str):
            return ZfsPoolStatusConfig._parse_pool_string(pools_input)

        if isinstance(pools_input, list):
            return ZfsPoolStatusConfig._parse_pool_list(pools_input)

        # Try to parse as Click tuples
        try:
            return [
                {"name": pool, "free_space_percent_min": threshold}
                for pool, threshold in pools_input
            ]
        except (TypeError, ValueError):
            return []

    @staticmethod
    def _parse_pool_string(pools_str: str) -> List[Dict[str, Any]]:
        """Parse pool string format: "pool1:10,pool2:15"."""
        if not pools_str or not pools_str.strip():
            return []

        result = []
        for item in pools_str.split(","):
            item = item.strip()
            if not item:
                continue

            parts = item.rsplit(":", 1)
            if len(parts) == 2:
                result.append(
                    {
                        "name": parts[0].strip(),
                        "free_space_percent_min": int(parts[1].strip()),
                    }
                )
            else:
                result.append({"name": parts[0].strip()})
        return result

    @staticmethod
    def _parse_pool_list(pools_list: list) -> List[Dict[str, Any]]:
        """Parse pool list format."""
        result = []
        for item in pools_list:
            if isinstance(item, dict):
                # Already normalized
                result.append(item)
            elif isinstance(item, (tuple, list)) and len(item) >= 1:
                # Tuple/list format
                result.append(
                    {
                        "name": item[0],
                        "free_space_percent_min": (
                            int(item[1]) if len(item) > 1 else None
                        ),
                    }
                )
        return result

    def validate(self):
        """Validate ZFS pool configuration."""
        super().validate()

        errors = []

        if not self.zfspoolstatus_pools:
            errors.append("No ZFS pools configured")

        if (
            self.zfspoolstatus_free_space_percent_default < 0
            or self.zfspoolstatus_free_space_percent_default > 100
        ):
            errors.append(
                "Default free space percent must be between 0 and 100, "
                f"got {self.zfspoolstatus_free_space_percent_default}"
            )

        # Validate individual pool thresholds
        for pool_config in self.zfspoolstatus_pools:
            if "free_space_percent_min" in pool_config:
                threshold = pool_config["free_space_percent_min"]
                if threshold < 0 or threshold > 100:
                    errors.append(
                        f"Pool '{pool_config.get('name')}' free space percent must be "
                        f"between 0 and 100, got {threshold}"
                    )

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get ZFS pool configuration summary for logging.

        Args:
            mask_tokens: Whether to mask sensitive tokens in output

        Returns:
            Dictionary with configuration summary
        """
        pools_summary = []
        for pool_config in self.zfspoolstatus_pools:
            pool_name = pool_config.get("name", "unknown")
            threshold = pool_config.get("free_space_percent_min")
            if threshold is not None:
                pools_summary.append(f"{pool_name}:{threshold}%")
            else:
                pools_summary.append(pool_name)

        return {
            "log_file": self.log_file,
            "log_level": self.log_level,
            "zfspoolstatus_pools": (
                ", ".join(pools_summary) if pools_summary else "none"
            ),
            "zfspoolstatus_free_space_percent_default": f"{self.zfspoolstatus_free_space_percent_default}%",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "zfspoolstatus_token": self._mask_token(self.command_token, mask_tokens),
        }
