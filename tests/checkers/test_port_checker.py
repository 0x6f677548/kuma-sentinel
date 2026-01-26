"""Tests for port checker module."""

import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from kuma_sentinel.core.checkers.port_checker import (
    PortChecker,
    _build_nmap_command,
    _create_nmap_xml_file,
    _extract_host_ip,
    _extract_hostname,
    _extract_open_ports,
    _run_nmap_process,
    _run_nmap_scan,
    parse_nmap_xml,
)
from kuma_sentinel.core.config.portscan_config import PortscanConfig
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
                    assert result.message == "[portscan] ✓ No open ports found"
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
            assert result.message == "[portscan] ✗ Port scan execution failed"
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
                    assert result.message == "[portscan] ✓ No open ports found"
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
            assert result.message == "[portscan] ✓ No open ports found"

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


# Tests for _build_nmap_command function
class TestBuildNmapCommand:
    """Tests for _build_nmap_command function."""

    def test_build_nmap_command_basic(self):
        """Test building basic nmap command."""
        config = MagicMock(spec=PortscanConfig)
        config.portscan_nmap_ports = "22,80,443"
        config.portscan_nmap_timing = "T3"

        cmd = _build_nmap_command(config)

        assert "nmap" in cmd
        assert "-p" in cmd
        assert "22,80,443" in cmd
        assert "-T3" in cmd
        assert "-oX" in cmd

    def test_build_nmap_command_different_timing(self):
        """Test building command with different timing options."""
        config = MagicMock(spec=PortscanConfig)
        config.portscan_nmap_ports = "1-65535"
        config.portscan_nmap_timing = "T4"

        cmd = _build_nmap_command(config)

        assert "-T4" in cmd
        assert "1-65535" in cmd

    def test_build_nmap_command_aggressive_timing(self):
        """Test building command with aggressive timing."""
        config = MagicMock(spec=PortscanConfig)
        config.portscan_nmap_ports = "80"
        config.portscan_nmap_timing = "T5"

        cmd = _build_nmap_command(config)

        assert "-T5" in cmd


# Tests for _create_nmap_xml_file function
class TestCreateNmapXmlFile:
    """Tests for _create_nmap_xml_file function."""

    def test_create_nmap_xml_file_creates_file(self):
        """Test that file is created and path is returned."""
        xml_path = _create_nmap_xml_file()

        try:
            assert os.path.exists(xml_path)
            assert xml_path.endswith(".xml")
        finally:
            if os.path.exists(xml_path):
                os.unlink(xml_path)

    def test_create_nmap_xml_file_returns_writable_path(self):
        """Test that returned path can be written to."""
        xml_path = _create_nmap_xml_file()

        try:
            with open(xml_path, "w") as f:
                f.write("test content")

            with open(xml_path) as f:
                content = f.read()

            assert content == "test content"
        finally:
            if os.path.exists(xml_path):
                os.unlink(xml_path)

    def test_create_nmap_xml_file_unique_paths(self):
        """Test that multiple calls create unique paths."""
        xml_path1 = _create_nmap_xml_file()
        xml_path2 = _create_nmap_xml_file()

        try:
            assert xml_path1 != xml_path2
            assert os.path.exists(xml_path1)
            assert os.path.exists(xml_path2)
        finally:
            for path in [xml_path1, xml_path2]:
                if os.path.exists(path):
                    os.unlink(path)


