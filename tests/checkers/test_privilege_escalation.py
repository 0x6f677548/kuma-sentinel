"""Tests for privilege escalation protection (Issue #11)."""

import logging
from unittest.mock import MagicMock

import pytest

from kuma_sentinel.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig


class TestPrivilegeEscalationProtection:
    """Tests for dangerous command pattern detection."""

    @pytest.fixture
    def setup_checker(self):
        """Setup a checker with mocked logger and config."""
        logger = MagicMock(spec=logging.Logger)
        config = CmdCheckConfig()
        config.logger = MagicMock()
        config.cmdcheck_commands = [{"command": "echo test", "name": "test"}]
        # Disable heartbeat to avoid initialization warnings in tests
        config.heartbeat_enabled = False
        return logger, config

    def test_systemctl_start_pattern_detected(self, setup_checker):
        """Test that systemctl start commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("sudo systemctl start nginx", "nginx_start")

        logger.warning.assert_called_once()
        call_args = str(logger.warning.call_args)
        assert "systemctl" in call_args.lower()
        assert "start" in call_args.lower()
        assert "system state" in call_args.lower()

    def test_systemctl_stop_pattern_detected(self, setup_checker):
        """Test that systemctl stop commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl stop redis", "redis_stop")

        logger.warning.assert_called_once()
        call_args = str(logger.warning.call_args)
        assert "systemctl" in call_args.lower()
        assert "stop" in call_args.lower()

    def test_systemctl_restart_pattern_detected(self, setup_checker):
        """Test that systemctl restart commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl restart postgres", "pg_restart")

        logger.warning.assert_called_once()
        assert "restart" in str(logger.warning.call_args).lower()

    def test_systemctl_reload_pattern_detected(self, setup_checker):
        """Test that systemctl reload commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl reload apache2", "apache_reload")

        logger.warning.assert_called_once()
        assert "reload" in str(logger.warning.call_args).lower()

    def test_systemctl_enable_pattern_detected(self, setup_checker):
        """Test that systemctl enable commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl enable docker", "docker_enable")

        logger.warning.assert_called_once()
        assert "enable" in str(logger.warning.call_args).lower()

    def test_systemctl_disable_pattern_detected(self, setup_checker):
        """Test that systemctl disable commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl disable bluetooth", "bt_disable")

        logger.warning.assert_called_once()
        assert "disable" in str(logger.warning.call_args).lower()

    def test_zpool_create_pattern_detected(self, setup_checker):
        """Test that zpool create commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zpool create tank /dev/sda", "pool_create")

        logger.warning.assert_called_once()
        call_args = str(logger.warning.call_args)
        assert "zpool" in call_args.lower()
        assert "create" in call_args.lower()
        assert "zfs pool" in call_args.lower()

    def test_zpool_destroy_pattern_detected(self, setup_checker):
        """Test that zpool destroy commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zpool destroy tank", "pool_destroy")

        logger.warning.assert_called_once()
        assert "destroy" in str(logger.warning.call_args).lower()

    def test_zpool_clear_pattern_detected(self, setup_checker):
        """Test that zpool clear commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zpool clear tank", "pool_clear")

        logger.warning.assert_called_once()
        assert "clear" in str(logger.warning.call_args).lower()

    def test_zfs_set_pattern_detected(self, setup_checker):
        """Test that zfs set commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns(
            "zfs set compression=lz4 tank/home", "zfs_compression"
        )

        logger.warning.assert_called_once()
        call_args = str(logger.warning.call_args)
        assert "zfs" in call_args.lower()
        assert "dataset" in call_args.lower()

    def test_zfs_create_pattern_detected(self, setup_checker):
        """Test that zfs create commands generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zfs create tank/backup", "zfs_create")

        logger.warning.assert_called_once()
        assert "create" in str(logger.warning.call_args).lower()

    def test_case_insensitive_detection(self, setup_checker):
        """Test that pattern detection is case-insensitive."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("SYSTEMCTL START NGINX", "nginx_upper")

        logger.warning.assert_called_once()
        assert "systemctl" in str(logger.warning.call_args).lower()

    def test_safe_systemctl_status_no_warning(self, setup_checker):
        """Test that safe systemctl status commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("systemctl status nginx", "nginx_status")

        logger.warning.assert_not_called()

    def test_safe_systemctl_show_no_warning(self, setup_checker):
        """Test that safe systemctl show commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns(
            "systemctl show -p ActiveState nginx", "nginx_show"
        )

        logger.warning.assert_not_called()

    def test_safe_zpool_status_no_warning(self, setup_checker):
        """Test that safe zpool status commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zpool status tank", "pool_status")

        logger.warning.assert_not_called()

    def test_safe_zpool_list_no_warning(self, setup_checker):
        """Test that safe zpool list commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zpool list", "pool_list")

        logger.warning.assert_not_called()

    def test_safe_zfs_list_no_warning(self, setup_checker):
        """Test that safe zfs list commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zfs list -t filesystem", "zfs_list")

        logger.warning.assert_not_called()

    def test_safe_zfs_get_no_warning(self, setup_checker):
        """Test that safe zfs get commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("zfs get quota tank/home", "zfs_quota")

        logger.warning.assert_not_called()

    def test_generic_command_no_warning(self, setup_checker):
        """Test that generic commands don't generate warnings."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns("curl https://example.com", "check_web")

        logger.warning.assert_not_called()

    def test_multiple_dangerous_args_warns_once(self, setup_checker):
        """Test that only the first dangerous pattern triggers a warning."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        # Command with multiple dangerous keywords - should warn once
        checker._check_dangerous_patterns(
            "systemctl start && systemctl stop", "multi_cmd"
        )

        # Should only warn once (for the first match)
        logger.warning.assert_called_once()

    def test_warning_includes_command_name(self, setup_checker):
        """Test that warning message includes the command name."""
        logger, config = setup_checker
        checker = CmdCheckChecker(logger, config)

        checker._check_dangerous_patterns(
            "systemctl restart myservice", "my_custom_name"
        )

        logger.warning.assert_called_once()
        call_args = str(logger.warning.call_args)
        assert "my_custom_name" in call_args
