"""Tests for HeartbeatService."""

from unittest.mock import Mock, patch

from kuma_sentinel.core.heartbeat import HeartbeatService


class TestHeartbeatService:
    """Test HeartbeatService class."""

    def test_heartbeat_init_defaults(self):
        """Test HeartbeatService initialization with defaults."""
        logger = Mock()

        service = HeartbeatService(logger, "http://localhost/api/push", "test_token")

        assert service.logger is logger
        assert service.uptime_kuma_url == "http://localhost/api/push"
        assert service.heartbeat_token == "test_token"
        assert service.interval == 300
        assert service.check_name == "Agent"
        assert service.thread is None

    def test_heartbeat_init_custom_values(self):
        """Test HeartbeatService initialization with custom values."""
        logger = Mock()

        service = HeartbeatService(
            logger,
            "http://kuma.example.com/api/push",
            "custom_token",
            interval=60,
            check_name="PortScan",
        )

        assert service.interval == 60
        assert service.check_name == "PortScan"

    def test_heartbeat_start_creates_thread(self):
        """Test start() creates and starts a daemon thread."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=300
        )

        with patch.object(service, "_ping_loop"):
            service.start()

            assert service.thread is not None
            assert service.thread.daemon is True

    def test_heartbeat_start_skip_negative_interval(self):
        """Test start() skips when interval <= 0."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=0
        )

        service.start()

        assert service.thread is None

    def test_heartbeat_start_skip_negative_interval_value(self):
        """Test start() skips when interval is negative."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=-1
        )

        service.start()

        assert service.thread is None

    def test_heartbeat_stop_waits_for_thread(self):
        """Test stop() signals thread to stop and waits."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=100
        )

        # Create a mock thread
        mock_thread = Mock()
        service.thread = mock_thread

        service.stop()

        # Verify stop event was set and thread was joined
        assert service.stop_event.is_set()
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_heartbeat_stop_handles_none_thread(self):
        """Test stop() handles case when thread is None."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=100
        )

        service.thread = None
        service.stop()  # Should not raise

        assert service.stop_event.is_set()

    def test_heartbeat_send_message_success(self):
        """Test send_message() sends push notification."""
        logger = Mock()

        service = HeartbeatService(logger, "http://localhost/api/push", "test_token")

        with patch("kuma_sentinel.core.heartbeat.send_push") as mock_send:
            mock_send.return_value = True

            result = service.send_message("Test message")

            assert result is True
            mock_send.assert_called_once()

    def test_heartbeat_send_message_failure(self):
        """Test send_message() handles push failure."""
        logger = Mock()

        service = HeartbeatService(logger, "http://localhost/api/push", "test_token")

        with patch("kuma_sentinel.core.heartbeat.send_push") as mock_send:
            mock_send.return_value = False

            result = service.send_message("Test message")

            assert result is False

    def test_heartbeat_send_message_uses_correct_parameters(self):
        """Test send_message() uses correct parameters."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", check_name="PortScan"
        )

        with patch("kuma_sentinel.core.heartbeat.send_push") as mock_send:
            mock_send.return_value = True

            service.send_message("Custom status")

            # Verify send_push was called with correct parameters
            call_args = mock_send.call_args
            assert call_args[0][0] is logger
            assert call_args[0][1] == "http://localhost/api/push"
            assert call_args[0][2] == "test_token"
            assert call_args[0][3] == "Custom status"
            assert call_args[1]["command"] == "heartbeat"

    def test_heartbeat_stop_event_initial_state(self):
        """Test stop_event is initially not set."""
        logger = Mock()

        service = HeartbeatService(logger, "http://localhost/api/push", "test_token")

        assert not service.stop_event.is_set()

    def test_heartbeat_multiple_start_calls(self):
        """Test calling start() multiple times creates new thread."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=100
        )

        with patch.object(service, "_ping_loop"):
            service.start()
            first_thread = service.thread

            service.start()
            second_thread = service.thread

            # Should create a new thread each time
            assert first_thread is not second_thread

    def test_heartbeat_zero_interval_prevents_thread(self):
        """Test interval of 0 prevents thread creation."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=0
        )

        with patch.object(service, "_ping_loop"):
            service.start()

            assert service.thread is None

    def test_heartbeat_ping_loop_basic_functionality(self):
        """Test _ping_loop basic functionality with mocked sleep."""
        logger = Mock()

        service = HeartbeatService(
            logger,
            "http://localhost/api/push",
            "test_token",
            interval=1,
            check_name="TestCheck",
        )

        with patch("kuma_sentinel.core.heartbeat.time.sleep") as mock_sleep:
            with patch.object(service, "send_message") as mock_send:
                mock_send.return_value = True

                # Simulate stop_event being set after first call
                def side_effect(*args):
                    service.stop_event.set()

                mock_sleep.side_effect = side_effect

                service.stop_event.clear()
                service._ping_loop()

                # Should have called sleep with interval
                mock_sleep.assert_called_with(1)

    def test_heartbeat_ping_loop_respects_stop_event(self):
        """Test _ping_loop stops when stop_event is set."""
        logger = Mock()

        service = HeartbeatService(
            logger, "http://localhost/api/push", "test_token", interval=100
        )

        service.stop_event.set()

        with patch.object(service, "send_message"):
            service._ping_loop()  # Should exit immediately

        assert service.stop_event.is_set()

    def test_heartbeat_message_includes_check_name(self):
        """Test message includes check name."""
        logger = Mock()

        service = HeartbeatService(
            logger,
            "http://localhost/api/push",
            "test_token",
            interval=1,
            check_name="KopiaCheck",
        )

        with patch("kuma_sentinel.core.heartbeat.time.sleep"):
            with patch.object(service, "send_message") as mock_send:
                mock_send.return_value = True

                def stop_after_sleep(*args):
                    service.stop_event.set()

                with patch(
                    "kuma_sentinel.core.heartbeat.time.sleep",
                    side_effect=stop_after_sleep,
                ):
                    service.stop_event.clear()
                    service._ping_loop()

                # Check that message includes check name
                if mock_send.called:
                    message = mock_send.call_args[0][0]
                    assert "KopiaCheck" in message

    def test_heartbeat_ping_loop_sends_formatted_message(self):
        """Test _ping_loop sends formatted message with check name."""
        logger = Mock()

        service = HeartbeatService(
            logger,
            "http://localhost/api/push",
            "test_token",
            interval=1,
            check_name="CustomCheck",
        )

        call_count = [0]

        def sleep_and_stop(*args):
            call_count[0] += 1
            if call_count[0] > 1:
                service.stop_event.set()

        with patch(
            "kuma_sentinel.core.heartbeat.time.sleep", side_effect=sleep_and_stop
        ):
            with patch.object(service, "send_message") as mock_send:
                mock_send.return_value = True
                service.stop_event.clear()
                service._ping_loop()

                # Verify message was sent
                assert mock_send.called
                message = mock_send.call_args[0][0]
                assert "check in progress" in message
                assert "CustomCheck" in message
