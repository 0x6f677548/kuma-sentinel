"""
Execution context management for structured error logging.

Uses Python's contextvars to manage execution context (check name, type, config)
throughout check execution without needing to pass context through function calls.
This allows output handlers and error handlers to automatically enrich logs with
contextual information.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class ExecutionContext:
    """Holds execution context for a check.

    This context is stored in a ContextVar so it's accessible throughout
    the entire check execution chain without passing it as an argument.

    Attributes:
        check_name: Name of the check being executed
        plugin_type: Type of plugin (e.g., "cmdcheck", "portscan")
        config_snapshot: Sanitized copy of check config for error context
        start_time: Unix timestamp when check started
    """

    check_name: str
    plugin_type: str
    config_snapshot: Dict[str, Any]
    start_time: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return asdict(self)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since execution started."""
        return time.time() - self.start_time


# Module-level ContextVar to store execution context
_execution_context: ContextVar[Optional[ExecutionContext]] = ContextVar(
    "execution_context", default=None
)


def get_execution_context() -> Optional[ExecutionContext]:
    """Get the current execution context, if any.

    Returns:
        ExecutionContext if currently executing a check, None otherwise
    """
    return _execution_context.get()


def set_execution_context(context: ExecutionContext) -> None:
    """Set the execution context.

    Args:
        context: ExecutionContext to set
    """
    _execution_context.set(context)


def clear_execution_context() -> None:
    """Clear the execution context."""
    _execution_context.set(None)


@contextmanager
def execution_context_manager(
    check_name: str,
    plugin_type: str,
    config_snapshot: Optional[Dict[str, Any]] = None,
):
    """Context manager for setting and clearing execution context.

    Usage:
        with execution_context_manager("my-check", "cmdcheck", config_dict):
            # code that executes the check
            # execution context is automatically available via get_execution_context()
            pass

    Args:
        check_name: Name of the check
        plugin_type: Type of plugin
        config_snapshot: Optional sanitized config dictionary for context

    Yields:
        The ExecutionContext that was set
    """
    context = ExecutionContext(
        check_name=check_name,
        plugin_type=plugin_type,
        config_snapshot=config_snapshot or {},
        start_time=time.time(),
    )
    set_execution_context(context)
    try:
        yield context
    finally:
        clear_execution_context()
