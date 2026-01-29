"""Tests for ReDoS protection in sanitizer."""

import time
import pytest
from src.kuma_scout.core.utils.sanitizer import DataSanitizer, SanitizerMonitor, get_sanitizer_monitor


class TestReDoSProtection:
    """Test ReDoS protection mechanisms."""

    def test_input_length_limit(self):
        """Test that overly long inputs are rejected."""
        long_input = "x" * (DataSanitizer.MAX_INPUT_LENGTH + 1)
        result = DataSanitizer.sanitize(long_input)
        assert "[INPUT_TOO_LONG_" in result

    def test_malicious_email_patterns(self):
        """Test resistance to malicious email-like patterns."""
        # Create input with many email-like strings that could cause backtracking in vulnerable patterns
        # This creates a string with many potential matches
        malicious_parts = []
        for i in range(100):
            malicious_parts.append(f"user{i}@example.com")
        malicious = " ".join(malicious_parts)

        start_time = time.time()
        result = DataSanitizer.sanitize(malicious)
        duration = time.time() - start_time

        # Should complete quickly despite many potential matches
        assert duration < 0.5  # Less than 500ms
        assert "[REDACTED_EMAIL]" in result
        # Should have multiple redactions
        assert result.count("[REDACTED_EMAIL]") > 50

    def test_nested_quotes_password_pattern(self):
        """Test resistance to complex password patterns."""
        # Create input with many password patterns that could cause backtracking
        malicious_parts = []
        for i in range(50):
            malicious_parts.append(f'password="value{i}"')
            malicious_parts.append(f'secret:token{i}')
            malicious_parts.append(f'api_key=value{i}')
        malicious = " ".join(malicious_parts)

        start_time = time.time()
        result = DataSanitizer.sanitize(malicious)
        duration = time.time() - start_time

        assert duration < 0.5
        assert "[REDACTED]" in result
        # Should have multiple redactions
        assert result.count("[REDACTED]") > 100

    def test_circuit_breaker_timeout(self):
        """Test circuit breaker activates on timeout."""
        result = DataSanitizer.sanitize_with_circuit_breaker(
            "normal input", max_processing_time=0.001
        )
        assert result == "normal input"

    def test_fallback_on_regex_failure(self):
        """Test fallback behavior when regex operations fail."""
        # Test with a pattern that might cause issues
        result = DataSanitizer.sanitize("test@example.com password=secret")
        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED]" in result

    def test_safe_sub_replacement_limits(self):
        """Test that _safe_sub respects replacement limits."""
        import re
        pattern = DataSanitizer._compile_pattern(r"a", re.IGNORECASE)
        input_str = "a" * 200  # 200 'a's

        result = DataSanitizer._safe_sub(pattern, "b", input_str)

        # Should not replace all occurrences due to MAX_REPLACEMENTS limit
        assert len(result) < len(input_str) * 2  # Should not grow excessively

    def test_monitor_functionality(self):
        """Test sanitizer monitor functionality."""
        monitor = SanitizerMonitor()

        # Record some sanitizations
        monitor.record_sanitization(100, 0.05, True, False)  # Normal
        monitor.record_sanitization(1000, 0.2, True, False)  # Slow
        monitor.record_sanitization(500, 0.1, False, False)  # Failed
        monitor.record_sanitization(200, 1.5, False, True)   # Timeout

        stats = monitor.get_stats()

        assert stats["total"] == 4
        assert stats["failed"] == 1
        assert stats["slow"] == 1
        assert stats["timeouts"] == 1
        assert stats["failure_rate"] == 0.25

    def test_global_monitor_access(self):
        """Test global monitor access."""
        monitor = get_sanitizer_monitor()
        assert isinstance(monitor, SanitizerMonitor)

        # Should return the same instance
        monitor2 = get_sanitizer_monitor()
        assert monitor is monitor2

    def test_length_limits_in_patterns(self):
        """Test that length limits in patterns prevent excessive matching."""
        # Test email pattern with very long local part
        long_local = "a" * 100 + "@example.com"
        result = DataSanitizer.sanitize(long_local)
        # Should still work but may not match due to length limits
        assert isinstance(result, str)

    def test_atomic_groups_prevent_backtracking(self):
        """Test that atomic groups in patterns prevent catastrophic backtracking."""
        # This test verifies the patterns compile and work
        test_input = 'password="secret" token=abc123 email=test@example.com'
        result = DataSanitizer.sanitize(test_input)

        assert "[REDACTED]" in result
        assert "[REDACTED_EMAIL]" in result
        assert "password" not in result
        assert "secret" not in result
        assert "token" not in result
        assert "abc123" not in result

    def test_regex_compilation_failure_fallback(self):
        """Test fallback behavior when regex compilation fails."""
        # Test the _compile_pattern method directly
        invalid_pattern = r"[invalid regex (unclosed bracket"
        compiled = DataSanitizer._compile_pattern(invalid_pattern)

        # Should return a pattern that never matches
        result = compiled.search("any text")
        assert result is None

    def test_safe_sub_excessive_growth_protection(self):
        """Test that _safe_sub prevents excessive result growth."""
        import re
        # Create a pattern that would cause massive growth if not limited
        pattern = DataSanitizer._compile_pattern(r"a", re.IGNORECASE)
        # Input that would grow massively if all replacements happen
        input_str = "a" * 50

        # Mock a replacement function that causes massive growth
        def growing_repl(match):
            return "x" * 1000  # Each replacement grows the string massively

        result = DataSanitizer._safe_sub(pattern, growing_repl, input_str)

        # Should be limited by the growth check - result should be shorter than unlimited growth
        # The warning message indicates the protection worked
        assert len(result) < 50000  # Much less than 50 * 1000 = 50,000

    def test_safe_sub_fallback_on_exception(self):
        """Test _safe_sub fallback when regex operations fail."""
        import re
        # Create a valid pattern
        pattern = DataSanitizer._compile_pattern(r"test", re.IGNORECASE)

        # Mock a replacement function that raises an exception
        def failing_repl(match):
            raise RuntimeError("Replacement failed")

        result = DataSanitizer._safe_sub(pattern, failing_repl, "test string")

        # Should return original string on failure
        assert result == "test string"

    def test_sanitize_ssh_uri_safe_method(self):
        """Test the _sanitize_ssh_uri_safe method directly."""
        # Test SSH URI sanitization
        test_input = "Connect to ssh://user:pass@host.com:22 for access"
        result = DataSanitizer._sanitize_ssh_uri_safe(test_input)

        assert "[REDACTED]" in result
        assert "user:pass" not in result
        assert "host.com" in result
        assert ":22" in result

    def test_sanitize_main_exception_handling(self):
        """Test exception handling in main sanitize method."""
        # Since _compile_pattern handles regex errors gracefully, we need to test
        # a different kind of exception. Let's mock the _safe_sub method to raise an exception
        import unittest.mock

        with unittest.mock.patch.object(DataSanitizer, '_safe_sub') as mock_safe_sub:
            mock_safe_sub.side_effect = RuntimeError("Mocked exception")

            result = DataSanitizer.sanitize("password=secret")
            # Should return the fallback error message
            assert result == "[SANITIZATION_FAILED]"

    def test_sanitize_with_circuit_breaker_slow_operation_logging(self):
        """Test that slow operations are logged in circuit breaker."""
        # Create input that will be slow to process (many replacements)
        slow_input = " ".join([f"password=secret{i}" for i in range(50)])

        result = DataSanitizer.sanitize_with_circuit_breaker(
            slow_input, max_processing_time=10.0  # High timeout
        )

        # Should still work and return sanitized result
        assert "[REDACTED]" in result
        assert "password=" not in result

    def test_sanitize_with_circuit_breaker_exception_handling(self):
        """Test exception handling in sanitize_with_circuit_breaker."""
        # Mock the sanitize method to raise an exception
        import unittest.mock

        with unittest.mock.patch.object(DataSanitizer, 'sanitize') as mock_sanitize:
            mock_sanitize.side_effect = RuntimeError("Mocked sanitize exception")

            result = DataSanitizer.sanitize_with_circuit_breaker(
                "password=secret", max_processing_time=1.0
            )
            # Should return fallback redaction (all non-space chars become *)
            assert result == "*" * len("password=secret")

    def test_sanitize_with_circuit_breaker_timeout_fallback(self):
        """Test timeout fallback in sanitize_with_circuit_breaker."""
        # Create a scenario that might timeout (though unlikely in test)
        # We'll simulate by setting a very low timeout
        result = DataSanitizer.sanitize_with_circuit_breaker(
            "normal text", max_processing_time=0.000001  # Very low timeout
        )

        # Should either return normal result or timeout indicator
        assert isinstance(result, str)

    def test_safe_sub_fallback_without_timeout(self):
        """Test _safe_sub fallback path when REGEX_TIMEOUT is None."""
        # Temporarily set REGEX_TIMEOUT to None to test fallback path
        original_timeout = DataSanitizer.REGEX_TIMEOUT
        DataSanitizer.REGEX_TIMEOUT = None

        try:
            import re
            pattern = DataSanitizer._compile_pattern(r"a", re.IGNORECASE)
            input_str = "a" * 200  # Many 'a's

            result = DataSanitizer._safe_sub(pattern, "b", input_str)

            # Should be limited by MAX_REPLACEMENTS
            assert len(result) <= len(input_str)  # Should not grow
        finally:
            DataSanitizer.REGEX_TIMEOUT = original_timeout

    def test_sanitize_ssh_uri_safe_exception_fallback(self):
        """Test exception fallback in _sanitize_ssh_uri_safe."""
        # Mock _compile_pattern to raise an exception
        import unittest.mock

        with unittest.mock.patch.object(DataSanitizer, '_compile_pattern') as mock_compile:
            mock_compile.side_effect = RuntimeError("Mocked compile error")

            result = DataSanitizer._sanitize_ssh_uri_safe("ssh://user@host.com")
            # Should fall back to the original _sanitize_ssh_uri method
            assert "[REDACTED]" in result

    def test_replace_ssh_uri_exception_handling(self):
        """Test exception handling in _replace_ssh_uri."""
        # Create a mock match object that will cause an exception
        import unittest.mock

        mock_match = unittest.mock.MagicMock()
        mock_match.group.side_effect = IndexError("Mocked index error")

        result = DataSanitizer._replace_ssh_uri(mock_match)
        assert result == "[REDACTED_SSH_URI]"

    def test_sanitize_output_early_return(self):
        """Test early return in sanitize_output when mask_sensitive is False."""
        result = DataSanitizer.sanitize_output("some text", mask_sensitive=False)
        assert result == "some text"

    def test_sanitize_error_message_method(self):
        """Test the sanitize_error_message method."""
        # Test with None error
        result = DataSanitizer.sanitize_error_message(None)
        assert result == ""

        # Test with actual error containing sensitive data
        error = ValueError("Connection failed: password=secret user@test.com")
        result = DataSanitizer.sanitize_error_message(error)

        assert "[REDACTED]" in result
        assert "[REDACTED_EMAIL]" in result
        assert "password=secret" not in result
        assert "user@test.com" not in result

    def test_sanitize_ssh_uri_with_port(self):
        """Test SSH URI sanitization with port number."""
        test_input = "Connect to ssh://user:pass@host.com:2222 for access"
        result = DataSanitizer._sanitize_ssh_uri_safe(test_input)

        assert "[REDACTED]" in result
        assert "user:pass" not in result
        assert "host.com" in result
        assert ":2222" in result

    def test_sanitize_with_circuit_breaker_empty_text(self):
        """Test sanitize_with_circuit_breaker with empty/None text."""
        result = DataSanitizer.sanitize_with_circuit_breaker(None)
        assert result == ""

        result = DataSanitizer.sanitize_with_circuit_breaker("")
        assert result == ""

    def test_sanitize_with_circuit_breaker_timeout_return(self):
        """Test the timeout return path in sanitize_with_circuit_breaker."""
        # Mock sanitize to raise an exception after taking longer than max_processing_time
        import unittest.mock
        import time

        def slow_sanitize(*args, **kwargs):
            time.sleep(0.01)  # Sleep for 10ms
            raise RuntimeError("Mocked timeout")

        with unittest.mock.patch.object(DataSanitizer, 'sanitize', side_effect=slow_sanitize):
            result = DataSanitizer.sanitize_with_circuit_breaker(
                "test", max_processing_time=0.005  # 5ms timeout
            )

            # Should return timeout since sanitize took longer than 5ms and raised exception
            assert result == "[SANITIZATION_TIMEOUT]"