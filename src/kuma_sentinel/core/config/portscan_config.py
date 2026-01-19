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
        self.portscan_exclude_ips = ""
        self.portscan_ip_ranges: List[str] = []
        self.portscan_nmap_keep_xmloutput = False

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for portscan configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "portscan_nmap_ports": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_PORTS",
                    arg_key="ports",
                    ini_section="portscan.targets",
                    ini_option="ports",
                ),
                "portscan_nmap_timing": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_TIMING",
                    arg_key="timing",
                    ini_section="portscan.nmap",
                    ini_option="timing",
                ),
                "portscan_nmap_timeout": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_TIMEOUT",
                    arg_key="timeout",
                    ini_section="portscan.nmap",
                    ini_option="timeout",
                    converter=int,
                ),
                "portscan_exclude_ips": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_EXCLUDE_IPS",
                    arg_key="exclude",
                    ini_section="portscan.targets",
                    ini_option="exclude_ips",
                ),
                "portscan_nmap_keep_xmloutput": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT",
                    ini_section="portscan.nmap",
                    ini_option="keep_xml_output",
                    bool_converter=True,
                ),
                "portscan_nmap_arguments": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS",
                    ini_section="portscan.nmap",
                    ini_option="arguments",
                    converter=str,
                    list_converter=True,
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_TOKEN",
                    arg_key="portscan_token",
                    ini_section="portscan.uptime_kuma",
                    ini_option="token",
                ),
                "portscan_ip_ranges": FieldMapping(
                    arg_key="ip_ranges",
                    ini_section="portscan.targets",
                    ini_option="ip_ranges",
                    converter=str,
                    list_converter=True,
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
            "portscan_exclude_ips": (
                self.portscan_exclude_ips if self.portscan_exclude_ips else "(none)"
            ),
            "portscan_ip_ranges": ", ".join(self.portscan_ip_ranges),
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "portscan_token": self._mask_token(self.command_token, mask_tokens),
            "portscan_nmap_keep_xmloutput": self.portscan_nmap_keep_xmloutput,
        }
