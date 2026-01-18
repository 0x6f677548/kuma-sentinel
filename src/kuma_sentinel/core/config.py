"""Configuration management for kuma sentinel."""

import configparser
import os
from typing import List, Optional, Set

# Hardcoded defaults
DEFAULT_CONFIG_PATH = "/etc/kuma-sentinel/config.ini"
DEFAULT_LOG_FILE = "/var/log/kuma-sentinel.log"
DEFAULT_PORTSCAN_NMAP_PORTS = "1-1000"
DEFAULT_PORTSCAN_NMAP_TIMING = "T3"
DEFAULT_PORTSCAN_NMAP_ARGUMENTS: List[str] = []
DEFAULT_HEARTBEAT_ENABLED = True
DEFAULT_HEARTBEAT_INTERVAL = 300
DEFAULT_PORTSCAN_NMAP_TIMEOUT = 3600  # seconds


class Config:
    """Configuration management with multiple sources."""

    def __init__(self):
        """Initialize configuration with defaults."""
        self.log_file = DEFAULT_LOG_FILE
        self.portscan_nmap_ports = DEFAULT_PORTSCAN_NMAP_PORTS
        self.portscan_nmap_timing = DEFAULT_PORTSCAN_NMAP_TIMING
        self.portscan_nmap_arguments = DEFAULT_PORTSCAN_NMAP_ARGUMENTS.copy()
        self.heartbeat_enabled = DEFAULT_HEARTBEAT_ENABLED
        self.heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self.portscan_exclude_ips = ""
        self.portscan_ip_ranges: List[str] = []
        self.uptime_kuma_url: Optional[str] = None
        self.heartbeat_token: Optional[str] = None
        self.portscan_token: Optional[str] = None
        self.portscan_nmap_keep_xmloutput = False
        # Track which values were explicitly set (not from defaults)
        self._explicitly_set: Set[str] = set()

    def load_from_env(self):
        """Load configuration from environment variables (only if not already set by INI/CLI)."""
        if (
            "log_file" not in self._explicitly_set
            and "KUMA_SENTINEL_LOG_FILE" in os.environ
        ):
            self.log_file = os.environ["KUMA_SENTINEL_LOG_FILE"]

        if (
            "portscan_nmap_ports" not in self._explicitly_set
            and "KUMA_SENTINEL_PORTSCAN_NMAP_PORTS" in os.environ
        ):
            self.portscan_nmap_ports = os.environ["KUMA_SENTINEL_PORTSCAN_NMAP_PORTS"]

        if (
            "portscan_nmap_timing" not in self._explicitly_set
            and "KUMA_SENTINEL_PORTSCAN_NMAP_TIMING" in os.environ
        ):
            self.portscan_nmap_timing = os.environ["KUMA_SENTINEL_PORTSCAN_NMAP_TIMING"]

        if (
            "portscan_exclude_ips" not in self._explicitly_set
            and "KUMA_SENTINEL_PORTSCAN_EXCLUDE_IPS" in os.environ
        ):
            self.portscan_exclude_ips = os.environ["KUMA_SENTINEL_PORTSCAN_EXCLUDE_IPS"]

        if (
            "heartbeat_interval" not in self._explicitly_set
            and "KUMA_SENTINEL_HEARTBEAT_INTERVAL" in os.environ
        ):
            self.heartbeat_interval = int(
                os.environ["KUMA_SENTINEL_HEARTBEAT_INTERVAL"]
            )

        if (
            "portscan_nmap_keep_xmloutput" not in self._explicitly_set
            and "KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT" in os.environ
        ):
            self.portscan_nmap_keep_xmloutput = (
                os.environ["KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT"].lower()
                == "true"
            )

        if (
            "portscan_nmap_arguments" not in self._explicitly_set
            and "KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS" in os.environ
        ):
            self.portscan_nmap_arguments = os.environ[
                "KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS"
            ].split()

        if (
            "heartbeat_enabled" not in self._explicitly_set
            and "KUMA_SENTINEL_HEARTBEAT_ENABLED" in os.environ
        ):
            self.heartbeat_enabled = (
                os.environ["KUMA_SENTINEL_HEARTBEAT_ENABLED"].lower() == "true"
            )

    def load_from_ini(self, config_file: str):
        """Load configuration from INI file.

        Args:
            config_file: Path to INI configuration file

        Raises:
            FileNotFoundError: If config file not found
            RuntimeError: If config file parsing fails
        """
        try:
            parser = configparser.ConfigParser()
            parser.read(config_file)

            self._load_logging_config(parser)
            self._load_nmap_config(parser)
            self._load_heartbeat_config(parser)
            self._load_targets_config(parser)
            self._load_uptime_kuma_config(parser)

        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse config file {config_file}: {str(e)}"
            ) from e

    def _load_logging_config(self, parser: configparser.ConfigParser):
        """Load logging configuration from INI."""
        if parser.has_section("logging") and parser.has_option("logging", "log_file"):
            self.log_file = parser.get("logging", "log_file")
            self._explicitly_set.add("log_file")

    def _load_nmap_config(self, parser: configparser.ConfigParser):
        """Load nmap configuration from INI."""
        section = "portscan.nmap"
        if not parser.has_section(section):
            return

        if parser.has_option(section, "timing"):
            self.portscan_nmap_timing = parser.get(section, "timing")
            self._explicitly_set.add("portscan_nmap_timing")

        if parser.has_option(section, "arguments"):
            args_str = parser.get(section, "arguments")
            if args_str.strip():
                self.portscan_nmap_arguments = args_str.split()
                self._explicitly_set.add("portscan_nmap_arguments")

        if parser.has_option(section, "keep_xml_output"):
            self.portscan_nmap_keep_xmloutput = parser.getboolean(
                section, "keep_xml_output"
            )
            self._explicitly_set.add("portscan_nmap_keep_xmloutput")

    def _load_heartbeat_config(self, parser: configparser.ConfigParser):
        """Load heartbeat configuration from INI."""
        section = "heartbeat"
        if not parser.has_section(section):
            return

        if parser.has_option(section, "enabled"):
            self.heartbeat_enabled = parser.getboolean(section, "enabled")
            self._explicitly_set.add("heartbeat_enabled")

        if parser.has_option(section, "interval"):
            self.heartbeat_interval = parser.getint(section, "interval")
            self._explicitly_set.add("heartbeat_interval")

    def _load_targets_config(self, parser: configparser.ConfigParser):
        """Load targets configuration from INI."""
        section = "portscan.targets"
        if not parser.has_section(section):
            return

        if parser.has_option(section, "ports"):
            self.portscan_nmap_ports = parser.get(section, "ports")
            self._explicitly_set.add("portscan_nmap_ports")

        if parser.has_option(section, "exclude_ips"):
            self.portscan_exclude_ips = parser.get(section, "exclude_ips")
            self._explicitly_set.add("portscan_exclude_ips")

        if parser.has_option(section, "ip_ranges"):
            ranges_str = parser.get(section, "ip_ranges")
            if ranges_str.strip():
                self.portscan_ip_ranges = [
                    r.strip() for r in ranges_str.split(",") if r.strip()
                ]
                self._explicitly_set.add("portscan_ip_ranges")

    def _load_uptime_kuma_config(self, parser: configparser.ConfigParser):
        """Load uptime kuma configuration from INI."""
        section = "uptime_kuma"
        if not parser.has_section(section):
            return

        if parser.has_option(section, "url"):
            self.uptime_kuma_url = parser.get(section, "url")
            self._explicitly_set.add("uptime_kuma_url")

        if parser.has_option(section, "heartbeat_token"):
            self.heartbeat_token = parser.get(section, "heartbeat_token")
            self._explicitly_set.add("heartbeat_token")

        if parser.has_option(section, "portscan_token"):
            self.portscan_token = parser.get(section, "portscan_token")
            self._explicitly_set.add("portscan_token")

    def load_from_args(self, args):
        """Load configuration from command-line arguments.

        Args:
            args: Parsed command-line arguments
        """
        # IP ranges and URLs from positional arguments
        if args.ip_ranges:
            self.portscan_ip_ranges = args.ip_ranges
            self._explicitly_set.add("portscan_ip_ranges")

        if args.uptime_kuma_url:
            self.uptime_kuma_url = args.uptime_kuma_url
            self._explicitly_set.add("uptime_kuma_url")

        if args.heartbeat_token:
            self.heartbeat_token = args.heartbeat_token
            self._explicitly_set.add("heartbeat_token")

        if args.portscan_token:
            self.portscan_token = args.portscan_token
            self._explicitly_set.add("portscan_token")

        # Override with CLI flags
        if args.ports:
            self.portscan_nmap_ports = args.ports
            self._explicitly_set.add("portscan_nmap_ports")

        if args.timing:
            self.portscan_nmap_timing = args.timing
            self._explicitly_set.add("portscan_nmap_timing")

        if args.exclude:
            self.portscan_exclude_ips = args.exclude
            self._explicitly_set.add("portscan_exclude_ips")

        if args.log_file:
            self.log_file = args.log_file
            self._explicitly_set.add("log_file")

    def validate(self):
        """Validate required configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        errors = []

        if not self.portscan_ip_ranges:
            errors.append("No IP ranges specified")

        if not self.uptime_kuma_url:
            errors.append("Uptime Kuma URL not provided")

        if not self.heartbeat_token:
            errors.append("Heartbeat push token not provided")

        if not self.portscan_token:
            errors.append("Port scan push token not provided")

        if self.portscan_nmap_timing not in ["T0", "T1", "T2", "T3", "T4", "T5"]:
            errors.append(
                f"Invalid timing level '{self.portscan_nmap_timing}'. Must be T0-T5"
            )

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get configuration summary for logging.

        Args:
            mask_tokens: If True, mask security tokens in output

        Returns:
            Dictionary with configuration summary
        """
        heartbeat_tok = (
            "***" if mask_tokens and self.heartbeat_token else self.heartbeat_token
        )
        portscan_tok = (
            "***" if mask_tokens and self.portscan_token else self.portscan_token
        )

        return {
            "log_file": self.log_file,
            "portscan_nmap_ports": self.portscan_nmap_ports,
            "portscan_nmap_timing": self.portscan_nmap_timing,
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
            "heartbeat_token": heartbeat_tok,
            "portscan_token": portscan_tok,
            "portscan_nmap_keep_xmloutput": self.portscan_nmap_keep_xmloutput,
        }
