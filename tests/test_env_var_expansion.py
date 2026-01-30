"""Tests for environment variable expansion in YAML configuration."""

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml

from kuma_scout.core.config.base import ConfigBase, FieldMapping
from kuma_scout.core.config.cmdcheck_config import CmdCheckConfig
from kuma_scout.core.config.kopia_snapshot_config import KopiaSnapshotConfig
from kuma_scout.core.config.portscan_config import PortscanConfig
from kuma_scout.core.config.zfs_pool_config import ZfsPoolStatusConfig


class TestEnvVarExpansion:
    """Test environment variable expansion in YAML configuration."""

    def test_field_mapping_expand_env_vars_flag(self):
        """Test that FieldMapping accepts expand_env_vars parameter."""
        mapping = FieldMapping(yaml_path="test.path", expand_env_vars=True)
        assert mapping.expand_env_vars is True

        mapping_default = FieldMapping(yaml_path="test.path")
        assert mapping_default.expand_env_vars is False

    def test_convert_value_string_expansion(self):
        """Test environment variable expansion for string values."""
        with patch.dict(os.environ, {"TEST_VAR": "expanded_value"}):
            mapping = FieldMapping(expand_env_vars=True)
            result = ConfigBase._convert_value("${TEST_VAR}", mapping)
            assert result == "expanded_value"

    def test_convert_value_string_no_expansion_when_disabled(self):
        """Test that expansion is not performed when expand_env_vars is False."""
        with patch.dict(os.environ, {"TEST_VAR": "expanded_value"}):
            mapping = FieldMapping(expand_env_vars=False)
            result = ConfigBase._convert_value("${TEST_VAR}", mapping)
            assert result == "${TEST_VAR}"

    def test_convert_value_missing_env_var_raises_error(self):
        """Test that missing environment variables raise ValueError."""
        mapping = FieldMapping(expand_env_vars=True)
        with pytest.raises(ValueError, match="Environment variable expansion failed"):
            ConfigBase._convert_value("${MISSING_VAR}", mapping)

    def test_convert_value_dict_expansion(self):
        """Test environment variable expansion in nested dictionaries."""
        with patch.dict(
            os.environ, {"TOKEN_VAR": "secret_token", "URL_VAR": "http://example.com"}
        ):
            mapping = FieldMapping(expand_env_vars=True)
            data = {"token": "${TOKEN_VAR}", "url": "${URL_VAR}", "plain": "unchanged"}
            result = ConfigBase._convert_value(data, mapping)
            expected = {
                "token": "secret_token",
                "url": "http://example.com",
                "plain": "unchanged",
            }
            assert result == expected

    def test_convert_value_list_expansion(self):
        """Test environment variable expansion in lists."""
        with patch.dict(os.environ, {"ITEM1": "value1", "ITEM2": "value2"}):
            mapping = FieldMapping(expand_env_vars=True)
            data = ["${ITEM1}", "${ITEM2}", "plain"]
            result = ConfigBase._convert_value(data, mapping)
            expected = ["value1", "value2", "plain"]
            assert result == expected

    def test_convert_value_nested_structures(self):
        """Test environment variable expansion in complex nested structures."""
        with patch.dict(os.environ, {"TOKEN": "abc123", "NAME": "test"}):
            mapping = FieldMapping(expand_env_vars=True)
            data = {
                "commands": [{"name": "${NAME}", "uptime_kuma": {"token": "${TOKEN}"}}]
            }
            result = ConfigBase._convert_value(data, mapping)
            expected = {
                "commands": [{"name": "test", "uptime_kuma": {"token": "abc123"}}]
            }
            assert result == expected

    def test_convert_value_missing_var_in_nested_structure(self):
        """Test that missing vars in nested structures raise errors."""
        mapping = FieldMapping(expand_env_vars=True)
        data = {"token": "${MISSING_VAR}"}
        with pytest.raises(ValueError, match="Environment variable expansion failed"):
            ConfigBase._convert_value(data, mapping)


