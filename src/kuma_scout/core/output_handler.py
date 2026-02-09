"""
Unified output handler for Kuma-Scout.

Handles both logging and optional Typer console output.
"""

from typing import Optional

from rich.console import Console
from rich.table import Table

from kuma_scout.core.logger import get_logger


class OutputHandler:
    """Handles logging and optional console output via Typer/Rich."""

    def __init__(self, console: Optional[Console] = None):
        self.logger = get_logger()
        self.console = console

    def info(self, message: str, echo: bool = False) -> None:
        """Log info message and optionally echo to console."""
        self.logger.info(message)
        if echo and self.console:
            self.console.print(message)

    def debug(self, message: str, echo: bool = False) -> None:
        """Log debug message and optionally echo to console."""
        self.logger.debug(message)
        if echo and self.console:
            self.console.print(message)

    def warning(self, message: str, echo: bool = False) -> None:
        """Log warning message and optionally echo to console."""
        self.logger.warning(message)
        if echo and self.console:
            self.console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str, echo: bool = False) -> None:
        """Log error message and optionally echo to console."""
        self.logger.error(message)
        if echo and self.console:
            self.console.print(f"[red]{message}[/red]")

    def print_table(self, table: Table, echo: bool = True) -> None:
        """Print a Rich table to console if echo is True."""
        if echo and self.console:
            self.console.print(table)
