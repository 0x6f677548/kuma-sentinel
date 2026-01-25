"""Sensitive data sanitization utilities for security."""

import re
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
    """

    # Pattern for common password/credential formats
    PASSWORD_PATTERNS = [
        # password=value, password: value, password"value
        r'(?i)(?:password|passwd|pwd|secret|api[_-]?key|token|auth|key|secret)\s*[:=]\s*["\']?([^\s"\'\n]+)["\']?',
        # "password":"value" JSON format
        r'(?i)"(?:password|passwd|pwd|secret|api[_-]?key|token|auth|key|secret)"\s*:\s*"([^"]*)"',
        # AWS/GCP/Azure patterns
        r"(?i)(?:aws_secret_access_key|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{36})",
    ]

    # Pattern for email addresses
    EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

    # Pattern for credit card numbers (PCI-DSS)
    CREDIT_CARD_PATTERN = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"

    # Pattern for database connection strings
    DB_CONNECTION_PATTERN = r"(?i)(?:mysql|postgres|mongodb|mssql)://[^\s]+"

    # Pattern for common secret formats in various config/output styles
    SECRET_PATTERNS = [
        r'(?i)(?:secret|key|token|credential)\s*[:=]\s*["\']?([^\s"\'\n]+)["\']?',
        r"(?i)bearer\s+([^\s]+)",
        r"(?i)authorization:\s*(?:bearer|basic)\s+([^\s]+)",
    ]

    @classmethod
    def sanitize(
        cls,
        text: Optional[str],
        sanitize_passwords: bool = True,
        sanitize_emails: bool = True,
        sanitize_cards: bool = True,
        sanitize_db_strings: bool = True,
    ) -> str:
        """Sanitize sensitive data from text.

        Args:
            text: Text to sanitize
            sanitize_passwords: Mask password/API key/token patterns
            sanitize_emails: Mask email addresses
            sanitize_cards: Mask credit card numbers
            sanitize_db_strings: Mask database connection strings

        Returns:
            Sanitized text with sensitive data masked as [REDACTED]
        """
        if not text:
            return text or ""

        result = text

        if sanitize_passwords:
            for pattern in cls.PASSWORD_PATTERNS + cls.SECRET_PATTERNS:
                result = re.sub(pattern, "[REDACTED]", result, flags=re.IGNORECASE)

        if sanitize_emails:
            result = re.sub(cls.EMAIL_PATTERN, "[REDACTED_EMAIL]", result)

        if sanitize_cards:
            result = re.sub(cls.CREDIT_CARD_PATTERN, "[REDACTED_CARD]", result)

        if sanitize_db_strings:
            result = re.sub(
                cls.DB_CONNECTION_PATTERN, "[REDACTED_DB_CONNECTION]", result
            )

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
        )
