"""Tests for portscan plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.models import GlobalConfig, LoggingConfig, UptimeKumaConfig
from kuma_scout.plugins.portscan import PortscanConfig, PortscanPlugin


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma=UptimeKumaConfig(
            url="http://localhost:3001/api/push", token="global-token"
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def plugin(global_config):
    """Create portscan plugin instance."""
    return PortscanPlugin(global_config=global_config)


@pytest.fixture
def config():
    """Create basic portscan config."""
    return PortscanConfig(
        name="test-scan",
        targets=["192.168.1.0/24"],
        ports="22,80,443",
    )


class TestPortscanExecution:
    """Test portscan plugin execution."""

    def test_successful_scan(self, plugin, config):
        """Test successful port scan."""
        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse:
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = ["192.168.1.10:22,80"]

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Open ports found" in result.message

    def test_scan_with_closed_ports(self, plugin, config):
        """Test scan with some closed ports."""
        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse:
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = ["192.168.1.10:22"]

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Open ports found" in result.message

    def test_scan_failure(self, plugin, config):
        """Test scan failure."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", "Nmap failed", 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Port scan execution failed" in result.message

    def test_no_open_ports(self, plugin, config):
        """Test scan with no open ports."""
        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse:
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = []

            result = plugin.execute(config)

            assert result.status == "up"
            assert "No open ports found" in result.message


class TestPortscanMethods:
    """Test individual portscan methods."""

    def test_build_nmap_command_basic(self, plugin, config):
        """Test building basic nmap command."""
        cmd = plugin._build_nmap_command(config)

        expected = [
            "nmap",
            "-p",
            "22,80,443",
            "-T3",
        ]
        assert cmd[:4] == expected

    def test_build_nmap_command_with_excludes(self, plugin):
        """Test building nmap command with exclusions."""
        config = PortscanConfig(
            name="test-scan",
            targets=["192.168.1.0/24"],
            ports="22,80,443",
            exclude=["192.168.1.1", "192.168.1.254"],
        )

        cmd = plugin._build_nmap_command(config)
        assert "--exclude" in cmd
        assert "192.168.1.1,192.168.1.254" in cmd

    def test_build_nmap_command_with_arguments(self, plugin):
        """Test building nmap command with additional arguments."""
        config = PortscanConfig(
            name="test-scan",
            targets=["192.168.1.0/24"],
            ports="22,80,443",
            arguments=["-sS", "--script", "banner"],
        )

        cmd = plugin._build_nmap_command(config)
        assert "-sS" in cmd
        assert "--script" in cmd
        assert "banner" in cmd

    @patch("tempfile.mkstemp")
    @patch("os.chmod")
    @patch("os.close")
    def test_create_nmap_xml_file(self, mock_close, mock_chmod, mock_mkstemp, plugin):
        """Test creating temporary XML file."""
        mock_mkstemp.return_value = (3, "/tmp/test.xml")

        result = plugin._create_nmap_xml_file()

        assert result == "/tmp/test.xml"
        mock_chmod.assert_called_once_with("/tmp/test.xml", 0o600)
        mock_close.assert_called_once_with(3)

    def test_parse_nmap_xml_success(self, plugin):
        """Test successful XML parsing."""
        from unittest.mock import Mock

        # Create a mock XML tree
        mock_root = Mock()
        mock_host = Mock()
        mock_root.findall.return_value = [mock_host]

        with patch.object(
            plugin, "_extract_ip", return_value="192.168.1.10"
        ), patch.object(
            plugin, "_extract_hostname", return_value="test.example.com"
        ), patch.object(
            plugin, "_extract_open_ports", return_value=["22/tcp", "80/tcp"]
        ), patch("xml.etree.ElementTree.parse") as mock_parse:
            mock_tree = Mock()
            mock_tree.getroot.return_value = mock_root
            mock_parse.return_value = mock_tree

            result = plugin._parse_nmap_xml("/tmp/test.xml")

            expected = ["test.example.com:22/tcp,80/tcp"]
            assert result == expected

    def test_parse_nmap_xml_error(self, plugin):
        """Test XML parsing error."""
        with patch(
            "kuma_scout.plugins.portscan.ET.parse", side_effect=Exception("Parse error")
        ):
            result = plugin._parse_nmap_xml("/tmp/test.xml")

            assert result == []

    def test_extract_ip(self, plugin):
        """Test IP extraction."""
        from unittest.mock import Mock

        # Mock element
        class MockElement:
            def findall(self, path):
                if path == ".//address[@addrtype='ipv4']":
                    mock_addr = Mock()
                    mock_addr.get.return_value = "192.168.1.10"
                    return [mock_addr]
                return []

        result = plugin._extract_ip(MockElement())
        assert result == "192.168.1.10"

    def test_extract_hostname(self, plugin):
        """Test hostname extraction."""
        from unittest.mock import Mock

        # Mock element
        class MockElement:
            def findall(self, path):
                if path == ".//hostname[@type='PTR']":
                    mock_hostname = Mock()
                    mock_hostname.get.return_value = "test.example.com"
                    return [mock_hostname]
                return []

        result = plugin._extract_hostname(MockElement())
        assert result == "test.example.com"

    def test_extract_open_ports(self, plugin):
        """Test open ports extraction."""
        from unittest.mock import Mock

        # Mock element
        class MockElement:
            def findall(self, path):
                if path == ".//port[@protocol='tcp']":
                    # Mock two ports, one open one closed
                    mock_port1 = Mock()
                    mock_port1.get.return_value = "22"
                    mock_state1 = Mock()
                    mock_state1.get.return_value = "open"
                    mock_port1.find.return_value = mock_state1

                    mock_port2 = Mock()
                    mock_port2.get.return_value = "80"
                    mock_state2 = Mock()
                    mock_state2.get.return_value = "closed"
                    mock_port2.find.return_value = mock_state2

                    return [mock_port1, mock_port2]
                return []

        result = plugin._extract_open_ports(MockElement())
        assert result == ["22/tcp"]

    @patch("kuma_scout.plugins.portscan.os.path.exists")
    @patch("kuma_scout.plugins.portscan.os.remove")
    def test_cleanup_success(self, mock_remove, mock_exists, plugin, config):
        """Test successful cleanup."""
        mock_exists.return_value = True

        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse, patch.object(plugin, "_create_nmap_xml_file") as mock_create:
            mock_create.return_value = "/tmp/test.xml"
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = []

            plugin.execute(config)

            mock_remove.assert_called_once_with("/tmp/test.xml")

    @patch("kuma_scout.plugins.portscan.os.path.exists")
    @patch(
        "kuma_scout.plugins.portscan.os.remove", side_effect=OSError("Remove failed")
    )
    def test_cleanup_failure(self, mock_remove, mock_exists, plugin, config):
        """Test cleanup failure."""
        mock_exists.return_value = True

        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse, patch.object(plugin, "_create_nmap_xml_file") as mock_create:
            mock_create.return_value = "/tmp/test.xml"
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = []

            result = plugin.execute(config)

            # Should still succeed despite cleanup failure
            assert result.status == "up"
