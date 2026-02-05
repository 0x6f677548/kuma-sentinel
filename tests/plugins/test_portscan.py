"""Tests for portscan plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.models import GlobalConfig
from kuma_scout.plugins.portscan import PortscanConfig, PortscanPlugin


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma={"url": "http://localhost:3001/api/push", "token": "global-token"},
        logging={"level": "INFO"},
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
            assert "2 open ports found" in result.message

    def test_scan_with_closed_ports(self, plugin, config):
        """Test scan with some closed ports."""
        with patch.object(plugin, "run_command") as mock_run, patch.object(
            plugin, "_parse_nmap_xml"
        ) as mock_parse:
            mock_run.return_value = (True, "", "", 0)
            mock_parse.return_value = ["192.168.1.10:22"]

            result = plugin.execute(config)

            assert result.status == "down"
            assert "1 open ports found" in result.message

    def test_scan_failure(self, plugin, config):
        """Test scan failure."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", "Nmap failed", 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Port scan failed" in result.message

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
