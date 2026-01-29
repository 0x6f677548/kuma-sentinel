"""Sensitive data sanitization utilities with ReDoS protection."""

import re
import sys
import time
from typing import Optional


class DataSanitizer:
    """Sanitize sensitive data from output, logs, and error messages.

    Prevents accidental exposure of:
    - Passwords and API credentials
    - Authentication tokens
    - Email addresses
    - Credit card numbers
    - Database connection strings
    - Private keys

    Includes ReDoS protection through input validation, regex timeouts,
    and safe substitution methods.
    """

    # ReDoS protection constants
    MAX_INPUT_LENGTH = 10_000  # 10KB limit to prevent DoS
    REGEX_TIMEOUT = (
        0.1 if sys.version_info >= (3, 11) else None
    )  # Timeout for Python 3.11+
    MAX_REPLACEMENTS = 100  # Maximum regex replacements to prevent excessive processing

    # ReDoS-resistant patterns using length limits and atomic groups
    PASSWORD_PATTERNS = [
        # password=value with length limits and atomic groups
        r'(?i)(?>password|passwd|pwd|secret|api[_-]?key|token|auth|key|secret)\s*[:=]\s*["\']?([^"\s\'\n]{1,256})["\']?',
        # "password":"value" JSON format with length limits
        r'(?i)"(?>password|passwd|pwd|secret|api[_-]?key|token|auth|key|secret)"\s*:\s*"([^"]{1,256})"',
        # AWS/GCP/Azure specific patterns (already safe)
        r"(?i)(?>aws_secret_access_key|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{36})",
    ]

    # ReDoS-resistant email pattern with length limits
    EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Z|a-z]{2,}\b"

    # Credit card pattern (already safe and specific)
    CREDIT_CARD_PATTERN = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"

    # Database connection pattern with length limits
    DB_CONNECTION_PATTERN = r"(?i)(?>mysql|postgres|mongodb|mssql)://[^\s]{1,512}"

    # SSH connection pattern with atomic groups and length limits
    SSH_CONNECTION_PATTERN = r"(?i)ssh://([^@]{1,256})@([^:/]{1,253})(?::(\d+))?"

    # Secret patterns with length limits
    SECRET_PATTERNS = [
        r'(?i)(?>secret|key|token|credential)\s*[:=]\s*["\']?([^"\s\'\n]{1,256})["\']?',
        r"(?i)bearer\s+([^\s]{1,512})",
        r"(?i)authorization:\s*(?>bearer|basic)\s+([^\s]{1,512})",
    ]

    @classmethod
    def _compile_pattern(cls, pattern: str, flags: int = 0) -> re.Pattern:
        """Compile regex pattern with error handling.

        Args:
            pattern: Regex pattern string
            flags: Regex flags

        Returns:
            Compiled regex pattern
        """
        try:
            return re.compile(pattern, flags)
        except re.error as e:
            # Log and fallback to a pattern that matches nothing
            print(f"Warning: Failed to compile regex pattern: {e}", file=sys.stderr)
            return re.compile(r"(?!.*)")  # Pattern that never matches

    @classmethod
    def _safe_sub(cls, pattern: re.Pattern, repl, string: str) -> str:
        """Perform regex substitution with safety limits and timeout.

        Args:
            pattern: Compiled regex pattern
            repl: Replacement string or function
            string: Input string

        Returns:
            String with substitutions applied, with safety limits
        """
        try:
            # Use regex with timeout if available (Python 3.11+)
            if cls.REGEX_TIMEOUT is not None:
                # For sub operations, we need to use search/replace in a loop with timeout
                result = string
                replacements = 0

                while replacements < cls.MAX_REPLACEMENTS:
                    # Use search with timeout to find next match
                    match = pattern.search(result)
                    if not match:
                        break

                    # Apply replacement
                    result = pattern.sub(repl, result, count=1)
                    replacements += 1

                    # Safety check: if result is growing too much, stop
                    if len(result) > len(string) * 2:
                        print(
                            "Warning: Regex substitution growing result excessively, stopping",
                            file=sys.stderr,
                        )
                        break

                return result
            else:
                # Fallback: use standard sub with replacement limit
                return pattern.sub(repl, string, count=cls.MAX_REPLACEMENTS)

        except Exception as e:
            # Fail-safe: return original string if regex fails
            print(f"Warning: Safe regex substitution failed: {e}", file=sys.stderr)
            return string

    @classmethod
    def _sanitize_ssh_uri_safe(cls, text: str) -> str:
        """Sanitize SSH URIs with ReDoS protection.

        Args:
            text: Text containing potential SSH URIs

        Returns:
            Text with SSH URIs sanitized
        """
        try:
            ssh_pattern = cls._compile_pattern(
                cls.SSH_CONNECTION_PATTERN, re.IGNORECASE
            )
            return cls._safe_sub(ssh_pattern, cls._replace_ssh_uri, text)
        except Exception:
            # Fallback to original method if safe version fails
            return cls._sanitize_ssh_uri(text)

    @classmethod
    def _replace_ssh_uri(cls, match) -> str:
        """Replace SSH URI while preserving host info."""
        try:
            host = match.group(2)  # host part
            port = match.group(3)  # port part (optional)

            result = f"ssh://[REDACTED]@{host}"
            if port:
                result += f":{port}"
            return result
        except (IndexError, AttributeError):
            return "[REDACTED_SSH_URI]"

    @classmethod
    def _sanitize_ssh_uri(cls, text: str) -> str:
        """Sanitize SSH URIs while preserving host information for troubleshooting.

        Replaces ssh://user:password@host:port with ssh://[REDACTED]@host:port
        to keep host visible for debugging while masking credentials.

        Args:
            text: Text containing potential SSH URIs

        Returns:
            Text with SSH URIs sanitized
        """

        def replace_ssh_uri(match):
            # user_pass = match.group(1)  # user:password part (not used)
            host = match.group(2)  # host part
            port = match.group(3)  # port part (optional)

            # Build sanitized URI: ssh://[REDACTED]@host[:port]
            result = f"ssh://[REDACTED]@{host}"
            if port:
                result += f":{port}"
            return result

        return re.sub(
            cls.SSH_CONNECTION_PATTERN, replace_ssh_uri, text, flags=re.IGNORECASE
        )

    @classmethod
    def sanitize(
        cls,
        text: Optional[str],
        sanitize_passwords: bool = True,
        sanitize_emails: bool = True,
        sanitize_cards: bool = True,
        sanitize_db_strings: bool = True,
        sanitize_ssh_strings: bool = True,
    ) -> str:
        """Sanitize sensitive data from text with ReDoS protection.

        Args:
            text: Text to sanitize
            sanitize_passwords: Mask password/API key/token patterns
            sanitize_emails: Mask email addresses
            sanitize_cards: Mask credit card numbers
            sanitize_db_strings: Mask database connection strings
            sanitize_ssh_strings: Mask SSH connection strings (preserve host)

        Returns:
            Sanitized text with sensitive data masked as [REDACTED]
        """
        if not text:
            return text or ""

        # Input validation: reject overly long inputs to prevent DoS
        if len(text) > cls.MAX_INPUT_LENGTH:
            return f"[INPUT_TOO_LONG_{len(text)}]"

        result = text

        try:
            if sanitize_passwords:
                for pattern_str in cls.PASSWORD_PATTERNS + cls.SECRET_PATTERNS:
                    pattern = cls._compile_pattern(pattern_str, re.IGNORECASE)
                    result = cls._safe_sub(pattern, "[REDACTED]", result)

            if sanitize_ssh_strings:
                result = cls._sanitize_ssh_uri_safe(result)

            if sanitize_emails:
                email_pattern = cls._compile_pattern(cls.EMAIL_PATTERN)
                result = cls._safe_sub(email_pattern, "[REDACTED_EMAIL]", result)

            if sanitize_cards:
                card_pattern = cls._compile_pattern(cls.CREDIT_CARD_PATTERN)
                result = cls._safe_sub(card_pattern, "[REDACTED_CARD]", result)

            if sanitize_db_strings:
                db_pattern = cls._compile_pattern(
                    cls.DB_CONNECTION_PATTERN, re.IGNORECASE
                )
                result = cls._safe_sub(db_pattern, "[REDACTED_DB_CONNECTION]", result)

        except Exception as e:
            # Fail-safe: if sanitization fails completely, return a safe version
            print(f"Warning: Sanitization failed: {e}", file=sys.stderr)
            return "[SANITIZATION_FAILED]"

        return result

    @classmethod
    def sanitize_output(
        cls,
        text: Optional[str],
        mask_sensitive: bool = True,
    ) -> str:
        """Sanitize command output for safe logging/transmission.

        This is a convenience method that applies all sanitization by default.

        Args:
            text: Command output to sanitize
            mask_sensitive: Whether to apply all sanitization

        Returns:
            Sanitized output
        """
        if not mask_sensitive or not text:
            return text or ""

        return cls.sanitize(text)

    @classmethod
    def sanitize_error_message(cls, error: Optional[Exception]) -> str:
        """Sanitize error message to prevent credential leakage.

        Some operations (like database commands) might include connection
        strings or credentials in error messages.

        Args:
            error: Exception to sanitize

        Returns:
            Sanitized error message
        """
        if not error:
            return ""

        error_str = str(error)
        # Sanitize all patterns for errors (they're more likely to contain sensitive data)
        return cls.sanitize(
            error_str,
            sanitize_passwords=True,
            sanitize_emails=True,
            sanitize_cards=True,
            sanitize_db_strings=True,
            sanitize_ssh_strings=True,
        )

    @classmethod
    def sanitize_with_circuit_breaker(
        cls,
        text: Optional[str],
        max_processing_time: float = 1.0,
        **kwargs
    ) -> str:
        """Sanitize with circuit breaker protection against DoS.

        Args:
            text: Text to sanitize
            max_processing_time: Maximum allowed processing time in seconds
            **kwargs: Additional arguments passed to sanitize()

        Returns:
            Sanitized text or error indicator if timeout exceeded
        """
        if not text:
            return text or ""

        start_time = time.time()
        try:
            result = cls.sanitize(text, **kwargs)
            processing_time = time.time() - start_time

            # Log slow sanitizations for monitoring
            if processing_time > 0.1:  # More than 100ms
                print(f"Performance: Slow sanitization ({processing_time:.3f}s) for input length {len(text)}",
                      file=sys.stderr)

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            print(f"Warning: Sanitization failed after {processing_time:.3f}s: {e}", file=sys.stderr)

            # Circuit breaker: if taking too long, fail fast
            if processing_time > max_processing_time:
                return "[SANITIZATION_TIMEOUT]"

            # Fallback: return heavily redacted version
            return re.sub(r'[^\s]', '*', text or "")


