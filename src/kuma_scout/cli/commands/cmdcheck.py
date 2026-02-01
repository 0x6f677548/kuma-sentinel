"""Command check monitoring command."""

from typing import Callable, Dict, Optional

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.cmdcheck_checker import CmdCheckChecker
from kuma_scout.core.config.cmdcheck_config import CmdCheckConfig
from kuma_scout.core.uptime_kuma import send_push


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
            retry_count: Optional[int] = common_options["retry_count"],
            retry_delay: Optional[int] = common_options["retry_delay"],
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
                "retry_count": retry_count,
                "retry_delay": retry_delay,
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

    def send_result_alert(
        self,
        logger,
        cfg,
        command_name: str,
        result,
        duration_ms: int,
    ) -> None:
        """Send result alerts, handling per-command tokens and aggregated results."""

        # Check if we have per-command results with tokens
        command_results = result.details.get("commands", [])
        has_per_command_tokens = any(cmd.get("token") for cmd in command_results)

        if has_per_command_tokens:
            # Send individual pushes only for commands that have per-command tokens
            for cmd_result in command_results:
                token = cmd_result.get("token")
                if token:  # Only send individual push if command has its own token
                    message = f"[{cmd_result['name']}] {cmd_result['output']}"
                    send_push(
                        logger=logger,
                        uptime_kuma_url=cfg.uptime_kuma_url,
                        push_token=token,
                        message=message,
                        command=f"{command_name}_{cmd_result['name']}",
                        status=cmd_result["status"],
                        ping_ms=int(cmd_result["duration_seconds"] * 1000),
                    )

            # Send aggregated push if global token exists
            if cfg.command_token:
                send_push(
                    logger=logger,
                    uptime_kuma_url=cfg.uptime_kuma_url,
                    push_token=cfg.command_token,
                    message=result.message,
                    command=command_name,
                    status=result.status,
                    ping_ms=duration_ms,
                )
        else:
            # Fallback to default behavior
            super().send_result_alert(logger, cfg, command_name, result, duration_ms)
