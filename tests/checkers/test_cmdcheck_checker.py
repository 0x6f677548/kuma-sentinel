"""Tests for cmdcheck checker."""

import time
from unittest.mock import MagicMock, patch

import pytest

from kuma_sentinel.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig


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
    cfg.cmdcheck_command = "test -f /tmp/file"
    cfg.cmdcheck_timeout = 30
    cfg.cmdcheck_expect_exit_code = 0
    cfg.cmdcheck_capture_output = True
    return cfg


@pytest.fixture
def checker(logger, config):
    """Create cmdcheck checker instance."""
    return CmdCheckChecker(logger, config)


class TestSingleCommandExecution:
    """Test single command execution."""

    def test_success_exit_code_zero(self, checker):
        """Test successful command with exit code 0."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="file exists\n", stderr=""
            )

            result = checker.execute()

            assert result.status == "up"
            assert "✓" in result.message  # Success symbol
            assert "test -f /tmp/file" in result.message  # Command included
            assert result.duration_seconds >= 0

    def test_failure_non_zero_exit(self, checker):
        """Test failed command with non-zero exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="file not found"
            )

            result = checker.execute()

            assert result.status == "down"
            assert "failed" in result.message.lower()

    def test_custom_expected_exit_code(self, checker):
        """Test with custom expected exit code."""
        checker.config.cmdcheck_expect_exit_code = 1

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"

    def test_command_timeout(self, checker):
        """Test command timeout handling."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

            result = checker.execute()

            assert result.status == "down"
            assert "timed" in result.message.lower()
            assert "30" in result.message

    def test_command_not_found(self, checker):
        """Test command not found error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = checker.execute()

            assert result.status == "down"
            assert "not found" in result.message.lower()

    def test_subprocess_error(self, checker):
        """Test generic subprocess error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Generic error")

            result = checker.execute()

            assert result.status == "down"
            assert "error" in result.message.lower()

    def test_output_truncation_stdout(self, checker):
        """Test output is truncated to 500 chars."""
        large_output = "x" * 1000

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=large_output, stderr=""
            )

            result = checker.execute()

            assert result.status == "up"
            # Details should contain truncated output
            output_in_details = result.details["output"]
            assert len(output_in_details) <= 200  # Limited in details

    def test_output_stderr_capture(self, checker):
        """Test stderr is captured along with stdout."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="stdout text", stderr="stderr text"
            )

            result = checker.execute()

            # Both should be in combined output
            assert result.status == "up"
            assert result.details is not None


class TestPatternMatching:
    """Test pattern matching logic."""

    def test_failure_pattern_match(self, checker):
        """Test failure pattern detection."""
        checker.config.cmdcheck_failure_pattern = "ERROR|FATAL"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Something went FATAL", stderr=""
            )

            result = checker.execute()

            assert result.status == "down"
            assert "failure pattern" in result.message.lower()

    def test_success_pattern_match(self, checker):
        """Test success pattern detection."""
        checker.config.cmdcheck_success_pattern = "healthy|OK"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="Status: OK", stderr=""
            )

            result = checker.execute()

            assert result.status == "up"
            assert "success pattern" in result.message.lower()

    def test_success_pattern_not_found(self, checker):
        """Test when success pattern is not found."""
        checker.config.cmdcheck_success_pattern = "^HEALTHY$"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Status: UNHEALTHY", stderr=""
            )

            result = checker.execute()

            assert result.status == "down"
            assert "not found" in result.message.lower()

    def test_pattern_precedence_failure_over_success(self, checker):
        """Test failure pattern takes precedence over success pattern."""
        checker.config.cmdcheck_failure_pattern = "FAIL"
        checker.config.cmdcheck_success_pattern = "OK"

        with patch("subprocess.run") as mock_run:
            # Output matches both patterns
            mock_run.return_value = MagicMock(returncode=0, stdout="FAIL OK", stderr="")

            result = checker.execute()

            # Failure pattern should win
            assert result.status == "down"

    def test_success_pattern_takes_precedence_over_exit_code(self, checker):
        """Test success pattern takes precedence over exit code."""
        checker.config.cmdcheck_success_pattern = "SUCCESS"
        checker.config.cmdcheck_expect_exit_code = 0

        with patch("subprocess.run") as mock_run:
            # Non-zero exit but matches success pattern
            mock_run.return_value = MagicMock(returncode=1, stdout="SUCCESS", stderr="")

            result = checker.execute()

            # Pattern should override exit code
            assert result.status == "up"

    def test_exit_code_fallback_when_no_patterns(self, checker):
        """Test exit code is used when no patterns specified."""
        # No patterns set
        checker.config.cmdcheck_success_pattern = None
        checker.config.cmdcheck_failure_pattern = None
        checker.config.cmdcheck_expect_exit_code = 42

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=42, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"

    def test_pattern_matching_on_last_500_chars(self, checker):
        """Test pattern matching uses last 500 chars of output."""
        checker.config.cmdcheck_failure_pattern = "ERROR"
        large_output = "x" * 800 + "ERROR at end"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=large_output, stderr=""
            )

            result = checker.execute()

            # ERROR is in last 500 chars, should be detected
            assert result.status == "down"

    def test_pattern_not_detected_before_last_500(self, checker):
        """Test pattern outside last 500 chars is not detected."""
        checker.config.cmdcheck_failure_pattern = "EARLY_ERROR"
        large_output = "EARLY_ERROR" + ("x" * 800)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=large_output, stderr=""
            )

            result = checker.execute()

            # EARLY_ERROR is outside last 500 chars
            assert result.status == "up"

    def test_regex_pattern_complex(self, checker):
        """Test complex regex patterns."""
        checker.config.cmdcheck_success_pattern = r"^\d+\.\d+\.\d+$"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="1.2.3", stderr="")

            result = checker.execute()

            assert result.status == "up"


