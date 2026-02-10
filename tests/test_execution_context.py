"""Tests for execution context management and structured error logging."""

from kuma_scout.core.execution_context import (
    ExecutionContext,
    clear_execution_context,
    execution_context_manager,
    get_execution_context,
    set_execution_context,
)
from kuma_scout.core.output_handler import OutputHandler


class TestExecutionContext:
    """Test execution context management."""

    def test_execution_context_initialization(self):
        """Test creating an ExecutionContext."""
        context = ExecutionContext(
            check_name="test-check",
            plugin_type="cmdcheck",
            config_snapshot={"timeout": 30},
            start_time=1000.0,
        )

        assert context.check_name == "test-check"
        assert context.plugin_type == "cmdcheck"
        assert context.config_snapshot == {"timeout": 30}

    def test_execution_context_elapsed_seconds(self):
        """Test elapsed_seconds property."""
        import time

        context = ExecutionContext(
            check_name="test-check",
            plugin_type="cmdcheck",
            config_snapshot={},
            start_time=time.time() - 5.5,  # 5.5 seconds ago
        )

        elapsed = context.elapsed_seconds
        assert 5 < elapsed < 6  # Allow for execution time variance

    def test_execution_context_to_dict(self):
        """Test converting context to dictionary."""
        context = ExecutionContext(
            check_name="test-check",
            plugin_type="cmdcheck",
            config_snapshot={"timeout": 30},
            start_time=1000.0,
        )

        ctx_dict = context.to_dict()
        assert ctx_dict["check_name"] == "test-check"
        assert ctx_dict["plugin_type"] == "cmdcheck"
        assert ctx_dict["config_snapshot"] == {"timeout": 30}
        assert "start_time" in ctx_dict

    def test_set_and_get_execution_context(self):
        """Test setting and getting execution context."""
        clear_execution_context()
        assert get_execution_context() is None

        context = ExecutionContext(
            check_name="test-check",
            plugin_type="cmdcheck",
            config_snapshot={},
            start_time=1000.0,
        )
        set_execution_context(context)
        retrieved = get_execution_context()

        assert retrieved is context
        assert retrieved.check_name == "test-check"

        clear_execution_context()
        assert get_execution_context() is None

    def test_execution_context_manager(self):
        """Test execution_context_manager context manager."""
        clear_execution_context()

        with execution_context_manager(
            check_name="my-check",
            plugin_type="portscan",
            config_snapshot={"port": 8080},
        ):
            # Inside context, should have the context set
            retrieved = get_execution_context()
            assert retrieved is not None
            assert retrieved.check_name == "my-check"
            assert retrieved.plugin_type == "portscan"

        # Outside context, should be cleared
        assert get_execution_context() is None

    def test_execution_context_manager_with_exception(self):
        """Test that context is cleared even when exception occurs."""
        clear_execution_context()

        try:
            with execution_context_manager(
                check_name="error-check",
                plugin_type="cmdcheck",
            ):
                # Verify context is set inside the manager
                assert get_execution_context() is not None
                raise ValueError("Test error")
        except ValueError:
            pass

        # Context should be cleared even after exception
        assert get_execution_context() is None

    def test_nested_execution_contexts(self):
        """Test that nested contexts override each other properly."""
        clear_execution_context()

        with execution_context_manager(
            check_name="outer-check",
            plugin_type="cmdcheck",
        ):
            outer_ctx = get_execution_context()
            assert outer_ctx is not None
            assert outer_ctx.check_name == "outer-check"

            with execution_context_manager(
                check_name="inner-check",
                plugin_type="portscan",
            ):
                inner_ctx = get_execution_context()
                assert inner_ctx is not None
                assert inner_ctx.check_name == "inner-check"

            # After inner context exits, the outer context is cleared as well
            # because we clear in the finally block - this is expected behavior
            # as each context manager is independent
            cleared = get_execution_context()
            assert cleared is None

        # Should clear on complete exit
        assert get_execution_context() is None


