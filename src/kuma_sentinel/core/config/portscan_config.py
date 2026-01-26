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
        """Parse comma-separated string into list, handling both strings and lists.

        Args:
            value: A string, list, or tuple to parse

        Returns:
            List of strings with whitespace trimmed
        """
        # Handle lists and tuples (from Click's multiple=True)
        if isinstance(value, (list, tuple)):
            return list(value)
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for portscan configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "portscan_nmap_ports": FieldMapping(
                    arg_key="ports",
                    yaml_path="portscan.ports",
                ),
                "portscan_nmap_timing": FieldMapping(
                    arg_key="timing",
                    yaml_path="portscan.nmap.timing",
                ),
                "portscan_nmap_timeout": FieldMapping(
                    arg_key="timeout",
                    yaml_path="portscan.nmap.timeout",
                    converter=int,
                ),
                "portscan_exclude": FieldMapping(
                    arg_key="exclude",
                    yaml_path="portscan.exclude",
                    converter=self._parse_comma_separated_list,
                ),
                "portscan_nmap_keep_xmloutput": FieldMapping(
                    yaml_path="portscan.nmap.keep_xml_output",
                    converter=self._parse_bool,
                ),
                "portscan_nmap_arguments": FieldMapping(
                    yaml_path="portscan.nmap.arguments",
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_PORTSCAN_TOKEN",
                    arg_key="portscan_token",
                    yaml_path="portscan.uptime_kuma.token",
                ),
                "portscan_ip_ranges": FieldMapping(
                    arg_key="ip_ranges",
                    yaml_path="portscan.ip_ranges",
                    converter=self._parse_comma_separated_list,
                ),
            }
        )
        return mappings

    @staticmethod
    def _validate_port_part(part: str) -> None:
        """Validate a single port or port range.

        Args:
            part: A port (e.g., "80") or range (e.g., "1-1000")

        Raises:
            ValueError: If the port or range is invalid
        """
        if "-" in part:
            # It's a range
            start_str, end_str = part.split("-")
            start = int(start_str)
            end = int(end_str)

            if start < 1 or start > 65535:
                raise ValueError(
                    f"Invalid port in range '{part}': start port {start} out of range (1-65535)"
                )
            if end < 1 or end > 65535:
                raise ValueError(
                    f"Invalid port in range '{part}': end port {end} out of range (1-65535)"
                )
            if start > end:
                raise ValueError(
                    f"Invalid port range '{part}': start port ({start}) > end port ({end})"
                )
        else:
            # Single port
            port = int(part)
            if port < 1 or port > 65535:
                raise ValueError(
                    f"Invalid port number: {port}. Must be between 1 and 65535"
                )

    @staticmethod
    def validate_port_range(port_spec: str) -> None:
        """Validate port range specification.

        Allows:
        - Single port: 80, 443
        - Range: 1-1000, 8000-9000
        - Comma-separated: 22,80,443 or 20-25,80,443-445

        Args:
            port_spec: Port specification string

        Raises:
            ValueError: If port specification is invalid
        """
        import re

        if not port_spec:
            raise ValueError("Port specification cannot be empty")

        # Validate format
        pattern = r"^(\d+(-\d+)?)(,\d+(-\d+)?)*$"
        if not re.match(pattern, port_spec):
            raise ValueError(
                f"Invalid port specification: '{port_spec}'. "
                f"Use format: 80 or 1-1000 or 22,80,443 or 20-25,80,443-445"
            )

        # Validate individual ports and ranges
        parts = port_spec.split(",")
        for part in parts:
            PortscanConfig._validate_port_part(part)

        return None

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

        # Validate port range
        try:
            self.validate_port_range(self.portscan_nmap_ports)
        except ValueError as e:
            errors.append(f"Invalid port specification: {str(e)}")

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
