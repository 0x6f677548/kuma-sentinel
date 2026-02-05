"""
Portscan plugin for Kuma-Scout.

Scans TCP ports on target IP ranges and reports results to Uptime Kuma.
"""

import os
import time
import xml.etree.ElementTree as ET
from typing import List, Optional, cast

from pydantic import Field

from kuma_scout.core.models import CheckResult

from .base import CheckConfig, Plugin


class PortscanConfig(CheckConfig):
    """Configuration for portscan plugin."""

    targets: List[str] = Field(description="IP ranges to scan")
    ports: str = Field(default="1-1000", description="Ports to scan (nmap format)")
    timeout: int = Field(default=3600, ge=1, description="Scan timeout in seconds")
    exclude: List[str] = Field(default_factory=list, description="Hosts to exclude")
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

    def execute(self, config: CheckConfig) -> CheckResult:
        """Execute the port scan."""
        # Cast to the specific config type
        config = cast(PortscanConfig, config)
        scan_start = time.time()

        try:
            # Build nmap command
            cmd = self._build_nmap_command(config)

            # Create temp XML file
            nmap_xml = self._create_nmap_xml_file()
            cmd.extend(["-oX", nmap_xml])
            cmd.extend(config.targets)

            self.logger.info(f"🔍 Running: {' '.join(cmd)}")

            # Run nmap scan
            success, stdout, stderr, exit_code = self.run_command(
                cmd, timeout=config.timeout
            )

            if success:
                self.logger.info("✅ Nmap scan completed successfully")

                # Parse results
                hosts_with_ports = (
                    self._parse_nmap_xml(nmap_xml) if os.path.exists(nmap_xml) else []
                )

                scan_duration = int(time.time() - scan_start)

                if hosts_with_ports:
                    open_ports_str = ", ".join(hosts_with_ports)
                    self.logger.warning(f"⚠️  Open ports found: {open_ports_str}")
                    return CheckResult(
                        check_name=config.name,
                        status="down",
                        message=f"Open ports found: {open_ports_str}",
                        duration_seconds=scan_duration,
                        details={"open_hosts": hosts_with_ports},
                    )
                else:
                    self.logger.info("✅ No open ports found")
                    return CheckResult(
                        check_name=config.name,
                        status="up",
                        message="No open ports found",
                        duration_seconds=scan_duration,
                    )
            else:
                scan_duration = int(time.time() - scan_start)
                error_msg = stderr.strip() if stderr else f"Exit code: {exit_code}"
                self.logger.error(f"❌ Port scan failed: {error_msg}")
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message=f"Port scan execution failed: {error_msg}",
                    duration_seconds=scan_duration,
                    details={"error": error_msg},
                )

        except Exception as e:
            scan_duration = int(time.time() - scan_start)
            self.logger.error(f"❌ Unexpected error during port scan: {str(e)}")
            return CheckResult(
                check_name=config.name,
                status="down",
                message=f"Port scan error: {str(e)}",
                duration_seconds=scan_duration,
                details={"error": str(e)},
            )
        finally:
            # Cleanup XML file
            if (
                "nmap_xml" in locals()
                and nmap_xml
                and os.path.exists(nmap_xml)
                and not config.keep_xml
            ):
                try:
                    os.remove(nmap_xml)
                    self.logger.debug(f"🗑️  Cleaned up temporary file: {nmap_xml}")
                except OSError as e:
                    self.logger.warning(
                        f"⚠️  Failed to cleanup temporary file {nmap_xml}: {e}"
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
            self.logger.error(f"Error parsing nmap XML: {e}")

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
