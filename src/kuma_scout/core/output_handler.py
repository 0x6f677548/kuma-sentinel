"""
Unified output handler for Kuma-Scout.

Handles both logging and optional Typer console output.
Automatically enriches logs with execution context when available.
"""

import json
from typing import Optional

from rich.console import Console
from rich.table import Table

from kuma_scout.core.execution_context import get_execution_context
from kuma_scout.core.logger import get_logger


class OutputHandler:
    """Handles logging and optional console output via Typer/Rich.

    Automatically enriches logs with execution context (check name, plugin type)
    when available via get_execution_context().
    """

    def __init__(self, console: Optional[Console] = None, quiet: bool = False):
        self.logger = get_logger()
        self.console = console
        self.quiet = quiet

    def _enrich_message(self, message: str) -> str:
        """Enrich message with execution context if available.

        Prepends check name and plugin type to message if execution context exists.

        Args:
            message: Original message

        Returns:
            Message optionally enriched with context prefix
        """
        context = get_execution_context()
        if context:
            return f"[{context.plugin_type}:{context.check_name}] {message}"
        return message

    def _get_full_context_details(self) -> Optional[str]:
        """Get full execution context details for troubleshooting.

        Returns:
            JSON string with context details if context exists, None otherwise
        """
        context = get_execution_context()
        if not context:
            return None

        details = {
            "check_name": context.check_name,
            "plugin_type": context.plugin_type,
            "elapsed_seconds": round(context.elapsed_seconds, 2),
            "start_time": context.start_time,
            "config": context.config_snapshot,
        }
        return json.dumps(details, separators=(",", ":"))

    def info(self, message: str, echo: bool = False) -> None:
        """Log info message and optionally echo to console.

        In quiet mode, console output is suppressed.
        """
        enriched = self._enrich_message(message)
        self.logger.info(enriched)
        if echo and self.console and not self.quiet:
            self.console.print(message)

    def debug(self, message: str, echo: bool = False) -> None:
        """Log debug message and optionally echo to console.

        In quiet mode, console output is suppressed.
        """
        enriched = self._enrich_message(message)
        self.logger.debug(enriched)
        if echo and self.console and not self.quiet:
            self.console.print(message)

    def warning(self, message: str, echo: bool = False) -> None:
        """Log warning message with full context and optionally echo to console.

        When execution context is available, includes full context details (timing,
        config, etc.) to aid troubleshooting.
        In quiet mode, console output is suppressed.
        """
        enriched = self._enrich_message(message)
        context_details = self._get_full_context_details()

        if context_details:
            log_message = f"{enriched} | context: {context_details}"
        else:
            log_message = enriched

        self.logger.warning(log_message)
        if echo and self.console and not self.quiet:
            self.console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str, echo: bool = False) -> None:
        """Log error message with full context and optionally echo to console.

        When execution context is available, includes full context details (timing,
        config, etc.) to aid troubleshooting.
        In quiet mode, console output is suppressed.
        """
        enriched = self._enrich_message(message)
        context_details = self._get_full_context_details()

        if context_details:
            log_message = f"{enriched} | context: {context_details}"
        else:
            log_message = enriched

        self.logger.error(log_message)
        if echo and self.console and not self.quiet:
            self.console.print(f"[red]{message}[/red]")

    def print_table(self, table: Table, echo: bool = True) -> None:
        """Print a Rich table to console if echo is True.

        In quiet mode, console output is suppressed.
        """
        if echo and self.console and not self.quiet:
            self.console.print(table)