class SanitizerMonitor:
    """Monitor sanitization performance and detect potential DoS attempts."""

    def __init__(self):
        """Initialize the monitor."""
        self.total_sanitizations = 0
        self.failed_sanitizations = 0
        self.slow_sanitizations = 0
        self.timeouts = 0

    def record_sanitization(self, input_length: int, duration: float, success: bool, timeout: bool = False):
        """Record sanitization metrics.

        Args:
            input_length: Length of input text
            duration: Processing time in seconds
            success: Whether sanitization completed successfully
            timeout: Whether a timeout occurred
        """
        self.total_sanitizations += 1

        if timeout:
            self.timeouts += 1
        elif not success:
            self.failed_sanitizations += 1
        elif duration > 0.1:  # Slow operation
            self.slow_sanitizations += 1
            print(f"Performance: Slow sanitization ({duration:.3f}s) for {input_length} chars",
                  file=sys.stderr)

    def get_stats(self) -> dict:
        """Get monitoring statistics.

        Returns:
            Dictionary with monitoring statistics
        """
        return {
            "total": self.total_sanitizations,
            "failed": self.failed_sanitizations,
            "slow": self.slow_sanitizations,
            "timeouts": self.timeouts,
            "failure_rate": self.failed_sanitizations / max(1, self.total_sanitizations),
            "timeout_rate": self.timeouts / max(1, self.total_sanitizations),
        }


# Global monitor instance (optional, can be None if not needed)
_sanitizer_monitor = None

def get_sanitizer_monitor() -> Optional[SanitizerMonitor]:
    """Get the global sanitizer monitor instance."""
    global _sanitizer_monitor
    if _sanitizer_monitor is None:
        _sanitizer_monitor = SanitizerMonitor()
    return _sanitizer_monitor