class TestOutputHandlerWithContext:
    """Test OutputHandler enriches logs with execution context."""

    def test_output_handler_without_context(self, caplog):
        """Test OutputHandler logs without context when none is set."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.INFO)

        handler = OutputHandler()
        handler.info("Test message")

        # Should log message without context enrichment
        assert "Test message" in caplog.text

    def test_output_handler_with_context_info(self, caplog):
        """Test OutputHandler enriches info logs with context."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.INFO)

        with execution_context_manager(
            check_name="my-check",
            plugin_type="cmdcheck",
        ):
            handler = OutputHandler()
            handler.info("Check is running")

        # Should log with context enrichment
        assert "[cmdcheck:my-check]" in caplog.text
        assert "Check is running" in caplog.text

    def test_output_handler_with_context_debug(self, caplog):
        """Test OutputHandler enriches debug logs with context."""
        import logging

        clear_execution_context()
        # Get the kuma_scout logger and set level to DEBUG
        logger = logging.getLogger("kuma_scout")
        original_level = logger.level
        logger.setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG)

        try:
            with execution_context_manager(
                check_name="debug-check",
                plugin_type="portscan",
            ):
                handler = OutputHandler()
                handler.debug("Debug info")

            # Should log with context enrichment
            assert "[portscan:debug-check]" in caplog.text
            assert "Debug info" in caplog.text
        finally:
            logger.setLevel(original_level)

    def test_output_handler_with_context_warning(self, caplog):
        """Test OutputHandler enriches warning logs with context."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.WARNING)

        with execution_context_manager(
            check_name="warn-check",
            plugin_type="cmdcheck",
        ):
            handler = OutputHandler()
            handler.warning("Warning message")

        # Should log with context enrichment
        assert "[cmdcheck:warn-check]" in caplog.text
        assert "Warning message" in caplog.text

    def test_output_handler_with_context_error(self, caplog):
        """Test OutputHandler enriches error logs with context."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.ERROR)

        with execution_context_manager(
            check_name="error-check",
            plugin_type="zfs",
        ):
            handler = OutputHandler()
            handler.error("Error occurred")

        # Should log with context enrichment
        assert "[zfs:error-check]" in caplog.text
        assert "Error occurred" in caplog.text

    def test_output_handler_enrich_message_method(self):
        """Test _enrich_message method directly."""
        clear_execution_context()

        handler = OutputHandler()

        # Without context
        message = handler._enrich_message("Test message")
        assert message == "Test message"

        # With context
        with execution_context_manager(
            check_name="test",
            plugin_type="type",
        ):
            message = handler._enrich_message("Test message")
            assert message == "[type:test] Test message"

    def test_output_handler_full_context_in_warning(self, caplog):
        """Test OutputHandler includes full context details in warning logs."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.WARNING)

        with execution_context_manager(
            check_name="warn-check",
            plugin_type="cmdcheck",
            config_snapshot={"timeout": 30, "retry_attempts": 1},
        ):
            handler = OutputHandler()
            handler.warning("Check timed out")

        # Should include full context details in JSON format
        assert "[cmdcheck:warn-check]" in caplog.text
        assert "Check timed out" in caplog.text
        assert "context:" in caplog.text
        assert "warn-check" in caplog.text
        assert "cmdcheck" in caplog.text
        assert "timeout" in caplog.text

    def test_output_handler_full_context_in_error(self, caplog):
        """Test OutputHandler includes full context details in error logs."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.ERROR)

        with execution_context_manager(
            check_name="error-check",
            plugin_type="portscan",
            config_snapshot={"port": 8080, "timeout": 60},
        ):
            handler = OutputHandler()
            handler.error("Connection refused")

        # Should include full context details in JSON format
        assert "[portscan:error-check]" in caplog.text
        assert "Connection refused" in caplog.text
        assert "context:" in caplog.text
        assert "error-check" in caplog.text
        assert "portscan" in caplog.text
        assert "port" in caplog.text

    def test_output_handler_no_context_in_warning(self, caplog):
        """Test OutputHandler warning without context."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.WARNING)

        handler = OutputHandler()
        handler.warning("Warning without context")

        # Should log message without context details
        assert "Warning without context" in caplog.text
        assert "context:" not in caplog.text

    def test_output_handler_no_context_in_error(self, caplog):
        """Test OutputHandler error without context."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.ERROR)

        handler = OutputHandler()
        handler.error("Error without context")

        # Should log message without context details
        assert "Error without context" in caplog.text
        assert "context:" not in caplog.text


class TestContextManagerIsolation:
    """Test that execution context is properly isolated between different execution paths."""

    def test_sequential_contexts_dont_interfere(self, caplog):
        """Test that sequential execution contexts don't interfere."""
        import logging

        clear_execution_context()
        caplog.set_level(logging.INFO)

        with execution_context_manager("check1", "type1"):
            handler = OutputHandler()
            handler.info("Message from check1")

        with execution_context_manager("check2", "type2"):
            handler = OutputHandler()
            handler.info("Message from check2")

        # Verify both messages have their correct context
        assert "[type1:check1]" in caplog.text
        assert "[type2:check2]" in caplog.text

    def test_context_not_leaked_between_tests(self):
        """Ensure context is properly isolated for concurrent or sequential tests."""
        # First execution
        clear_execution_context()
        with execution_context_manager("first", "type1"):
            ctx = get_execution_context()
            assert ctx is not None
            assert ctx.check_name == "first"
        assert get_execution_context() is None

        # Second execution (should not see first context)
        with execution_context_manager("second", "type2"):
            ctx = get_execution_context()
            assert ctx is not None
            assert ctx.check_name == "second"
        assert get_execution_context() is None
