"""Tests for SSH runner utilities."""

from unittest.mock import MagicMock, patch

import pytest

from kuma_scout.core.utils.ssh_runner import (
    SSHConfig,
    SSHConnectionError,
    SSHRunner,
    parse_ssh_connection_string,
    parse_ssh_shorthand,
)


class TestSSHConfig:
    """Test SSHConfig dataclass and methods."""

    def test_from_connection_string(self):
        """Test creating SSHConfig from connection string."""
        config = SSHConfig.from_connection_string("user@host:22")
        assert config.host == "host"
        assert config.user == "user"
        assert config.port == 22

    def test_update_from_connection_string(self):
        """Test updating SSHConfig from connection string."""
        config = SSHConfig(host="existing", user="existing")
        config.update_from_connection_string("newuser@newhost:2222")
        # Should not update since values are already set
        assert config.host == "existing"
        assert config.user == "existing"
        assert config.port == 2222  # Port was None, so it gets set

        # Now update with None values
        config2 = SSHConfig()
        config2.update_from_connection_string("user@host:22")
        assert config2.host == "host"
        assert config2.user == "user"
        assert config2.port == 22

    def test_is_complete(self):
        """Test is_complete method."""
        assert SSHConfig(host="host").is_complete()
        assert not SSHConfig().is_complete()
        assert not SSHConfig(user="user").is_complete()


