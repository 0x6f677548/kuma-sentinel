"""Tests for port checker module."""

import os
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from kuma_sentinel.core.checkers.port_checker import (
    PortChecker,
    _extract_host_ip,
    _extract_hostname,
    _extract_open_ports,
    parse_nmap_xml,
)
from kuma_sentinel.core.models import CheckResult


def test_extract_host_ip():
    """Test IP extraction from host element."""
    xml_str = """<host>
        <address addr="192.168.1.10" addrtype="ipv4"/>
    </host>"""

    host = ET.fromstring(xml_str)
    ip = _extract_host_ip(host)
    assert ip == "192.168.1.10"


def test_extract_host_ip_not_found():
    """Test IP extraction returns None when not found."""
    xml_str = "<host></host>"
    host = ET.fromstring(xml_str)
    ip = _extract_host_ip(host)
    assert ip is None


def test_extract_hostname():
    """Test hostname extraction from host element."""
    xml_str = """<host>
        <hostnames>
            <hostname name="server.local" type="PTR"/>
        </hostnames>
    </host>"""

    host = ET.fromstring(xml_str)
    hostname = _extract_hostname(host)
    assert hostname == "server.local"


def test_extract_hostname_not_found():
    """Test hostname extraction returns None when not found."""
    xml_str = "<host></host>"
    host = ET.fromstring(xml_str)
    hostname = _extract_hostname(host)
    assert hostname is None


def test_extract_hostname_multiple():
    """Test hostname extraction with multiple hostnames - first selected."""
    xml_str = """<host>
        <hostnames>
            <hostname name="server.local" type="PTR"/>
            <hostname name="server.example.com" type="user"/>
        </hostnames>
    </host>"""

    host = ET.fromstring(xml_str)
    hostname = _extract_hostname(host)
    assert hostname == "server.local"


def test_extract_open_ports():
    """Test open ports extraction from host element."""
    xml_str = """<host>
        <ports>
            <port protocol="tcp" portid="22">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="443">
                <state state="closed"/>
            </port>
        </ports>
    </host>"""

    host = ET.fromstring(xml_str)
    ports = _extract_open_ports(host)
    assert ports == ["22/tcp", "80/tcp"]


def test_extract_open_ports_none():
    """Test extraction when no ports found."""
    xml_str = "<host><ports></ports></host>"
    host = ET.fromstring(xml_str)
    ports = _extract_open_ports(host)
    assert ports == []


def test_extract_open_ports_mixed_states():
    """Test extraction with mixed port states - only open ports."""
    xml_str = """<host>
        <ports>
            <port protocol="tcp" portid="22">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="23">
                <state state="filtered"/>
            </port>
            <port protocol="tcp" portid="25">
                <state state="closed"/>
            </port>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
        </ports>
    </host>"""

    host = ET.fromstring(xml_str)
    ports = _extract_open_ports(host)

    # Should only include open ports
    assert "22/tcp" in ports
    assert "80/tcp" in ports
    assert "23/tcp" not in ports
    assert "25/tcp" not in ports


def test_parse_nmap_xml_no_open_ports():
    """Test parsing nmap XML with no open ports."""
    logger = MagicMock()
    xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <ports></ports>
    </host>
</nmaprun>"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml_str)
        f.flush()
        xml_file = f.name

    try:
        result = parse_nmap_xml(logger, xml_file)
        assert result == []
        logger.info.assert_called_once()
    finally:
        os.unlink(xml_file)


def test_parse_nmap_xml_with_open_ports():
    """Test parsing nmap XML with open ports."""
    logger = MagicMock()
    xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <hostnames>
            <hostname name="server.local" type="PTR"/>
        </hostnames>
        <ports>
            <port protocol="tcp" portid="22">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
        </ports>
    </host>
</nmaprun>"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml_str)
        f.flush()
        xml_file = f.name

    try:
        result = parse_nmap_xml(logger, xml_file)
        assert len(result) == 1
        assert "server.local(192.168.1.10)" in result[0]
        assert "22/tcp" in result[0]
        assert "80/tcp" in result[0]
    finally:
        os.unlink(xml_file)


def test_parse_nmap_xml_multiple_hosts():
    """Test parsing nmap XML with multiple hosts."""
    logger = MagicMock()
    xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <ports>
            <port protocol="tcp" portid="22">
                <state state="open"/>
            </port>
        </ports>
    </host>
    <host>
        <address addr="192.168.1.20" addrtype="ipv4"/>
        <ports>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
        </ports>
    </host>
</nmaprun>"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml_str)
        f.flush()
        xml_file = f.name

    try:
        result = parse_nmap_xml(logger, xml_file)
        assert len(result) == 2
        assert any("192.168.1.10" in r for r in result)
        assert any("192.168.1.20" in r for r in result)
    finally:
        os.unlink(xml_file)


def test_parse_nmap_xml_invalid_file():
    """Test parsing invalid XML file."""
    logger = MagicMock()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write("invalid xml content")
        f.flush()
        xml_file = f.name

    try:
        result = parse_nmap_xml(logger, xml_file)
        assert result == []
        logger.error.assert_called_once()
    finally:
        os.unlink(xml_file)


# Tests for PortChecker.execute() public method
class TestPortCheckerExecute:
    """Test PortChecker.execute() - the public execution interface."""

    def test_execute_success_no_open_ports(self):
        """Test execute() when scan succeeds and no open ports found."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        xml_content = """<?xml version="1.0"?>