class TestCmdCheckConfigEnvVarExpansion:
    """Test environment variable expansion in cmdcheck configuration."""

    def test_cmdcheck_global_token_expansion(self):
        """Test global token expansion in cmdcheck config."""
        with patch.dict(os.environ, {"CMDCHECK_TOKEN": "global_token_value"}):
            config = CmdCheckConfig()
            config_data = {
                "cmdcheck": {
                    "uptime_kuma": {"token": "${CMDCHECK_TOKEN}"},
                    "commands": [{"command": "echo test"}],
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "global_token_value"
            finally:
                os.unlink(config_file)

    def test_cmdcheck_per_command_token_expansion(self):
        """Test per-command token expansion in cmdcheck config."""
        with patch.dict(os.environ, {"CMD1_TOKEN": "token1", "CMD2_TOKEN": "token2"}):
            config = CmdCheckConfig()
            config_data = {
                "cmdcheck": {
                    "commands": [
                        {
                            "command": "echo test1",
                            "uptime_kuma": {"token": "${CMD1_TOKEN}"},
                        },
                        {
                            "command": "echo test2",
                            "uptime_kuma": {"token": "${CMD2_TOKEN}"},
                        },
                    ]
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                commands = config.cmdcheck_commands
                assert len(commands) == 2
                assert commands[0]["uptime_kuma"]["token"] == "token1"
                assert commands[1]["uptime_kuma"]["token"] == "token2"
            finally:
                os.unlink(config_file)

    def test_cmdcheck_mixed_tokens(self):
        """Test mix of expanded and plain tokens in cmdcheck config."""
        with patch.dict(os.environ, {"EXPANDED_TOKEN": "expanded_value"}):
            config = CmdCheckConfig()
            config_data = {
                "cmdcheck": {
                    "uptime_kuma": {"token": "${EXPANDED_TOKEN}"},
                    "commands": [
                        {
                            "command": "echo test1",
                            "uptime_kuma": {"token": "plain_token"},
                        }
                    ],
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "expanded_value"
                commands = config.cmdcheck_commands
                assert commands[0]["uptime_kuma"]["token"] == "plain_token"
            finally:
                os.unlink(config_file)


class TestOtherCommandsEnvVarExpansion:
    """Test environment variable expansion in other command configurations."""

    def test_portscan_token_expansion(self):
        """Test token expansion in portscan config."""
        with patch.dict(os.environ, {"PORTSCAN_TOKEN": "portscan_value"}):
            config = PortscanConfig()
            config_data = {
                "portscan": {
                    "uptime_kuma": {"token": "${PORTSCAN_TOKEN}"},
                    "ip_ranges": ["192.168.1.0/24"],
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "portscan_value"
            finally:
                os.unlink(config_file)

    def test_kopia_token_expansion(self):
        """Test token expansion in kopia config."""
        with patch.dict(os.environ, {"KOPIA_TOKEN": "kopia_value"}):
            config = KopiaSnapshotConfig()
            config_data = {
                "kopiasnapshotstatus": {
                    "uptime_kuma": {"token": "${KOPIA_TOKEN}"},
                    "snapshots": [{"path": "/data"}],
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "kopia_value"
            finally:
                os.unlink(config_file)

    def test_zfs_token_expansion(self):
        """Test token expansion in ZFS config."""
        with patch.dict(os.environ, {"ZFS_TOKEN": "zfs_value"}):
            config = ZfsPoolStatusConfig()
            config_data = {
                "zfspoolstatus": {
                    "uptime_kuma": {"token": "${ZFS_TOKEN}"},
                    "pools": [{"name": "tank"}],
                }
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "zfs_value"
            finally:
                os.unlink(config_file)

    def test_heartbeat_token_expansion(self):
        """Test token expansion in heartbeat config."""
        with patch.dict(os.environ, {"HEARTBEAT_TOKEN": "heartbeat_value"}):
            config = CmdCheckConfig()  # Any config class inherits from ConfigBase
            config_data = {
                "heartbeat": {"uptime_kuma": {"token": "${HEARTBEAT_TOKEN}"}}
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.heartbeat_token == "heartbeat_value"
            finally:
                os.unlink(config_file)


class TestErrorHandling:
    """Test error handling for environment variable expansion."""

    def test_missing_env_var_in_cmdcheck_global_token(self):
        """Test error when global token references missing env var."""
        config = CmdCheckConfig()
        config_data = {
            "cmdcheck": {
                "uptime_kuma": {"token": "${MISSING_TOKEN}"},
                "commands": [{"command": "echo test"}],
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(
                RuntimeError, match="Environment variable expansion failed"
            ):
                config.load_from_yaml(config_file)
        finally:
            os.unlink(config_file)

    def test_missing_env_var_in_per_command_token(self):
        """Test error when per-command token references missing env var."""
        config = CmdCheckConfig()
        config_data = {
            "cmdcheck": {
                "commands": [
                    {
                        "command": "echo test",
                        "uptime_kuma": {"token": "${MISSING_TOKEN}"},
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(
                RuntimeError, match="Environment variable expansion failed"
            ):
                config.load_from_yaml(config_file)
        finally:
            os.unlink(config_file)


class TestCmdCheckCommandSecurity:
    """Test that cmdcheck commands allow environment variables as-is (not expanded, not rejected)."""

    def test_cmdcheck_commands_allow_env_vars_as_is(self):
        """Test that commands with env vars in YAML are kept as-is (not expanded, not rejected)."""
        with patch.dict(os.environ, {"MALICIOUS_VAR": "injected_command"}):
            config = CmdCheckConfig()
            config_data = {
                "uptime_kuma": {"url": "http://test.com"},
                "heartbeat": {"uptime_kuma": {"token": "heartbeat_token"}},
                "cmdcheck": {
                    "commands": [{"command": "echo ${MALICIOUS_VAR}"}],
                    "uptime_kuma": {"token": "cmd_token"},
                },
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                # Loading should succeed (env vars not expanded in commands)
                config.load_from_yaml(config_file)

                # Command should remain as-is with literal ${MALICIOUS_VAR}
                assert config.cmdcheck_commands[0]["command"] == "echo ${MALICIOUS_VAR}"

                # Validation should succeed
                config.validate()

            finally:
                os.unlink(config_file)

    def test_cmdcheck_commands_allow_env_vars_in_tokens(self):
        """Test that tokens with env vars in YAML are expanded and allowed."""
        with patch.dict(os.environ, {"SECRET_TOKEN": "expanded_token_value"}):
            config = CmdCheckConfig()
            config_data = {
                "uptime_kuma": {"url": "http://test.com"},
                "heartbeat": {"uptime_kuma": {"token": "heartbeat_token"}},
                "cmdcheck": {
                    "commands": [{"command": "echo hello"}],
                    "uptime_kuma": {"token": "${SECRET_TOKEN}"},
                },
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                assert config.command_token == "expanded_token_value"
                # Validation should succeed
                config.validate()

            finally:
                os.unlink(config_file)

    def test_cmdcheck_commands_not_expanded_during_yaml_loading(self):
        """Test that command env vars are not expanded during YAML loading."""
        with patch.dict(os.environ, {"MALICIOUS_VAR": "injected_command"}):
            config = CmdCheckConfig()
            config_data = {
                "uptime_kuma": {"url": "http://test.com"},
                "heartbeat": {"uptime_kuma": {"token": "heartbeat_token"}},
                "cmdcheck": {
                    "commands": [{"command": "echo ${MALICIOUS_VAR}"}],
                    "uptime_kuma": {"token": "cmd_token"},
                },
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = f.name

            try:
                config.load_from_yaml(config_file)
                # Command should still contain the literal ${MALICIOUS_VAR}
                assert config.cmdcheck_commands[0]["command"] == "echo ${MALICIOUS_VAR}"

            finally:
                os.unlink(config_file)