class TestSSHRunner:
    """Test SSHRunner class."""

    def test_init(self):
        """Test SSHRunner initialization."""
        runner = SSHRunner(
            host="testhost",
            user="testuser",
            port=2222,
            key_file="/path/to/key",
            password="secret",
            timeout=60,
            strict_host_key_checking=False,
        )
        assert runner.host == "testhost"
        assert runner.user == "testuser"
        assert runner.port == 2222
        assert runner.key_file == "/path/to/key"
        assert runner.password == "secret"
        assert runner.timeout == 60
        assert not runner.strict_host_key_checking

    def test_build_ssh_command_basic(self):
        """Test building basic SSH command."""
        runner = SSHRunner(host="host")
        cmd = runner.build_ssh_command(["echo", "hello"])
        expected = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=yes",
            "-T",
            "-p",
            "22",
            "host",
            "echo hello",
        ]
        assert cmd == expected

    def test_build_ssh_command_with_options(self):
        """Test building SSH command with all options."""
        runner = SSHRunner(
            host="host",
            user="user",
            port=2222,
            key_file="/key",
            strict_host_key_checking=False,
        )
        cmd = runner.build_ssh_command(["ls", "-la"])
        expected = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-T",
            "-p",
            "2222",
            "-i",
            "/key",
            "user@host",
            "ls -la",
        ]
        assert cmd == expected

    @patch("subprocess.run")
    def test_run_success(self, mock_run):
        """Test successful command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        runner = SSHRunner(host="host")
        success, stdout, stderr = runner.run(["echo", "test"])
        assert success
        assert stdout == "output"
        assert stderr == "error"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_failure(self, mock_run):
        """Test failed command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "command failed"
        mock_run.return_value = mock_result

        runner = SSHRunner(host="host")
        success, stdout, stderr = runner.run(["bad", "command"])
        assert not success
        assert stdout == ""
        assert stderr == "command failed"

    @patch("subprocess.run")
    def test_run_timeout(self, mock_run):
        """Test command timeout."""
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired(["ssh"], 30)

        runner = SSHRunner(host="host", timeout=30)
        success, stdout, stderr = runner.run(["slow", "command"])
        assert not success
        assert stdout == ""
        assert stderr == "Command timed out after 30s"

    @patch("subprocess.run")
    def test_run_exception(self, mock_run):
        """Test general exception during command execution."""
        mock_run.side_effect = Exception("network error")

        runner = SSHRunner(host="host")
        success, stdout, stderr = runner.run(["command"])
        assert not success
        assert stdout == ""
        assert stderr == "network error"

    @patch("subprocess.run")
    def test_run_with_password(self, mock_run):
        """Test command execution with password using sshpass."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        runner = SSHRunner(host="host", password="secret")
        runner.run(["echo", "test"])
        # Check that sshpass is prepended with -e flag
        args, kwargs = mock_run.call_args
        cmd = args[0]
        env = kwargs.get("env", {})
        assert cmd[0] == "sshpass"
        assert cmd[1] == "-e"
        assert cmd[2] == "ssh"
        # Password should be set in environment variable, not command line
        assert env.get("SSHPASS") == "secret"

    def test_is_ssh_connection_error(self):
        """Test SSH connection error detection."""
        runner = SSHRunner(host="host")

        # Test various connection error patterns
        assert runner._is_ssh_connection_error(
            "Connection closed by 192.168.1.1 port 22"
        )
        assert runner._is_ssh_connection_error("Permission denied (publickey,password)")
        assert runner._is_ssh_connection_error("Host key verification failed")
        assert runner._is_ssh_connection_error(
            "ssh: connect to host example.com port 22: Connection refused"
        )
        assert runner._is_ssh_connection_error("Network is unreachable")
        assert runner._is_ssh_connection_error("No route to host")
        assert runner._is_ssh_connection_error("Connection timed out")
        assert runner._is_ssh_connection_error("Authentication failed")
        assert runner._is_ssh_connection_error(
            "tailnet policy does not permit you to SSH as user"
        )

        # Test case insensitive
        assert runner._is_ssh_connection_error("CONNECTION CLOSED BY host")
        assert runner._is_ssh_connection_error("permission denied")

        # Test non-connection errors
        assert not runner._is_ssh_connection_error("command not found")
        assert not runner._is_ssh_connection_error("syntax error")
        assert not runner._is_ssh_connection_error("")

    @patch("subprocess.run")
    def test_run_ssh_connection_error(self, mock_run):
        """Test that SSH connection errors raise SSHConnectionError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Connection closed by 192.168.1.1 port 22"
        mock_run.return_value = mock_result

        runner = SSHRunner(host="host")
        with pytest.raises(SSHConnectionError) as exc_info:
            runner.run(["echo", "test"])

        assert "SSH connection failed" in str(exc_info.value)
        assert exc_info.value.stderr == "Connection closed by 192.168.1.1 port 22"

    @patch("subprocess.run")
    def test_run_ssh_connection_error_with_password(self, mock_run):
        """Test that SSH connection errors raise SSHConnectionError with password auth."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Permission denied (publickey,password)"
        mock_run.return_value = mock_result

        runner = SSHRunner(host="host", password="secret")
        with pytest.raises(SSHConnectionError) as exc_info:
            runner.run(["echo", "test"])

        assert "SSH connection failed" in str(exc_info.value)
        assert exc_info.value.stderr == "Permission denied (publickey,password)"


class TestParseSSHShorthand:
    """Test parse_ssh_shorthand function."""

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("user@host", ("host", "user")),
            ("host", ("host", None)),
            ("", (None, None)),
            (None, (None, None)),
            ("root@192.168.1.1", ("192.168.1.1", "root")),
        ],
    )
    def test_parse_ssh_shorthand(self, input_str, expected):
        """Test parsing various SSH shorthand formats."""
        assert parse_ssh_shorthand(input_str) == expected


class TestParseSSHConnectionString:
    """Test parse_ssh_connection_string function."""

    @pytest.mark.parametrize(
        "conn_str,expected",
        [
            ("host", ("host", None, None)),
            ("user@host", ("host", "user", None)),
            ("host:22", ("host", None, 22)),
            ("user@host:22", ("host", "user", 22)),
            ("ssh://user@host:22", ("host", "user", 22)),
            ("", (None, None, None)),
            ("host:invalid", ("host:invalid", None, None)),  # Invalid port
            ("user@host:invalid", ("user@host:invalid", None, None)),  # Invalid port
            ("host:123", ("host", None, 123)),
            ("[::1]:22", ("[::1]", None, 22)),  # IPv6 with port
        ],
    )
    def test_parse_ssh_connection_string(self, conn_str, expected):
        """Test parsing various SSH connection string formats."""
        assert parse_ssh_connection_string(conn_str) == expected