<nmaprun>
    <host starttime="1" endtime="1">
        <status state="up"/>
        <address addr="192.168.1.1" addrtype="ipv4"/>
        <ports></ports>
    </host>
</nmaprun>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=100):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    assert isinstance(result, CheckResult)
                    assert result.status == "up"
                    assert result.message == "No open ports found"
                    assert result.check_name == "portscan"
                    assert result.duration_seconds >= 0
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_success_open_ports_found(self):
        """Test execute() when scan succeeds and open ports are found."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        xml_content = """<?xml version="1.0"?>
<nmaprun>
    <host starttime="1" endtime="1">
        <status state="up"/>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <hostnames>
            <hostname name="server.local" type="PTR"/>
        </hostnames>
        <ports>
            <port protocol="tcp" portid="22">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
        </ports>
    </host>
</nmaprun>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=100):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    assert isinstance(result, CheckResult)
                    assert result.status == "down"
                    assert "Open ports found" in result.message
                    assert result.check_name == "portscan"
                    assert "open_hosts" in result.details
                    assert len(result.details["open_hosts"]) > 0
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_scan_failure(self):
        """Test execute() when nmap scan fails."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        with patch(
            "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
        ) as mock_scan:
            mock_scan.return_value = (False, None)

            result = checker.execute()

            assert isinstance(result, CheckResult)
            assert result.status == "down"
            assert result.message == "Port scan execution failed"
            assert result.check_name == "portscan"
            assert "scan_execution_failed" in result.details.get("error", "")

    def test_execute_empty_xml_file(self):
        """Test execute() when XML file is empty."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        xml_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False
        ).name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=0):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    assert isinstance(result, CheckResult)
                    assert result.status == "up"
                    assert result.message == "No open ports found"
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_nonexistent_xml_file(self):
        """Test execute() when XML file doesn't exist."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        with patch(
            "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
        ) as mock_scan:
            mock_scan.return_value = (True, "/nonexistent/file.xml")

            result = checker.execute()

            assert isinstance(result, CheckResult)
            assert result.status == "up"
            assert result.message == "No open ports found"

    def test_execute_xml_cleanup_when_keep_disabled(self):
        """Test that XML file is removed when keep_xmloutput is False."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        xml_content = """<?xml version="1.0"?>
<nmaprun>
    <host><address addr="192.168.1.1" addrtype="ipv4"/><ports></ports></host>
</nmaprun>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=100):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    # File should be deleted
                    assert not os.path.exists(xml_file)
                    assert result.status == "up"
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_xml_preserved_when_keep_enabled(self):
        """Test that XML file is preserved when keep_xmloutput is True."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = True

        checker = PortChecker(logger, config)

        xml_content = """<?xml version="1.0"?>
<nmaprun>
    <host><address addr="192.168.1.1" addrtype="ipv4"/><ports></ports></host>
</nmaprun>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=100):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    # File should still exist
                    assert os.path.exists(xml_file)
                    assert result.status == "up"
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_exception_handling(self):
        """Test execute() handles exceptions gracefully."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"

        checker = PortChecker(logger, config)

        with patch(
            "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
        ) as mock_scan:
            mock_scan.side_effect = Exception("Unexpected error")

            result = checker.execute()

            assert isinstance(result, CheckResult)
            assert result.status == "down"
            assert "Port scan error" in result.message
            assert "error" in result.details

    def test_execute_multiple_hosts_with_ports(self):
        """Test execute() parsing multiple hosts with different open ports."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_nmap_keep_xmloutput = False

        checker = PortChecker(logger, config)

        xml_content = """<?xml version="1.0"?>
<nmaprun>
    <host starttime="1" endtime="1">
        <status state="up"/>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <hostnames><hostname name="web.local" type="PTR"/></hostnames>
        <ports>
            <port protocol="tcp" portid="80">
                <state state="open"/>
            </port>
            <port protocol="tcp" portid="443">
                <state state="open"/>
            </port>
        </ports>
    </host>
    <host starttime="2" endtime="2">
        <status state="up"/>
        <address addr="192.168.1.20" addrtype="ipv4"/>
        <hostnames><hostname name="db.local" type="PTR"/></hostnames>
        <ports>
            <port protocol="tcp" portid="3306">
                <state state="open"/>
            </port>
        </ports>
    </host>
</nmaprun>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            xml_file = f.name

        try:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._run_nmap_scan"
            ) as mock_scan:
                with patch("os.path.getsize", return_value=100):
                    mock_scan.return_value = (True, xml_file)

                    result = checker.execute()

                    assert result.status == "down"
                    assert "Open ports found" in result.message
                    assert len(result.details["open_hosts"]) == 2
                    assert any(
                        "192.168.1.10" in h for h in result.details["open_hosts"]
                    )
                    assert any(
                        "192.168.1.20" in h for h in result.details["open_hosts"]
                    )
        finally:
            if os.path.exists(xml_file):
                os.unlink(xml_file)

    def test_execute_attributes(self):
        """Test PortChecker class attributes."""
        logger = MagicMock()
        config = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_interval = 60
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"

        checker = PortChecker(logger, config)

        assert checker.name == "portscan"
        assert "TCP ports" in checker.description
        assert checker.logger == logger
        assert checker.config == config
