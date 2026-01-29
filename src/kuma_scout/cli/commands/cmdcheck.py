"""Command check monitoring command."""

from typing import Callable, Dict, Optional

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_scout.core.config.cmdcheck_config import CmdCheckConfig


@register_command(
    "cmdcheck",
    checker_class=CmdCheckChecker,
    config_class=CmdCheckConfig,
    help_text="Execute arbitrary shell commands and report results to Uptime Kuma",
)
class CmdCheckCommand(CommandExecutor):
    """Command check monitoring using unified executor."""

    def get_builtin_command(self) -> Callable:
        """Build and return cmdcheck command function with Typer parameters.

        Note: CLI supports single command only. For multiple commands,
        use YAML configuration with cmdcheck.commands list.
        """

        def cmdcheck_cmd(
            config: Optional[str] = typer.Option(
                None,
                "--config",
                help="Configuration file path (e.g., /etc/kuma-scout/config.yaml)",
            ),
            log_file: Optional[str] = typer.Option(
                None, "--log-file", help="Log file path (e.g., /var/log/kuma-scout.log)"
            ),
            uptime_kuma_url: Optional[str] = typer.Option(
                None,
                "--uptime-kuma-url",
                help="Uptime Kuma API URL (e.g., http://uptimekuma:3001/api/push)",
            ),
            heartbeat_token: Optional[str] = typer.Option(
                None,
                "--heartbeat-token",
                help="Heartbeat token (env: KUMA_SCOUT_HEARTBEAT_TOKEN). Example: abc123xyz789",
            ),
            token: Optional[str] = typer.Option(
                None,
                "--token",
                help="Command check token (env: KUMA_SCOUT_CMDCHECK_TOKEN). Example: def456uvw012",
            ),
            ignore_file_permissions: bool = typer.Option(
                False,
                "--ignore-file-permissions",
                help="Skip config file permission validation (use only in development)",
            ),
            # SSH options
            ssh: Optional[str] = typer.Option(
                None,
                "--ssh",
                help="SSH shorthand (user@host or host). Examples: root@server or server",
            ),
            ssh_host: Optional[str] = typer.Option(
                None,
                "--ssh-host",
                help="SSH host to run command on (e.g., fileserver or 192.168.1.10)",
            ),
            ssh_user: Optional[str] = typer.Option(
                None,
                "--ssh-user",
                help="SSH username (default: current user)",
            ),
            ssh_port: int = typer.Option(
                22,
                "--ssh-port",
                help="SSH port (default: 22)",
            ),
            ssh_key_file: Optional[str] = typer.Option(
                None,
                "--ssh-key-file",
                help="Path to SSH private key",
            ),
            ssh_password: Optional[str] = typer.Option(
                None,
                "--ssh-password",
                help="SSH password (discouraged, use keys instead)",
            ),
            ssh_strict_host_key_checking: bool = typer.Option(
                True,
                "--ssh-strict-host-key-checking/--ssh-no-strict-host-key-checking",
                help="Enable/disable SSH strict host key checking (default: enabled)",
            ),
            command: Optional[str] = typer.Option(
                None,
                "--command",
                help="Shell command to execute (e.g., systemctl is-active nginx)",
            ),
            timeout: Optional[int] = typer.Option(
                None,
                "--timeout",
                help="Command timeout in seconds (e.g., 30, range: 1-300)",
            ),
            expect_exit_code: Optional[int] = typer.Option(
                None,
                "--expect-exit-code",
                help="Expected exit code for success (e.g., 0, range: 0-255)",
            ),
            success_pattern: Optional[str] = typer.Option(
                None,
                "--success-pattern",
                help="Regex pattern indicating success (e.g., active.*running)",
            ),
            failure_pattern: Optional[str] = typer.Option(
                None,
                "--failure-pattern",
                help="Regex pattern indicating failure (e.g., ERROR|FAILED)",
            ),
        ):
            """Execute arbitrary shell commands and report results to Uptime Kuma.

Examples:

  Check service status with config file (recommended for multiple commands):
  $ kuma-scout cmdcheck --config /etc/kuma-scout/config.yaml

  Check service status with CLI options:
  $ kuma-scout cmdcheck \\
      --command "systemctl is-active nginx" \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-cmdcheck-token

  Check with pattern matching (failure detection):
  $ kuma-scout cmdcheck \\
      --command "tail -n 100 /var/log/app.log" \\
      --failure-pattern "ERROR|CRITICAL|PANIC" \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-cmdcheck-token

  Check with custom timeout:
  $ kuma-scout cmdcheck \\
      --command "curl -s http://localhost" \\
      --timeout 30 \\
      --uptime-kuma-url http://uptimekuma:3001/api/push \\
      --heartbeat-token your-heartbeat-token \\
      --token your-cmdcheck-token
            """
            args = {
                "uptime_kuma_url": uptime_kuma_url,
                "heartbeat_token": heartbeat_token,
                "token": token,
                "config": config,
                "log_file": log_file,
                "ignore_file_permissions": ignore_file_permissions,
                # SSH options
                "ssh": ssh,
                "ssh_host": ssh_host,
                "ssh_user": ssh_user,
                "ssh_port": ssh_port,
                "ssh_key_file": ssh_key_file,
                "ssh_password": ssh_password,
                "ssh_strict_host_key_checking": ssh_strict_host_key_checking,
                "command": command,
                "timeout": timeout,
                "expect_exit_code": expect_exit_code,
                "success_pattern": success_pattern,
                "failure_pattern": failure_pattern,
            }
            self.execute_with_orchestration(args)

        return cmdcheck_cmd

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "🎯 Execution Target": {
                "Target": "execution_target",
            },
            "🔧 Command Configuration": {
                "Total Commands": "cmdcheck_total_commands",
                "Timeout": "cmdcheck_timeout",
                "Expected Exit Code": "cmdcheck_expect_exit_code",
                "Success Pattern": "cmdcheck_success_pattern",
                "Failure Pattern": "cmdcheck_failure_pattern",
            },
            "� Logging Configuration": {
                "Log File": "log_file",
                "Log Level": "log_level",
            },
            "�🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
