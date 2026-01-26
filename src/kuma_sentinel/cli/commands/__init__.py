"""Sentinel commands."""

from typing import Dict, Type

# Registry for commands - used by app.py for auto-discovery
_COMMAND_REGISTRY: Dict[str, Type] = {}


def register_command(
    command_name: str, checker_class: Type, config_class: Type, help_text: str = ""
):
    """Decorator to register a command along with its checker and config.

    Stores command metadata as class attributes on the command class.
    The command is registered for app.py auto-discovery.

    Args:
        command_name: The command name (e.g., "portscan", "kopiasnapshotstatus")
        checker_class: The checker class for this command
        config_class: The config class for this command
        help_text: Help text for the command (displayed in CLI help)

    Returns:
        Decorator function
    """

    def decorator(command_cls: Type) -> Type:
        # Store command metadata as class attributes for direct access
        command_cls._command_name = command_name
        command_cls._help_text = help_text
        command_cls._checker_class = checker_class
        command_cls._config_class = config_class

        # Register command for app.py auto-discovery
        _COMMAND_REGISTRY[command_name] = command_cls

        return command_cls

    return decorator


# Imports trigger registration via the decorator
from kuma_sentinel.cli.commands.cmdcheck import CmdCheckCommand  # noqa: E402
from kuma_sentinel.cli.commands.kopiasnapshotstatus import (  # noqa: E402
    KopiaSnapshotStatusCommand,
)  # noqa: E402
from kuma_sentinel.cli.commands.portscan import PortscanCommand  # noqa: E402
from kuma_sentinel.cli.commands.zfspoolstatus import ZfsPoolStatusCommand  # noqa: E402

__all__ = [
    "CmdCheckCommand",
    "PortscanCommand",
    "KopiaSnapshotStatusCommand",
    "ZfsPoolStatusCommand",
    "register_command",
    "_COMMAND_REGISTRY",
]
