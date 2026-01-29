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

        common_options = self.get_common_options()

        def cmdcheck_cmd(
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
            config: Optional[str] = common_options["config"],
            uptime_kuma_url: Optional[str] = common_options["uptime_kuma_url"],
            heartbeat_token: Optional[str] = common_options["heartbeat_token"],
            token: Optional[str] = common_options["token"],
            ignore_file_permissions: bool = common_options["ignore_file_permissions"],
            ssh: Optional[str] = common_options["ssh"],
            ssh_key_file: Optional[str] = common_options["ssh_key_file"],
            ssh_password: Optional[str] = common_options["ssh_password"],
            ssh_strict_host_key_checking: bool = common_options[
                "ssh_strict_host_key_checking"
            ],
            log_file: Optional[str] = common_options["log_file"],
            log_level: Optional[str] = common_options["log_level"],
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
                "log_level": log_level,
                "ignore_file_permissions": ignore_file_permissions,
                # SSH options
                "ssh": ssh,
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
