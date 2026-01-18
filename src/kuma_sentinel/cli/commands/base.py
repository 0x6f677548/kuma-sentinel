"""Abstract base class for sentinel CLI commands."""

from abc import ABC, abstractmethod

import click


class Command(ABC):
    """Base class for sentinel CLI commands.

    Subclasses should implement register_command() to return a Click command.
    """

    @abstractmethod
    def register_command(self) -> click.Command:
        """Register and return a Click command.

        Returns:
            A Click Command object
        """
        pass
