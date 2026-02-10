"""
Portscan plugin for Kuma-Scout.

Scans TCP ports on target IP ranges and reports results to Uptime Kuma.
"""

import os
import xml.etree.ElementTree as ET
from typing import List, Optional

from pydantic import Field

from kuma_scout.core.logger import log_security_event
from kuma_scout.core.models import CheckResult

from .base import CheckConfig, Plugin, execute_with_timing


class PortscanConfig(CheckConfig):
    """Configuration for portscan plugin."""

    targets: List[str] = Field(description="IP ranges to scan")
    ports: str = Field(default="1-1000", description="Ports to scan (nmap format)")
    timeout: int = Field(default=3600, ge=1, description="Scan timeout in seconds")
    exclude: List[str] = Field(
        default_factory=list, description="Hosts to exclude (can be repeated)"
    )
    timing: str = Field(default="T3", description="Nmap timing template")
    arguments: List[str] = Field(
        default_factory=list, description="Additional nmap arguments"
    )
    keep_xml: bool = Field(default=False, description="Keep XML output file")


class PortscanPlugin(Plugin):
    """Plugin for port scanning."""

    name = "portscan"
    description = "Scans TCP ports on target IP ranges and reports to Uptime Kuma"
    config_class = PortscanConfig

    @execute_with_timing
    def execute(self, config: PortscanConfig) -> CheckResult:
        """Execute the port scan."""
        # Build nmap command
        cmd = self._build_nmap_command(config)

        # Create temp XML file
        nmap_xml = self._create_nmap_xml_file()
        cmd.extend(["-oX", nmap_xml])
        cmd.extend(config.targets)

        try:
            self.output_handler.info(f"Portscan: running {' '.join(cmd)}", echo=False)

            # Run nmap scan
            success, stdout, stderr, exit_code = self.run_command(
                cmd, timeout=config.timeout
            )

            if success:
                self.output_handler.info(
                    "Portscan: Nmap scan completed successfully", echo=False
                )

                # Parse results
                hosts_with_ports = (
                    self._parse_nmap_xml(nmap_xml) if os.path.exists(nmap_xml) else []
                )

                if hosts_with_ports:
                    open_ports_str = ", ".join(hosts_with_ports)
                    log_security_event(
                        "open_ports_detected",
                        f"Port scan detected open ports on hosts: {open_ports_str}",
                        level="warning",
                    )
                    self.output_handler.warning(
                        f"Portscan: Open ports found: {open_ports_str}", echo=False
                    )
                    return CheckResult(
                        check_name=config.name,
                        status="down",
                        message=f"Open ports found: {open_ports_str}",
                        details={"open_hosts": hosts_with_ports},
                    )
                else:
                    self.output_handler.info(
                        "Portscan: No open ports found", echo=False
                    )
                    return CheckResult(
                        check_name=config.name,
                        status="up",
                        message="No open ports found",
                        details={"open_hosts": []},
                    )
            else:
                error_msg = stderr.strip() if stderr else f"Exit code: {exit_code}"
                self.output_handler.error(
                    f"Portscan: Port scan failed: {error_msg}", echo=False
                )
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Port scan execution failed: {error_msg}",
                    details={"error": error_msg},
                )
        finally:
            # Cleanup XML file
            if nmap_xml and os.path.exists(nmap_xml) and not config.keep_xml:
                try:
                    os.remove(nmap_xml)
                    self.output_handler.debug(
                        f"Portscan: Cleaned up temporary file: {nmap_xml}", echo=False
                    )
                except OSError as e:
                    self.output_handler.warning(
                        f"Portscan: Failed to cleanup temporary file {nmap_xml}: {e}",
                        echo=False,
                    )

    def _build_nmap_command(self, config: PortscanConfig) -> List[str]:
        """Build the nmap command."""
        cmd = [
            "nmap",
            "-p",
            config.ports,
            f"-{config.timing}",
        ]

        if config.exclude:
            cmd.extend(["--exclude", ",".join(config.exclude)])

        if config.arguments:
            cmd.extend(config.arguments)

        return cmd

    def _create_nmap_xml_file(self) -> str:
        """Create temporary file for nmap XML output."""
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".xml", text=True)
        os.chmod(path, 0o600)
        os.close(fd)
        return path

    def _parse_nmap_xml(self, xml_file: str) -> List[str]:
        """Parse nmap XML output and extract hosts with open ports."""
        hosts_with_ports = []

        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            for host in root.findall(".//host"):
                ip = self._extract_ip(host)
                hostname = self._extract_hostname(host)
                open_ports = self._extract_open_ports(host)

                if open_ports:
                    host_display = hostname if hostname else ip
                    if host_display:
                        ports_str = ",".join(open_ports)
                        hosts_with_ports.append(f"{host_display}:{ports_str}")

        except Exception as e:
            self.output_handler.error(f"Error parsing nmap XML: {e}", echo=False)

        return hosts_with_ports

    def _extract_ip(self, host) -> Optional[str]:
        """Extract IP address from host element."""
        for addr in host.findall(".//address[@addrtype='ipv4']"):
            return addr.get("addr")
        return None

    def _extract_hostname(self, host) -> Optional[str]:
        """Extract hostname from host element."""
        for h in host.findall(".//hostname[@type='PTR']"):
            hostname = h.get("name")
            if hostname:
                return hostname
        return None

    def _extract_open_ports(self, host) -> List[str]:
        """Extract open ports from host element."""
        open_ports = []
        for port in host.findall(".//port[@protocol='tcp']"):
            state = port.find("state")
            if state is not None and state.get("state") == "open":
                port_id = port.get("portid")
                open_ports.append(f"{port_id}/tcp")
        return open_ports
