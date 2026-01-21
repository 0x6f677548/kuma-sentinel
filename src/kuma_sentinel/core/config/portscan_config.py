"""Portscan command configuration."""

from typing import Dict, List

from .base import ConfigBase, FieldMapping


class PortscanConfig(ConfigBase):
    """Configuration for portscan command."""

    def __init__(self):
        """Initialize portscan configuration with defaults."""
        super().__init__()

        # Portscan-specific attributes
        self.portscan_nmap_ports = "1-1000"
        self.portscan_nmap_timing = "T3"
        self.portscan_nmap_arguments = []
        self.portscan_nmap_timeout = 3600
        self.portscan_exclude: List[str] = []
        self.portscan_ip_ranges: List[str] = []
        self.portscan_nmap_keep_xmloutput = False

    @staticmethod
    def _parse_comma_separated_list(value: str) -> List[str]:
        """Parse comma-separated string into list, handling both strings and lists."""
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for portscan configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "portscan_nmap_ports": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_PORTS",
                    arg_key="ports",
                    yaml_path="portscan.ports",
                ),
                "portscan_nmap_timing": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_TIMING",
                    arg_key="timing",
                    yaml_path="portscan.nmap.timing",
                ),
                "portscan_nmap_timeout": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_TIMEOUT",
                    arg_key="timeout",
                    yaml_path="portscan.nmap.timeout",
                    converter=int,
                ),
                "portscan_exclude": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_EXCLUDE",
                    arg_key="exclude",
                    yaml_path="portscan.exclude",
                    converter=self._parse_comma_separated_list,
                ),
                "portscan_nmap_keep_xmloutput": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT",
                    yaml_path="portscan.nmap.keep_xml_output",
                    converter=self._parse_bool,
                ),
                "portscan_nmap_arguments": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS",
                    yaml_path="portscan.nmap.arguments",
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_TOKEN",
                    arg_key="portscan_token",
                    yaml_path="portscan.uptime_kuma.token",
                ),
                "portscan_ip_ranges": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_IP_RANGES",
                    arg_key="ip_ranges",
                    yaml_path="portscan.ip_ranges",
                    converter=self._parse_comma_separated_list,
                ),
            }
        )
        return mappings

    def validate(self):
        """Validate portscan configuration."""
        # Validate shared config first (raises if invalid)
        super().validate()

        # Validate portscan-specific config
        errors = []

        if not self.portscan_ip_ranges:
            errors.append("No IP ranges specified")

        if self.portscan_nmap_timing not in ["T0", "T1", "T2", "T3", "T4", "T5"]:
            errors.append(
                f"Invalid timing level '{self.portscan_nmap_timing}'. Must be T0-T5"
            )

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get portscan configuration summary for logging."""
        return {
            "log_file": self.log_file,
            "portscan_nmap_ports": self.portscan_nmap_ports,
            "portscan_nmap_timing": self.portscan_nmap_timing,
            "portscan_nmap_timeout": f"{self.portscan_nmap_timeout}s",
            "portscan_nmap_arguments": (
                self.portscan_nmap_arguments
                if self.portscan_nmap_arguments
                else "(none)"
            ),
            "portscan_exclude": (
                ", ".join(self.portscan_exclude) if self.portscan_exclude else "(none)"
            ),
            "portscan_ip_ranges": ", ".join(self.portscan_ip_ranges),
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "portscan_token": self._mask_token(self.command_token, mask_tokens),
            "portscan_nmap_keep_xmloutput": self.portscan_nmap_keep_xmloutput,
        }
