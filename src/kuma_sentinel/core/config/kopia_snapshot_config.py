"""Kopia snapshot status command configuration."""

from typing import Dict, List

from .base import ConfigBase, FieldMapping


class KopiaSnapshotConfig(ConfigBase):
    """Configuration for kopiasnapshotstatus command."""

    def __init__(self):
        """Initialize kopia snapshot configuration with defaults."""
        super().__init__()

        # Kopia-specific attributes
        self.kopiasnapshotstatus_snapshot_paths: List[str] = []
        self.kopiasnapshotstatus_max_age_hours = 24

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for kopia snapshot configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "kopiasnapshotstatus_snapshot_paths": FieldMapping(
                    arg_key="snapshot_paths",
                    yaml_path="kopiasnapshotstatus.targets.snapshot_paths",
                ),
                "kopiasnapshotstatus_max_age_hours": FieldMapping(
                    env_var="KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS",
                    arg_key="max_age_hours",
                    yaml_path="kopiasnapshotstatus.targets.max_age_hours",
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

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get kopia snapshot configuration summary for logging."""
        return {
            "log_file": self.log_file,
            "kopiasnapshotstatus_snapshot_paths": ", ".join(
                self.kopiasnapshotstatus_snapshot_paths
            ),
            "kopiasnapshotstatus_max_age_hours": self.kopiasnapshotstatus_max_age_hours,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "kopiasnapshotstatus_token": self._mask_token(
                self.command_token, mask_tokens
            ),
        }
