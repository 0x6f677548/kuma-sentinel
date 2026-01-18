"""Tests for port checker module."""

import os
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

from kuma_sentinel.core.checkers.port_checker import (
    _extract_host_ip,
    _extract_hostname,
    _extract_open_ports,
    parse_nmap_xml,
)


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
