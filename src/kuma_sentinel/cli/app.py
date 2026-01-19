"""Click CLI application for kuma sentinel."""

from importlib.metadata import version

import click

__version__ = version("kuma-sentinel")
from kuma_sentinel.cli.commands.kopiasnapshotstatus import (
    KopiaSnapshotStatusCommand,
)
from kuma_sentinel.cli.commands.portscan import PortscanCommand


def print_version(ctx, param, value):
    """Print version and exit."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"kuma-sentinel version {__version__}")
    ctx.exit()


@click.group()
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version and exit",
)
@click.pass_context
def cli(ctx: click.Context):
    """Kuma Sentinel - Extensible Monitoring Agent.

    Monitor services and systems with reports to Uptime Kuma.
    Use subcommands for specific checks: portscan, etc.
    """
    ctx.ensure_object(dict)


# Register commands
portscan_cmd = PortscanCommand()
cli.add_command(portscan_cmd.register_command())

kopiasnapshotstatus_cmd = KopiaSnapshotStatusCommand()
cli.add_command(kopiasnapshotstatus_cmd.register_command())


if __name__ == "__main__":
    cli()
