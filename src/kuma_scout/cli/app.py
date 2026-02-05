"""Typer CLI application for kuma scout."""

from importlib.metadata import version
from typing import Optional

import typer

__version__ = version("kuma-scout")
from kuma_scout.cli.generator import CLIGenerator


def version_callback(value: bool) -> None:
    """Handle --version flag."""
    if value:
        typer.echo(f"kuma-scout version {__version__}")
        raise typer.Exit()


app = typer.Typer(
    help="Kuma Scout - Extensible Monitoring Agent scout for Uptime Kuma.\n\nDeploy to servers, run checks, report system health back to push monitors.\nUse subcommands for specific checks: portscan, etc."
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version_flag: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        help="Show version and exit",
        is_eager=True,
    ),
):
    """
    Kuma Scout - Extensible monitoring agent for Uptime Kuma.

    Run monitoring checks and report results to Uptime Kuma's push API.
    """
    # If no command was provided, show error and suggest --help
    if ctx.invoked_subcommand is None and not version_flag:
        typer.echo("Error: No command provided.", err=True)
        typer.echo("", err=True)
        typer.echo("Use 'kuma-scout --help' to see available commands.", err=True)
        raise typer.Exit(code=1)


# Register  plugin-based commands
def _register_commands():
    """Register the new plugin-based commands."""
    generator = CLIGenerator()

    # Add run command
    run_cmd = generator.generate_run_command()
    app.command("run", help="Runs checks from a configuration file")(run_cmd)

    # Add list commands
    list_plugins_cmd = generator.generate_list_plugins_command()
    app.command("list-plugins", help="Lists available plugins")(list_plugins_cmd)

    list_checks_cmd = generator.generate_list_checks_command()
    app.command("list-checks", help="Lists checks available in a configuration file")(
        list_checks_cmd
    )

    # Add check subcommands for each plugin
    check_commands = generator.generate_check_commands()
    for plugin_type, check_cmd in check_commands:
        app.command(plugin_type, help=f"Execute a single {plugin_type} check")(
            check_cmd
        )


# Call registration
_register_commands()

# Create alias for compatibility
cli = app


if __name__ == "__main__":
    cli()
