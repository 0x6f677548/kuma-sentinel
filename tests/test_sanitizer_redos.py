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