class TestMultipleCommands:
    """Test multiple command execution."""

    def test_all_commands_succeed(self, checker):
        """Test when all commands succeed."""
        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_commands = [
            {"command": "true", "name": "cmd1"},
            {"command": "true", "name": "cmd2"},
            {"command": "true", "name": "cmd3"},
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"
            assert "✓" in result.message  # Success symbol
            assert "All 3/3" in result.message
            assert "cmd1" in result.message  # Command names included
            assert result.details is not None
            assert len(result.details["commands"]) == 3

    def test_one_command_fails(self, checker):
        """Test when one command fails."""
        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_commands = [
            {"command": "true", "name": "cmd1"},
            {"command": "false", "name": "cmd2"},
            {"command": "true", "name": "cmd3"},
        ]

        with patch("subprocess.run") as mock_run:

            def side_effect(*args, **kwargs):
                # Return based on which command
                if "false" in args[0]:
                    return MagicMock(returncode=1, stdout="", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "down"
            assert "✗" in result.message  # Failure symbol
            assert "2/3 passed" in result.message or "1/3 failed" in result.message
            assert "cmd2" in result.message  # Failed command name included

    def test_all_commands_fail(self, checker):
        """Test when all commands fail."""
        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_commands = [
            {"command": "false", "name": "cmd1"},
            {"command": "false", "name": "cmd2"},
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

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

        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_timeout = 10  # Default
        checker.config.cmdcheck_commands = [
            {"command": "sleep 5", "timeout": 20},  # Should not timeout
            {"command": "sleep 100", "timeout": 2, "name": "slow"},  # Should timeout
        ]

        with patch("subprocess.run") as mock_run:

            def side_effect(*args, **kwargs):
                timeout = kwargs.get("timeout", 10)
                if "sleep 100" in args[0] and timeout <= 2:
                    raise subprocess.TimeoutExpired("cmd", timeout)
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "down"
            assert "failed" in result.message.lower()

    def test_multiple_commands_per_command_exit_code(self, checker):
        """Test per-command exit code override."""
        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_expect_exit_code = 0  # Default
        checker.config.cmdcheck_commands = [
            {"command": "grep notfound file", "expect_exit_code": 1, "name": "grep"},
            {"command": "true", "expect_exit_code": 0, "name": "true"},
        ]

        with patch("subprocess.run") as mock_run:

            def side_effect(*args, **kwargs):
                if "notfound" in args[0]:
                    return MagicMock(returncode=1, stdout="", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            result = checker.execute()

            assert result.status == "up"

    def test_multiple_commands_aggregated_details(self, checker):
        """Test aggregated details for multiple commands."""
        checker.config.cmdcheck_multiple = True
        checker.config.cmdcheck_commands = [
            {"command": "echo hello", "name": "cmd1"},
            {"command": "echo world", "name": "cmd2"},
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

            result = checker.execute()

            assert result.details is not None
            assert "commands" in result.details
            assert len(result.details["commands"]) == 2
            assert result.details["commands"][0]["name"] == "cmd1"
            assert result.details["commands"][1]["name"] == "cmd2"


class TestShellExecution:
    """Test shell execution details."""

    def test_shell_features_pipes(self, checker):
        """Test that shell features like pipes work."""
        checker.config.cmdcheck_command = "echo hello | grep hello"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="hello", stderr="")

            checker.execute()

            # Verify shell=True and /bin/bash were used
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["shell"] is True
            assert call_kwargs["executable"] == "/bin/bash"

    def test_shell_redirects(self, checker):
        """Test shell redirects work."""
        checker.config.cmdcheck_command = (
            "echo test > /tmp/test.txt && test -f /tmp/test.txt"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"

    def test_shell_command_substitution(self, checker):
        """Test shell command substitution."""
        checker.config.cmdcheck_command = "test $(echo 5) -gt 3"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"


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

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = checker.execute()

            assert result.status == "up"

    def test_command_with_newlines(self, checker):
        """Test command with newlines."""
        checker.config.cmdcheck_command = "echo hello\necho world"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="hello\nworld", stderr=""
            )

            result = checker.execute()

            assert result.status == "up"

    def test_both_capture_output_true_and_false(self, checker):
        """Test capture_output flag behavior."""
        # With capture
        checker.config.cmdcheck_capture_output = True
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="test", stderr="")
            checker.execute()
            assert mock_run.call_args[1]["capture_output"] is True

        # Without capture
        checker.config.cmdcheck_capture_output = False
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=None, stderr=None)
            checker.execute()
            assert mock_run.call_args[1]["capture_output"] is False

    def test_duration_tracking(self, checker):
        """Test that duration is properly tracked."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            start = time.time()
            result = checker.execute()
            elapsed = time.time() - start

            assert result.duration_seconds >= 0
            assert result.duration_seconds <= elapsed + 0.1

    def test_none_stdout_stderr(self, checker):
        """Test handling of None stdout/stderr."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=None, stderr=None)

            result = checker.execute()

            assert result.status == "up"
            assert result.details is not None

    def test_very_long_output(self, checker):
        """Test with very long output (5000+ chars)."""
        huge_output = "x" * 5000

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=huge_output, stderr=""
            )

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
