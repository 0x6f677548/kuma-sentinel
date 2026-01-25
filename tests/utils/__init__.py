"""Tests for sensitive data sanitization."""

from kuma_sentinel.core.utils.sanitizer import DataSanitizer


class TestDataSanitizer:
    """Test data sanitization for sensitive data protection."""

    def test_sanitize_password_equals_format(self):
        """Test password=value format sanitization."""
        text = "database password=secret123 connected"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "secret123" not in result

    def test_sanitize_password_colon_format(self):
        """Test password: value format sanitization."""
        text = "Error: password: mypassword123"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "mypassword123" not in result

    def test_sanitize_api_key(self):
        """Test API key sanitization."""
        text = "api_key=sk_live_4eC39HqLyjWDarhhTeafmVmZ"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "sk_live" not in result

    def test_sanitize_aws_secret_key(self):
        """Test AWS secret key pattern."""
        text = "AKIA2E6TPGB7KXYKC5Q1 is the AWS key"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "AKIA2E6TPGB7KXYKC5Q1" not in result

    def test_sanitize_github_token(self):
        """Test GitHub token pattern."""
        text = "token: ghp_1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZab"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "ghp_1234567890" not in result

    def test_sanitize_bearer_token(self):
        """Test bearer token sanitization."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = DataSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_sanitize_email_address(self):
        """Test email address sanitization."""
        text = "Error from user admin@example.com"
        result = DataSanitizer.sanitize(text, sanitize_emails=True)
        assert "[REDACTED_EMAIL]" in result
        assert "admin@example.com" not in result

    def test_sanitize_credit_card(self):
        """Test credit card number sanitization."""
        text = "Card number 4532-1234-5678-9010 failed"
        result = DataSanitizer.sanitize(text, sanitize_cards=True)
        assert "[REDACTED_CARD]" in result
        assert "4532-1234" not in result

    def test_sanitize_database_connection_string(self):
        """Test database connection string sanitization."""
        text = "mysql://user:password@localhost:3306/mydb failed"
        result = DataSanitizer.sanitize(text, sanitize_db_strings=True)
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "mysql://user:password" not in result

    def test_sanitize_postgresql_connection(self):
        """Test PostgreSQL connection string sanitization."""
        text = "Error: postgres://admin:secretpass@db.local:5432/prod"
        result = DataSanitizer.sanitize(text, sanitize_db_strings=True)
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "admin:secretpass" not in result

    def test_sanitize_multiple_sensitive_data(self):
        """Test sanitization of multiple sensitive data types."""
        text = "User admin@example.com connected with password=secret123"
        result = DataSanitizer.sanitize(text)
        assert "admin@example.com" not in result
        assert "secret123" not in result
        assert "[REDACTED" in result

    def test_sanitize_json_password(self):
        """Test JSON-formatted password sanitization."""
        text = '{"password":"mySecretPassword123","username":"admin"}'
        result = DataSanitizer.sanitize(text)
        assert "mySecretPassword123" not in result
        assert "[REDACTED]" in result

    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        result = DataSanitizer.sanitize("")
        assert result == ""

    def test_sanitize_none(self):
        """Test sanitization of None."""
        result = DataSanitizer.sanitize(None)
        assert result == ""

    def test_sanitize_disabled_passwords(self):
        """Test that passwords aren't sanitized when disabled."""
        text = "password=secret123"
        result = DataSanitizer.sanitize(text, sanitize_passwords=False)
        assert "secret123" in result

    def test_sanitize_disabled_emails(self):
        """Test that emails aren't sanitized when disabled."""
        text = "user@example.com"
        result = DataSanitizer.sanitize(text, sanitize_emails=False)
        assert "user@example.com" in result

    def test_sanitize_output_with_masking(self):
        """Test sanitize_output convenience method with masking."""
        text = "Database password=mypass connected"
        result = DataSanitizer.sanitize_output(text, mask_sensitive=True)
        assert "mypass" not in result
        assert "[REDACTED]" in result

    def test_sanitize_output_without_masking(self):
        """Test sanitize_output with masking disabled."""
        text = "password=mypass123"
        result = DataSanitizer.sanitize_output(text, mask_sensitive=False)
        assert "mypass123" in result

    def test_sanitize_error_message(self):
        """Test error message sanitization."""
        exc = Exception("Connection failed: password=secret123")
        result = DataSanitizer.sanitize_error_message(exc)
        assert "secret123" not in result
        assert "[REDACTED]" in result

    def test_sanitize_error_message_none(self):
        """Test error message sanitization with None."""
        result = DataSanitizer.sanitize_error_message(None)
        assert result == ""

    def test_case_insensitive_password_matching(self):
        """Test case-insensitive password pattern matching."""
        text1 = "Password=secret"
        text2 = "PASSWORD=secret"
        text3 = "PaSsWoRd=secret"

        assert "[REDACTED]" in DataSanitizer.sanitize(text1)
        assert "[REDACTED]" in DataSanitizer.sanitize(text2)
        assert "[REDACTED]" in DataSanitizer.sanitize(text3)

    def test_case_insensitive_api_key_matching(self):
        """Test case-insensitive API key pattern matching."""
        text1 = "api_key=mykey"
        text2 = "API_KEY=mykey"
        text3 = "Api_Key=mykey"

        assert "[REDACTED]" in DataSanitizer.sanitize(text1)
        assert "[REDACTED]" in DataSanitizer.sanitize(text2)
        assert "[REDACTED]" in DataSanitizer.sanitize(text3)

    def test_quoted_password_values(self):
        """Test sanitization of quoted password values."""
        text1 = 'password="secret123"'
        text2 = "password='secret123'"
        text3 = 'password: "secret123"'

        assert "[REDACTED]" in DataSanitizer.sanitize(text1)
        assert "[REDACTED]" in DataSanitizer.sanitize(text2)
        assert "[REDACTED]" in DataSanitizer.sanitize(text3)

    def test_real_world_database_error(self):
        """Test real-world database error with connection string."""
        error_msg = (
            "ERROR: Connection to mysql://user:pass123@db.example.com:3306/prod failed. "
            "Check credentials at admin@example.com"
        )
        result = DataSanitizer.sanitize(error_msg)
        assert "pass123" not in result
        assert "user:pass123@db" not in result
        assert "admin@example.com" not in result
        assert "[REDACTED" in result

    def test_does_not_mask_ip_addresses(self):
        """Test that IP addresses are NOT masked (not sensitive data)."""
        text1 = "Server at 192.168.1.10"
        text2 = "API endpoint at 8.8.8.8"
        text3 = "Connect to localhost:8080"

        result1 = DataSanitizer.sanitize(text1)
        result2 = DataSanitizer.sanitize(text2)
        result3 = DataSanitizer.sanitize(text3)

        # IPs should NOT be masked
        assert "192.168.1.10" in result1
        assert "8.8.8.8" in result2
        assert "localhost" in result3


class TestCmdCheckSanitizationIntegration:
    """Test sanitization integration with cmdcheck."""

    def test_config_default_sanitization_enabled(self):
        """Test that sanitization is enabled by default in config."""
        from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig

        config = CmdCheckConfig()
        assert config.cmdcheck_sanitize_output is True

    def test_config_sanitization_can_be_disabled(self):
        """Test that sanitization can be disabled via config."""
        from kuma_sentinel.core.config.cmdcheck_config import CmdCheckConfig

        config = CmdCheckConfig()
        config.cmdcheck_sanitize_output = False
        assert config.cmdcheck_sanitize_output is False
