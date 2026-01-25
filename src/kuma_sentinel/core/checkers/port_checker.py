"""Port scanning checker for sentinel."""

import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from logging import Logger
from typing import List, Optional, Tuple

from kuma_sentinel.core.checkers.base import Checker
from kuma_sentinel.core.config.portscan_config import PortscanConfig
from kuma_sentinel.core.models import CheckResult


def _build_nmap_command(config: PortscanConfig) -> List[str]:
    """Build the nmap command based on config.

    Args:
        config: PortscanConfig object

    Returns:
        List of command arguments
    """
    cmd = [
        "nmap",
        "-p",
        str(config.portscan_nmap_ports),
        f"-{config.portscan_nmap_timing}",
        "-oX",
    ]
    return cmd


def _create_nmap_xml_file() -> str:
    """Create temporary file for nmap XML output.

    Returns:
        Path to temporary XML file
    """
    f = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xml")
    path = f.name
    f.close()
    return path


def _run_nmap_process(
    logger: Logger, cmd: List[str], timeout: int
) -> Tuple[bool, Optional[str]]:
    """Run nmap subprocess.

    Args:
        logger: Logger instance
        cmd: Nmap command list
        timeout: Timeout in seconds

    Returns:
        Tuple of (success: bool, stderr_msg: Optional[str])
    """
    try:
        logger.debug(f"🔧 Running nmap command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            if result.stdout:
                logger.info("📊 Scan output:")
                for line in result.stdout.split("\n"):
                    if line.strip():
                        logger.info(f"  {line}")
            return True, None
        else:
            logger.error(f"❌ Nmap scan failed with exit code {result.returncode}")
            return False, result.stderr

    except subprocess.TimeoutExpired:
        logger.error("❌ Nmap scan timed out")
        return False, None


def _extract_host_ip(host) -> Optional[str]:
    """Extract IPv4 address from host element.

    Args:
        host: XML host element

    Returns:
        IP address or None
    """
    for addr in host.findall("address"):
        if addr.get("addrtype") == "ipv4":
            return addr.get("addr")
    return None


def _extract_hostname(host) -> Optional[str]:
    """Extract hostname from host element.

    Args:
        host: XML host element

    Returns:
        Hostname or None
    """
    for h in host.findall(".//hostname[@type='PTR']"):
        hostname = h.get("name")
        if hostname:
            return hostname
    return None


def _extract_open_ports(host) -> List[str]:
    """Extract open ports from host element.

    Args:
        host: XML host element

    Returns:
        List of open ports in format "portid/tcp"
    """
    open_ports = []
    for port in host.findall(".//port[@protocol='tcp']"):
        state = port.find("state")
        if state is not None and state.get("state") == "open":
            port_id = port.get("portid")
            open_ports.append(f"{port_id}/tcp")
    return open_ports


def _parse_nmap_xml(logger: Logger, xml_file: str) -> List[str]:
    """Parse nmap XML output and extract hosts with open ports.

    Args:
        logger: Logger instance
        xml_file: Path to nmap XML output file

    Returns:
        List of strings with hosts and open ports in format
        "hostname(ip):port/tcp,port/tcp"
    """
    hosts_with_ports = []

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        for host in root.findall("host"):
            ip = _extract_host_ip(host)
            if not ip:
                continue

            hostname = _extract_hostname(host)
            open_ports = _extract_open_ports(host)

            if not open_ports:
                continue

            host_str = f"{hostname}({ip})" if hostname else ip
            hosts_with_ports.append(f"{host_str}:{','.join(open_ports)}")

        logger.info(
            f"✅ Parsed XML: found {len(hosts_with_ports)} hosts with open ports"
        )
        return hosts_with_ports

    except ET.ParseError as e:
        logger.error(f"❌ Failed to parse XML: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"❌ Error reading XML: {str(e)}")
        return []


def _run_nmap_scan(
    logger: Logger, config: PortscanConfig
) -> Tuple[bool, Optional[str]]:
    """Run nmap scan with periodic heartbeat pings.

    Args:
        logger: Logger instance
        config: PortscanConfig object

    Returns:
        Tuple of (success: bool, nmap_xml_path: Optional[str])
    """
    nmap_xml = None

    try:
        nmap_xml = _create_nmap_xml_file()
        cmd = _build_nmap_command(config)
        cmd.append(nmap_xml)

        # Get config values
        exclude_hosts = config.portscan_exclude
        nmap_args = config.portscan_nmap_arguments or []
        portscan_ip_ranges = config.portscan_ip_ranges or []

        if exclude_hosts:
            # Join list into comma-separated string for nmap
            exclude_str = ",".join(exclude_hosts)
            cmd.extend(["--exclude", exclude_str])
        cmd.extend(nmap_args)
        cmd.extend(portscan_ip_ranges)

        logger.info(f"🔍 Running: {' '.join(cmd)}")

        # Run nmap scan
        success, stderr = _run_nmap_process(logger, cmd, config.portscan_nmap_timeout)

        if success:
            logger.info("✅ Nmap scan completed successfully")
            return True, nmap_xml
        else:
            if stderr:
                logger.error(f"  Error: {stderr}")
            return False, nmap_xml

    except Exception as e:
        from kuma_sentinel.core.utils.sanitizer import DataSanitizer

        sanitized_error = DataSanitizer.sanitize_error_message(e)
        logger.error(f"❌ Error running nmap: {sanitized_error}")
        return False, nmap_xml


class PortChecker(Checker):
    """Port scanning checker for sentinel."""

    name = "portscan"
    description = "Scans TCP ports on target IP ranges and reports to Uptime Kuma"

    def execute(self) -> CheckResult:
        """Execute port scan and return result.

        Returns:
            CheckResult with scan outcome
        """
        scan_start = time.time()

        try:
            self.logger.info("🔍 Starting port scan check")

            # Run nmap scan - cast config to PortscanConfig
            scan_success, nmap_xml = _run_nmap_scan(self.logger, self.config)  # type: ignore

            # Parse XML results
            hosts_with_ports = []
            if nmap_xml and os.path.exists(nmap_xml) and os.path.getsize(nmap_xml) > 0:
                hosts_with_ports = _parse_nmap_xml(self.logger, nmap_xml)

            # Calculate scan duration
            scan_end = time.time()
            scan_duration = int(scan_end - scan_start)

            # Cleanup
            if nmap_xml and os.path.exists(nmap_xml):
                self.logger.info(f"📋 XML output saved to: {nmap_xml}")
                if not self.config.portscan_nmap_keep_xmloutput:  # type: ignore
                    os.remove(nmap_xml)

            # Determine result
            if not scan_success:
                self.logger.error("❌ Port scan failed")
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=f"[{self.name}] ✗ Port scan execution failed",
                    duration_seconds=scan_duration,
                    details={"error": "scan_execution_failed"},
                )
            elif hosts_with_ports:
                open_ports_str = ", ".join(hosts_with_ports)
                self.logger.warning(f"⚠️  Open ports found: {open_ports_str}")
                return CheckResult(
                    check_name=self.name,
                    status="down",
                    message=f"[{self.name}] ✗ Open ports found: {open_ports_str}",
                    duration_seconds=scan_duration,
                    details={"open_hosts": hosts_with_ports},
                )
            else:
                self.logger.info("✅ No open ports found")
                return CheckResult(
                    check_name=self.name,
                    status="up",
                    message=f"[{self.name}] ✓ No open ports found",
                    duration_seconds=scan_duration,
                )

        except Exception as e:
            from kuma_sentinel.core.utils.sanitizer import DataSanitizer

            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(
                f"❌ Unexpected error during port scan: {sanitized_error}"
            )
            scan_end = time.time()
            scan_duration = int(scan_end - scan_start)
            return CheckResult(
                check_name=self.name,
                status="down",
                message=f"[{self.name}] ✗ Port scan error: {sanitized_error}",
                duration_seconds=scan_duration,
                details={"error": sanitized_error},
            )


# Public API for testing and direct use
def parse_nmap_xml(logger: Logger, xml_file: str) -> List[str]:
    """Public API for parsing nmap XML output.

    Args:
        logger: Logger instance
        xml_file: Path to nmap XML output file

    Returns:
        List of strings with hosts and open ports
    """
    return _parse_nmap_xml(logger, xml_file)