# Tests for _run_nmap_process function
class TestRunNmapProcess:
    """Tests for _run_nmap_process function."""

    def test_run_nmap_process_success(self):
        """Test successful nmap process execution."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="nmap output", stderr=""
            )

            success, stderr = _run_nmap_process(logger, ["nmap", "-h"], 30)

            assert success is True
            assert stderr is None
            mock_run.assert_called_once()

    def test_run_nmap_process_failure(self):
        """Test failed nmap process execution."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error message"
            )

            success, stderr = _run_nmap_process(logger, ["nmap", "-h"], 30)

            assert success is False
            assert stderr == "Error message"
            logger.error.assert_called()

    def test_run_nmap_process_timeout(self):
        """Test timeout during nmap process execution."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("nmap", 30)

            success, stderr = _run_nmap_process(logger, ["nmap", "-h"], 30)

            assert success is False
            assert stderr is None
            logger.error.assert_called_with("❌ Nmap scan timed out")

    def test_run_nmap_process_logs_stdout(self):
        """Test that stdout is logged when nmap succeeds."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="line1\nline2\nline3", stderr=""
            )

            success, stderr = _run_nmap_process(logger, ["nmap", "-h"], 30)

            assert success is True
            # Verify info was logged for output
            assert logger.info.called

    def test_run_nmap_process_handles_no_stdout(self):
        """Test handling of empty stdout."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, stderr = _run_nmap_process(logger, ["nmap", "-h"], 30)

            assert success is True
            assert stderr is None

    def test_run_nmap_process_timeout_value_used(self):
        """Test that timeout value is passed to subprocess.run."""
        logger = MagicMock()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            _run_nmap_process(logger, ["nmap", "-h"], 60)

            # Verify timeout was passed
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 60


# Tests for _run_nmap_scan function
class TestRunNmapScan:
    """Tests for _run_nmap_scan function."""

    def test_run_nmap_scan_with_exclude_hosts(self):
        """Test nmap scan with excluded hosts."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = ["192.168.1.1", "192.168.1.2"]
        config.portscan_nmap_arguments = []
        config.portscan_ip_ranges = ["192.168.0.0/24"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap", "-p", "80,443"]
                    mock_run.return_value = (True, None)

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is True
                    assert xml_path == "/tmp/nmap.xml"
                    # Verify exclude hosts were added to command
                    call_args = mock_run.call_args[0][1]
                    assert "--exclude" in call_args

    def test_run_nmap_scan_with_nmap_arguments(self):
        """Test nmap scan with additional nmap arguments."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = ["-sS", "-A"]
        config.portscan_ip_ranges = ["10.0.0.0/8"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap", "-p", "22"]
                    mock_run.return_value = (True, None)

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is True
                    # Verify nmap arguments were added
                    call_args = mock_run.call_args[0][1]
                    assert "-sS" in call_args
                    assert "-A" in call_args

    def test_run_nmap_scan_with_multiple_ip_ranges(self):
        """Test nmap scan with multiple IP ranges."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = []
        config.portscan_ip_ranges = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap"]
                    mock_run.return_value = (True, None)

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is True
                    # Verify all IP ranges were added
                    call_args = mock_run.call_args[0][1]
                    assert "10.0.0.0/8" in call_args
                    assert "172.16.0.0/12" in call_args
                    assert "192.168.0.0/16" in call_args

    def test_run_nmap_scan_failure(self):
        """Test nmap scan failure."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = []
        config.portscan_ip_ranges = ["192.168.0.0/24"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap"]
                    mock_run.return_value = (False, "Permission denied")

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is False

    def test_run_nmap_scan_exception_handling(self):
        """Test exception handling in nmap scan."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            mock_create.side_effect = Exception("File creation error")

            success, xml_path = _run_nmap_scan(logger, config)

            assert success is False
            assert xml_path is None
            logger.error.assert_called()

    def test_run_nmap_scan_none_arguments(self):
        """Test nmap scan when nmap_arguments is None."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = None  # None instead of list
        config.portscan_ip_ranges = ["192.168.0.0/24"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap"]
                    mock_run.return_value = (True, None)

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is True

    def test_run_nmap_scan_none_ip_ranges(self):
        """Test nmap scan when ip_ranges is None."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = []
        config.portscan_ip_ranges = None  # None instead of list
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap"]
                    mock_run.return_value = (True, None)

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is True

    def test_run_nmap_scan_error_with_stderr(self):
        """Test nmap scan error logging with stderr message."""
        logger = MagicMock()
        config = MagicMock(spec=PortscanConfig)
        config.portscan_exclude = []
        config.portscan_nmap_arguments = []
        config.portscan_ip_ranges = ["192.168.0.0/24"]
        config.portscan_nmap_timeout = 300

        with patch(
            "kuma_sentinel.core.checkers.port_checker._create_nmap_xml_file"
        ) as mock_create:
            with patch(
                "kuma_sentinel.core.checkers.port_checker._build_nmap_command"
            ) as mock_build:
                with patch(
                    "kuma_sentinel.core.checkers.port_checker._run_nmap_process"
                ) as mock_run:
                    mock_create.return_value = "/tmp/nmap.xml"
                    mock_build.return_value = ["nmap"]
                    mock_run.return_value = (False, "Nmap error details")

                    success, xml_path = _run_nmap_scan(logger, config)

                    assert success is False
                    # Verify error was logged
                    logger.error.assert_called()


# Tests for parse_nmap_xml edge cases
class TestParseNmapXmlEdgeCases:
    """Additional edge case tests for parse_nmap_xml."""

    def test_parse_nmap_xml_host_without_ip(self):
        """Test parsing XML with host element missing IP."""
        logger = MagicMock()
        xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <ports>
            <port protocol="tcp" portid="22">
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
            # Host without IP should be skipped
            assert result == []
        finally:
            os.unlink(xml_file)

    def test_parse_nmap_xml_ipv6_ignored(self):
        """Test that IPv6 addresses are not included (only IPv4)."""
        logger = MagicMock()
        xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <address addr="::1" addrtype="ipv6"/>
        <address addr="127.0.0.1" addrtype="ipv4"/>
        <ports>
            <port protocol="tcp" portid="22">
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
            assert "127.0.0.1" in result[0]
        finally:
            os.unlink(xml_file)

    def test_parse_nmap_xml_file_not_found(self):
        """Test parsing non-existent XML file."""
        logger = MagicMock()

        result = parse_nmap_xml(logger, "/nonexistent/file.xml")

        assert result == []
        logger.error.assert_called()

    def test_parse_nmap_xml_hostname_without_name_attribute(self):
        """Test hostname extraction when name attribute is empty."""
        logger = MagicMock()
        xml_str = """<?xml version="1.0"?>
<nmaprun>
    <host>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <hostnames>
            <hostname name="" type="PTR"/>
        </hostnames>
        <ports>
            <port protocol="tcp" portid="22">
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
            # Should use IP only since hostname is empty
            assert "192.168.1.10:22/tcp" in result
        finally:
            os.unlink(xml_file)


class TestCheckerBaseClass:
    """Test base Checker class functionality through PortChecker."""

    def test_checker_init_missing_name(self):
        """Test Checker initialization fails without name."""
        from kuma_sentinel.core.checkers.base import Checker
        from kuma_sentinel.core.config.base import ConfigBase

        class BrokenChecker(Checker):
            description = "test"

            def execute(self):
                pass

        logger = MagicMock()
        config = MagicMock(spec=ConfigBase)

        with patch.object(BrokenChecker, "name", ""):
            with pytest.raises(ValueError, match="must define 'name'"):
                BrokenChecker(logger, config)

    def test_checker_init_missing_description(self):
        """Test Checker initialization fails without description."""
        from kuma_sentinel.core.checkers.base import Checker
        from kuma_sentinel.core.config.base import ConfigBase

        class BrokenChecker(Checker):
            name = "test"

            def execute(self):
                pass

        logger = MagicMock()
        config = MagicMock(spec=ConfigBase)

        with patch.object(BrokenChecker, "description", ""):
            with pytest.raises(ValueError, match="must define 'description'"):
                BrokenChecker(logger, config)

    def test_initialize_heartbeat_disabled(self):
        """Test heartbeat initialization when heartbeat is disabled."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = False
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"

        checker = PortChecker(logger, config)
        assert checker.heartbeat is None

    def test_initialize_heartbeat_missing_token(self):
        """Test heartbeat initialization when token is missing."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = None
        config.uptime_kuma_url = "http://localhost"

        checker = PortChecker(logger, config)
        assert checker.heartbeat is None

    def test_initialize_heartbeat_missing_url(self):
        """Test heartbeat initialization when URL is missing."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = None

        checker = PortChecker(logger, config)
        assert checker.heartbeat is None

    def test_initialize_heartbeat_string_enabled_true(self):
        """Test heartbeat initialization with string 'true' for enabled."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True  # Boolean value
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch("kuma_sentinel.core.checkers.base.HeartbeatService"):
            checker = PortChecker(logger, config)
            # Should initialize heartbeat because "true" string is recognized
            assert checker.heartbeat is not None

    def test_initialize_heartbeat_string_enabled_false(self):
        """Test heartbeat initialization with string 'false' for enabled."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = False  # Boolean value
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        checker = PortChecker(logger, config)
        assert checker.heartbeat is None

    def test_initialize_heartbeat_all_configured(self):
        """Test successful heartbeat initialization with all required config."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "test_token"
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch("kuma_sentinel.core.checkers.base.HeartbeatService") as mock_hb:
            checker = PortChecker(logger, config)
            assert checker.heartbeat is not None
            # Verify HeartbeatService was instantiated with correct parameters
            mock_hb.assert_called_once()
            call_kwargs = mock_hb.call_args[1]
            assert call_kwargs["check_name"] == "portscan"

    def test_execute_with_heartbeat_success(self):
        """Test execute_with_heartbeat on successful check execution."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch(
            "kuma_sentinel.core.checkers.base.HeartbeatService"
        ) as mock_hb_class:
            mock_heartbeat = MagicMock()
            mock_hb_class.return_value = mock_heartbeat

            checker = PortChecker(logger, config)

            # Mock the execute method to return a result
            with patch.object(checker, "execute") as mock_execute:
                result = CheckResult(
                    check_name="portscan",
                    status="up",
                    message="Test success",
                    duration_seconds=1,
                )
                mock_execute.return_value = result

                # Call execute_with_heartbeat
                returned_result = checker.execute_with_heartbeat()

                # Verify heartbeat was called
                assert (
                    mock_heartbeat.send_message.call_count >= 2
                )  # Start and end messages
                mock_heartbeat.start.assert_called_once()
                mock_heartbeat.stop.assert_called_once()
                assert returned_result == result

    def test_execute_with_heartbeat_no_heartbeat(self):
        """Test execute_with_heartbeat when heartbeat is not configured."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = False
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        checker = PortChecker(logger, config)
        assert checker.heartbeat is None

        # Mock execute method
        with patch.object(checker, "execute") as mock_execute:
            result = CheckResult(
                check_name="portscan",
                status="up",
                message="Test",
                duration_seconds=1,
            )
            mock_execute.return_value = result

            returned_result = checker.execute_with_heartbeat()
            assert returned_result == result

    def test_execute_with_heartbeat_timeout_error(self):
        """Test execute_with_heartbeat handles TimeoutError."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch(
            "kuma_sentinel.core.checkers.base.HeartbeatService"
        ) as mock_hb_class:
            mock_heartbeat = MagicMock()
            mock_hb_class.return_value = mock_heartbeat

            checker = PortChecker(logger, config)

            # Mock execute to raise TimeoutError
            with patch.object(checker, "execute") as mock_execute:
                mock_execute.side_effect = TimeoutError("Execution timeout")

                import pytest

                with pytest.raises(TimeoutError):
                    checker.execute_with_heartbeat()

                # Verify heartbeat stop was still called (in finally block)
                mock_heartbeat.stop.assert_called_once()
                # Verify error was logged
                assert logger.error.called

    def test_execute_with_heartbeat_general_exception(self):
        """Test execute_with_heartbeat handles general exceptions."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch(
            "kuma_sentinel.core.checkers.base.HeartbeatService"
        ) as mock_hb_class:
            mock_heartbeat = MagicMock()
            mock_hb_class.return_value = mock_heartbeat

            checker = PortChecker(logger, config)

            # Mock execute to raise Exception
            with patch.object(checker, "execute") as mock_execute:
                mock_execute.side_effect = RuntimeError("Unexpected error")

                import pytest

                with pytest.raises(RuntimeError):
                    checker.execute_with_heartbeat()

                # Verify heartbeat stop was still called (in finally block)
                mock_heartbeat.stop.assert_called_once()
                # Verify error was logged
                assert logger.error.called

    def test_execute_with_heartbeat_down_status(self):
        """Test execute_with_heartbeat with DOWN status result."""
        logger = MagicMock()
        config = PortscanConfig()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://localhost"
        config.heartbeat_interval = 300
        config.portscan_ip_ranges = ["192.168.1.0/24"]

        with patch(
            "kuma_sentinel.core.checkers.base.HeartbeatService"
        ) as mock_hb_class:
            mock_heartbeat = MagicMock()
            mock_hb_class.return_value = mock_heartbeat

            checker = PortChecker(logger, config)

            # Mock execute method to return DOWN status
            with patch.object(checker, "execute") as mock_execute:
                result = CheckResult(
                    check_name="portscan",
                    status="down",
                    message="Check failed",
                    duration_seconds=2,
                )
                mock_execute.return_value = result

                checker.execute_with_heartbeat()

                # Verify heartbeat was called with DOWN emoji
                assert mock_heartbeat.send_message.called
                # Check that end message contains the DOWN emoji
                calls = mock_heartbeat.send_message.call_args_list
                end_message = calls[-1][0][0]  # Last message sent
                assert "❌" in end_message or "down" in end_message.lower()
