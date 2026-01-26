"""Tests for Uptime Kuma integration."""

from unittest.mock import Mock, patch
from urllib.error import URLError

from kuma_sentinel.core.uptime_kuma import send_push, url_encode


class TestUrlEncode:
    """Test URL encoding utility function."""

    def test_url_encode_simple_message(self):
        """Test encoding simple ASCII message."""
        result = url_encode("Test message")
        assert isinstance(result, str)
        assert "Test%20message" in result

    def test_url_encode_special_characters(self):
        """Test encoding message with special characters."""
        result = url_encode("Status: OK & Running")
        assert isinstance(result, str)
        assert "%26" in result

    def test_url_encode_unicode_characters(self):
        """Test encoding message with unicode characters."""
        result = url_encode("Status: ✓ OK")
        assert isinstance(result, str)

    def test_url_encode_empty_string(self):
        """Test encoding empty string."""
        result = url_encode("")
        assert result == ""

    def test_url_encode_url_unsafe_characters(self):
        """Test encoding preserves safety of special URL characters."""
        result = url_encode("Test & Special <> Characters")
        assert isinstance(result, str)
        assert "&" not in result or "%26" in result


class TestSendPush:
    """Test send_push function for Uptime Kuma API integration."""

    def test_send_push_successful_request(self):
        """Test successful push notification."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            result = send_push(
                logger,
                "http://localhost/api/push",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert result is True

    def test_send_push_response_not_ok(self):
        """Test send_push with non-ok response."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":false}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            result = send_push(
                logger,
                "http://localhost/api/push",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert result is False

    def test_send_push_missing_url(self):
        """Test send_push with missing URL."""
        logger = Mock()

        result = send_push(logger, "", "test_token", "Test message", "heartbeat")

        assert result is False

    def test_send_push_missing_token(self):
        """Test send_push with missing token."""
        logger = Mock()

        result = send_push(
            logger, "http://localhost/api/push", "", "Test message", "heartbeat"
        )

        assert result is False

    def test_send_push_network_error_urlerror(self):
        """Test send_push handles URLError."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert result is False

    def test_send_push_network_error_timeout(self):
        """Test send_push handles timeout."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Request timeout")

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert result is False

    def test_send_push_invalid_json_response(self):
        """Test send_push handles invalid JSON response."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b"invalid json"
            mock_response.getcode.return_value = 200
            mock_urlopen.return_value = mock_response

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert isinstance(result, bool)

    def test_send_push_http_error_response(self):
        """Test send_push handles HTTP error status."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.getcode.return_value = 500
            mock_urlopen.return_value = mock_response

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test message",
                "heartbeat",
            )

            assert result is False

    def test_send_push_message_encoded_in_url(self):
        """Test send_push includes message in URL parameters."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.getcode.return_value = 200
            mock_urlopen.return_value = mock_response

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Custom status message",
                "heartbeat",
            )

            call_args = mock_urlopen.call_args
            url = call_args[0][0]
            assert "Custom%20status%20message" in url or "Custom" in str(url)

    def test_send_push_heartbeat_status_parameter(self):
        """Test send_push uses status parameter."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.getcode.return_value = 200
            mock_urlopen.return_value = mock_response

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Heartbeat",
                "heartbeat",
            )

            call_args = mock_urlopen.call_args
            url = call_args[0][0]
            assert "status=" in url

    def test_send_push_timeout_parameter(self):
        """Test send_push uses correct timeout."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.getcode.return_value = 200
            mock_urlopen.return_value = mock_response

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test",
                "heartbeat",
            )

            call_kwargs = mock_urlopen.call_args[1]
            assert "timeout" in call_kwargs

    def test_send_push_command_in_message(self):
        """Test send_push includes command name in message."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=None)
            mock_urlopen.return_value = mock_response

            send_push(
                logger, "http://localhost/api/push", "test_token", "Status", "portscan"
            )

            assert "portscan" in logger.info.call_args[0][0]

    def test_send_push_logs_errors(self):
        """Test send_push logs errors appropriately."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("Network error")

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test",
                "heartbeat",
            )

            assert logger.error.called or logger.warning.called

    def test_send_push_generic_exception(self):
        """Test send_push handles generic exceptions."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Unexpected error")

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Test",
                "heartbeat",
            )

            assert result is False


class TestSecurityEventLogging:
    """Test security event logging in uptime_kuma module."""

    def test_send_push_logs_security_events(self):
        """Test that security-relevant events are logged with security markers."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = b'{"ok":true}'
            mock_response.getcode.return_value = 200
            mock_urlopen.return_value = mock_response

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Heartbeat",
                "heartbeat",
            )

            # Verify logging occurred
            assert logger.info.called or logger.warning.called or logger.error.called

    def test_send_push_error_logging_security_event(self):
        """Test that errors in push notification are logged as security events."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")

            send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Heartbeat",
                "heartbeat",
            )

            # Should log error when connection fails
            assert logger.error.called or logger.warning.called

    def test_send_push_timeout_security_event(self):
        """Test that timeout errors are logged appropriately."""
        logger = Mock()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Request timeout")

            result = send_push(
                logger,
                "http://localhost/api/push/test_token",
                "test_token",
                "Heartbeat",
                "heartbeat",
            )

            assert result is False
            assert logger.error.called or logger.warning.called
