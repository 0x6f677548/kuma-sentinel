"""Kopia snapshot status command configuration."""

from typing import Any, Dict, List

from .base import ConfigBase, FieldMapping


class KopiaSnapshotConfig(ConfigBase):
    """Configuration for kopiasnapshotstatus command."""

    def __init__(self):
        """Initialize kopia snapshot configuration with defaults."""
        super().__init__()

        # Kopia-specific attributes
        # snapshots: List of dicts with 'path' and optional 'max_age_hours' keys
        self.kopiasnapshotstatus_snapshots: List[Dict[str, Any]] = []
        # Global default for any path without explicit max_age_hours
        self.kopiasnapshotstatus_max_age_hours = 24

    @staticmethod
    def _snapshot_converter(snapshots_input: Any) -> List[Dict[str, Any]]:
        """Convert snapshot input to dict list.

        Handles multiple input formats:
        - Click tuples: ((path1, age1), (path2, age2), ...)
        - Environment string: "path1:age1,path2:age2"
        - Already converted list: [{"path": path1, "max_age_hours": age1}, ...]

        Returns: [{"path": path1, "max_age_hours": age1}, ...]
        """
        if not snapshots_input:
            return []

        # If already a list of dicts, return as-is
        if (
            isinstance(snapshots_input, list)
            and snapshots_input
            and isinstance(snapshots_input[0], dict)
        ):
            return snapshots_input

        # If it's a string from environment (e.g., "/data:24,/backups:48")
        if isinstance(snapshots_input, str):
            result = []
            for item in snapshots_input.split(","):
                item = item.strip()
                if not item:
                    continue
                parts = item.rsplit(
                    ":", 1
                )  # Split from right to handle paths with colons
                if len(parts) == 2:
                    try:
                        result.append(
                            {
                                "path": parts[0].strip(),
                                "max_age_hours": int(parts[1].strip()),
                            }
                        )
                    except ValueError:
                        # If can't parse age, skip this entry
                        continue
                else:
                    # Path without age - use default
                    result.append({"path": parts[0].strip()})
            return result

        # If it's Click tuples ((path1, age1), (path2, age2), ...)
        try:
            return [
                {"path": path, "max_age_hours": max_age}
                for path, max_age in snapshots_input
            ]
        except (TypeError, ValueError):
            return []

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for kopia snapshot configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "kopiasnapshotstatus_snapshots": FieldMapping(
                    arg_key="snapshots",
                    yaml_path="kopiasnapshotstatus.snapshots",
                    converter=self._snapshot_converter,
                ),
                "kopiasnapshotstatus_max_age_hours": FieldMapping(
                    arg_key="max_age_hours",
                    yaml_path="kopiasnapshotstatus.max_age_hours",
                    converter=int,
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN",
                    arg_key="kopiasnapshotstatus_token",
                    yaml_path="kopiasnapshotstatus.uptime_kuma.token",
                ),
            }
        )
        return mappings

    def validate(self):
        """Validate kopia snapshot configuration."""
        # Validate shared config first (raises if invalid)
        super().validate()

        # Validate snapshot paths if any are configured
        # (paths are optional at config time, but will be validated at execution time)
        if self.kopiasnapshotstatus_snapshots:
            from kuma_sentinel.core.checkers.kopia_snapshot_checker import (
                _validate_snapshot_path,
            )

            for snapshot in self.kopiasnapshotstatus_snapshots:
                path = snapshot.get("path")
                if path:
                    try:
                        _validate_snapshot_path(path)
                    except ValueError as e:
                        raise ValueError(
                            f"Invalid snapshot path in configuration: {str(e)}"
                        ) from e

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get kopia snapshot configuration summary for logging."""
        # Build snapshot summary
        snapshot_summary = []
        for snapshot in self.kopiasnapshotstatus_snapshots:
            path = snapshot.get("path", "")
            max_age = snapshot.get(
                "max_age_hours", self.kopiasnapshotstatus_max_age_hours
            )
            snapshot_summary.append(f"{path}@{max_age}h")

        return {
            "log_file": self.log_file,
            "kopiasnapshotstatus_snapshots": (
                "; ".join(snapshot_summary) if snapshot_summary else "(using defaults)"
            ),
            "kopiasnapshotstatus_max_age_hours_default": self.kopiasnapshotstatus_max_age_hours,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "kopiasnapshotstatus_token": self._mask_token(
                self.command_token, mask_tokens
            ),
        }
