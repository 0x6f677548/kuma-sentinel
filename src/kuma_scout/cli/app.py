"""Typer CLI application for kuma scout."""

from importlib.metadata import version
from typing import Optional

import typer

__version__ = version("kuma-scout")
from kuma_scout.cli.commands import _COMMAND_REGISTRY
from kuma_scout.cli.generator import CLIGenerator
from kuma_scout.cli.state import state


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
    log_level: str = typer.Option("INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)"),
    log_file: Optional[str] = typer.Option(None, "--log-file", help="Log file path"),
    uptime_kuma_url: Optional[str] = typer.Option(None, "--uptime-kuma-url", help="Uptime Kuma push API URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Uptime Kuma push token"),
    heartbeat_token: Optional[str] = typer.Option(None, "--heartbeat-token", help="Uptime Kuma token for heartbeat"),
    timeout: int = typer.Option(300, "--timeout", help="Global timeout for checks (seconds)"),
    ssh: Optional[str] = typer.Option(None, "--ssh", help="SSH host (user@host or host)"),
    ssh_key_file: Optional[str] = typer.Option(None, "--ssh-key-file", help="SSH private key file path"),
    ssh_password: Optional[str] = typer.Option(None, "--ssh-password", help="SSH password"),
    ssh_strict_host_key_checking: bool = typer.Option(True, "--ssh-strict-host-key-checking", help="Enable strict SSH host key checking"),
    ssh_no_strict_host_key_checking: bool = typer.Option(False, "--ssh-no-strict-host-key-checking", help="Disable strict SSH host key checking"),
    ignore_file_permissions: bool = typer.Option(False, "--ignore-file-permissions", help="Ignore file permission checks on config files"),
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

    state["log_level"] = log_level
    state["log_file"] = log_file
    state["uptime_kuma_url"] = uptime_kuma_url
    state["uptime_kuma_token"] = token
    state["heartbeat_token"] = heartbeat_token
    state["timeout"] = timeout
    state["ssh_host"] = ssh
    state["ssh_key_file"] = ssh_key_file
    state["ssh_password"] = ssh_password
    state["ssh_strict_host_key_checking"] = ssh_strict_host_key_checking and not ssh_no_strict_host_key_checking
    state["ignore_file_permissions"] = ignore_file_permissions


# Register commands at function definition time
def _register_commands():
    """Register all commands from the registry."""
    for cmd_name, command_class in sorted(_COMMAND_REGISTRY.items()):
        cmd_instance = command_class()
        registered_cmd = cmd_instance.register_command()
        # Use the function's docstring if available, otherwise use the class help text
        help_text = registered_cmd.__doc__ or command_class._help_text
        app.command(name=cmd_name, help=help_text)(registered_cmd)


# Register new plugin-based commands
def _register_new_commands():
    """Register the new plugin-based commands."""
    generator = CLIGenerator()

    # Add run command
    run_cmd = generator.generate_run_command()
    app.command("run", help="Run checks from a configuration file")(run_cmd)

    # Add list command
    list_cmd = generator.generate_list_command()
    app.command("list", help="List available plugins or checks in a config file")(
        list_cmd
    )

    # Add check subcommands for each plugin
    check_commands = generator.generate_check_commands()
    for plugin_type, check_cmd in check_commands:
        app.command(plugin_type, help=f"Execute a single {plugin_type} check")(check_cmd)


# Call registration
# _register_commands()  # Disabled during Phase 2 migration
_register_new_commands()

# Create alias for compatibility
cli = app


if __name__ == "__main__":
    cli()
