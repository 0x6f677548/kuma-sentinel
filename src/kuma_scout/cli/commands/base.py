"""Abstract base class for scout CLI commands."""

from abc import ABC, abstractmethod
from typing import Callable


class Command(ABC):
    """Base class for scout CLI commands.

    Subclasses should implement register_command() to return a Typer-compatible command function.
    """

    @abstractmethod
    def register_command(self) -> Callable:
        """Register and return a Typer-compatible command function.

        Returns:
            A callable function that Typer can register as a command
        """
        pass
