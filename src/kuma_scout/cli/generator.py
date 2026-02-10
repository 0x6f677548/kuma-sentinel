"""CLI generator for the new plugin-based architecture."""

import inspect
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.table import Table

import kuma_scout
from kuma_scout.cli.config_merger import ConfigMerger
from kuma_scout.core.config_loader import load_config
from kuma_scout.core.execution_context import execution_context_manager
from kuma_scout.core.logger import setup_default_logging, setup_logging
from kuma_scout.core.models import CheckResult
from kuma_scout.core.output_handler import OutputHandler
from kuma_scout.core.uptime_kuma import send_push
from kuma_scout.core.utils.sanitizer import DataSanitizer
from kuma_scout.core.utils.ssh_runner import SSHRunner, parse_ssh_connection_string
from kuma_scout.plugins import get_all_plugins
from kuma_scout.plugins.models import GlobalConfig, UptimeKumaConfig

if TYPE_CHECKING:
    pass


class CLIGenerator:
    """Generates CLI commands for the new plugin architecture."""

    def _compute_aggregated_result(
        self, results: list, tag_name: str
    ) -> Tuple[str, str, int]:
        """
        Compute aggregated result for a tag.

        Args:
            results: List of CheckResult objects belonging to this tag
            tag_name: Name of the tag for logging

        Returns:
            Tuple of (status, message, duration_ms)
        """
        if not results:
            return "up", f"Tag '{tag_name}': no checks executed", 0

        # Status is "down" if ANY check is down
        overall_status = "down" if any(r.status == "down" for r in results) else "up"

        # Create detailed breakdown
        up_checks = [r.check_name for r in results if r.status == "up"]
        down_checks = [r.check_name for r in results if r.status == "down"]

        check_details = []
        if up_checks:
            quoted_up = [f"'{name}'" for name in up_checks]
            check_details.append(f"UP: {', '.join(quoted_up)}")
        if down_checks:
            quoted_down = [f"'{name}'" for name in down_checks]
            check_details.append(f"DOWN: {', '.join(quoted_down)}")

        message = f"Tag '{tag_name}' [{len(up_checks)}/{len(results)} healthy] - {'; '.join(check_details)}"

        # Total duration is sum of all check durations
        total_duration_ms = sum(r.duration_seconds for r in results) * 1000

        return overall_status, message, int(total_duration_ms)

    def _setup_run_command(
        self,
        config: str,
        ignore_file_permissions: bool,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        heartbeat_token: Optional[str],
        timeout: int,
        log_file: Optional[str],
        log_level: Optional[str],
        ssh: Optional[str],
        ssh_key_file: Optional[str],
        ssh_password: Optional[str],
        ssh_strict_host_key_checking: bool,
        ssh_no_strict_host_key_checking: bool,
        quiet: bool = False,
        verbose: bool = False,
    ) -> tuple:
        """Setup phase for run command: logging, config loading, overrides, SSH."""
        # Initialize default logging first
        setup_default_logging()

        # Create output handler for unified logging and echoing
        output_handler = OutputHandler(Console(), quiet=quiet)

        # Log program version
        output_handler.info(f"Kuma Scout v{kuma_scout.__version__} starting", echo=True)

        # Load config with global options
        try:
            global_config, checks = load_config(
                config, ignore_file_permissions=ignore_file_permissions
            )
        except ValueError as e:
            output_handler.error(f"Configuration error: {e}", echo=True)
            raise typer.Exit(1) from e

        # Apply command-line overrides
        self._apply_command_line_overrides(
            global_config,
            uptime_kuma_url,
            token,
            heartbeat_token,
            timeout,
            log_file,
            log_level,
            quiet,
            verbose,
        )

        # Merge uptime_kuma configs for all checks with global config (field-level merging)
        ConfigMerger.merge_all_checks_configs(checks, global_config)

        # Merge all tag configs with global config (field-level merging)
        ConfigMerger.merge_all_tags_configs(global_config)

        # Update logging configuration with final config values
        setup_logging(
            global_config.logging.file,
            global_config.logging.level,
            verbose=global_config.verbose,
        )

        # Setup SSH configuration
        self._setup_ssh_config(
            global_config,
            ssh,
            ssh_key_file,
            ssh_password,
            ssh_strict_host_key_checking,
            ssh_no_strict_host_key_checking,
            output_handler,
        )

        return output_handler, global_config, checks

    def _handle_dry_run(
        self,
        output_handler,
        filtered_checks: list,
        config: str,
        tag: Optional[List[str]],
        name: Optional[List[str]],
        plugin_type: Optional[List[str]],
        exclude: Optional[List[str]],
    ) -> None:
        """Handle dry run mode - show what would be executed."""
        output_handler.info(f"Configuration: {config}", echo=True)
        if tag:
            output_handler.info(f"Tag filters: {', '.join(tag)}", echo=True)
        if name:
            output_handler.info(f"Name filters: {', '.join(name)}", echo=True)
        if plugin_type:
            output_handler.info(f"Type filters: {', '.join(plugin_type)}", echo=True)
        if exclude:
            output_handler.info(f"Excluding checks: {', '.join(exclude)}", echo=True)
        output_handler.info(
            f"Found {len(filtered_checks)} check(s) to execute", echo=True
        )

        output_handler.info("Dry run - would execute the following checks:", echo=True)
        for check_type, check_config in filtered_checks:
            tags_str = (
                f" [tags: {', '.join(check_config.get('tags', []))}]"
                if check_config.get("tags")
                else ""
            )
            output_handler.info(
                f"  - '{check_config['name']}' ({check_type}){tags_str}",
                echo=True,
            )

    def _execute_checks_and_collect_results(
        self,
        filtered_checks: list,
        global_config,
        plugins: dict,
        output_handler,
    ) -> tuple:
        """Execute checks and collect results for aggregation."""
        results_by_tag: dict[str, list] = {}
        all_results = []

        output_handler.info(
            f"Starting execution of {len(filtered_checks)} checks", echo=True
        )

        for check_type, check_config in filtered_checks:
            check_name = check_config.get("name", f"unnamed-{check_type}")

            # Determine execution type (local/remote)
            ssh_config_dict = check_config.get("ssh")
            if ssh_config_dict and ssh_config_dict.get("host"):
                host = ssh_config_dict.get("host")
            elif global_config.ssh and global_config.ssh.host:
                host = global_config.ssh.host
            else:
                host = None

            execution_type = f"remote: {host}" if host else "local"

            output_handler.info(
                f"Starting check: '{check_name}' ({check_type}) ({execution_type})",
                echo=True,
            )
            result = self._execute_single_check(
                check_type, check_config, global_config, plugins, output_handler
            )
            if result:
                all_results.append(result)
                # Organize results by tag for aggregation
                for result_tag in result.tags:
                    if result_tag not in results_by_tag:
                        results_by_tag[result_tag] = []
                    results_by_tag[result_tag].append(result)

        return results_by_tag, all_results

    def _process_results_and_report(
        self,
        results_by_tag: dict,
        all_results: list,
        global_config,
        output_handler,
    ) -> None:
        """Process results: send aggregated results and print summary table."""
        # Send aggregated results for all tags found in executed checks
        if results_by_tag and all_results:
            all_tags = list(results_by_tag.keys())
            output_handler.debug(
                f"Auto-aggregating results for tags: {all_tags}, "
                f"total checks: {len(all_results)}",
                echo=False,
            )
            self._send_aggregated_results(
                results_by_tag, all_tags, global_config, output_handler
            )

        # Print summary table
        if all_results:
            table = Table(title="Check Results Summary")
            table.add_column("Check Name", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Tags", style="blue")
            table.add_column("Status")
            table.add_column("Duration (s)", style="yellow")
            table.add_column("Message", style="white")

            for result in all_results:
                # Color status: green for up, red for down
                status_text = (
                    f"[green]{result.status}[/green]"
                    if result.status == "up"
                    else f"[red]{result.status}[/red]"
                )
                tags_str = ", ".join(result.tags) if result.tags else ""

                table.add_row(
                    result.check_name,
                    result.plugin_type,
                    tags_str,
                    status_text,
                    f"{result.duration_seconds:.2f}",
                    (
                        result.message[:50] + "..."
                        if len(result.message) > 50
                        else result.message
                    ),
                )

            output_handler.print_table(table, echo=True)

    def _send_aggregated_results(
        self,
        results_by_tag: dict[str, list],
        requested_tags: Optional[List[str]],
        global_config: GlobalConfig,
        output_handler,
    ) -> None:
        """
        Send aggregated results to Uptime Kuma for each requested tag.

        Args:
            results_by_tag: Dict mapping tag_name -> list of CheckResults
            requested_tags: List of tag names passed via --tag flags
            global_config: Global configuration containing tag configs
            output_handler: OutputHandler instance for logging and console output
        """
        if not requested_tags or not global_config.tags:
            output_handler.debug(
                f"No tag aggregation: requested_tags={requested_tags}, "
                f"global_config.tags={bool(global_config.tags)}",
                echo=False,
            )
            return

        output_handler.debug(
            f"Starting tag aggregation for tags: {requested_tags}, "
            f"available results: {list(results_by_tag.keys())}",
            echo=False,
        )

        for tag_name in requested_tags:
            if tag_name not in global_config.tags:
                output_handler.warning(
                    f"Tag '{tag_name}' has no aggregation config, skipping aggregation",
                    echo=True,
                )
                continue

            tag_config = global_config.tags[tag_name]
            tag_results = results_by_tag.get(tag_name, [])

            if not tag_results:
                output_handler.debug(
                    f"No checks found for tag '{tag_name}'", echo=False
                )
                continue

            status, message, duration_ms = self._compute_aggregated_result(
                tag_results, tag_name
            )

            # Sanitize message before sending
            sanitized_message = DataSanitizer.sanitize_output(message)

            output_handler.info(
                f"Aggregating {len(tag_results)} check(s) for tag '{tag_name}': {status}",
                echo=True,
            )

            # Validate tag has uptime_kuma config before sending
            if not tag_config.uptime_kuma:
                output_handler.debug(
                    f"Tag '{tag_name}' has no uptime_kuma config, skipping aggregation",
                    echo=False,
                )
                continue

            if not tag_config.uptime_kuma.url or not tag_config.uptime_kuma.token:
                output_handler.debug(
                    f"Tag '{tag_name}' missing url or token, skipping aggregation",
                    echo=False,
                )
                continue

            # Send to Uptime Kuma (config already merged at load time)
            success = send_push(
                uptime_kuma_url=tag_config.uptime_kuma.url,
                push_token=tag_config.uptime_kuma.token,
                message=sanitized_message,
                command=f"tag-{tag_name}",
                status=status,
                ping_ms=duration_ms,
                output_handler=output_handler,
            )

            if success:
                output_handler.info(
                    f"Aggregated result for tag '{tag_name}' sent to Uptime Kuma",
                    echo=True,
                )
            else:
                output_handler.error(
                    f"Failed to send aggregated result for tag '{tag_name}' to Uptime Kuma",
                    echo=True,
                )

    def _apply_command_line_overrides(
        self,
        global_config: GlobalConfig,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        heartbeat_token: Optional[str],
        timeout: int,
        log_file: Optional[str],
        log_level: Optional[str],
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        """Apply command-line overrides to global configuration."""
        # Expand environment variables in tokens
        if token:
            token = os.path.expandvars(token)
        if heartbeat_token:
            heartbeat_token = os.path.expandvars(heartbeat_token)

        # Apply CLI overrides using ConfigMerger
        ConfigMerger.apply_cli_overrides(
            global_config,
            uptime_kuma_url,
            token,
            heartbeat_token,
            timeout,
            log_file,
            log_level,
            quiet,
            verbose,
        )

    def _setup_ssh_config(
        self,
        global_config: GlobalConfig,
        ssh: Optional[str],
        ssh_key_file: Optional[str],
        ssh_password: Optional[str],
        ssh_strict_host_key_checking: bool,
        ssh_no_strict_host_key_checking: bool,
        output_handler: OutputHandler,
    ) -> None:
        """Setup SSH configuration from command-line options.

        This method handles CLI parsing and validation, then delegates
        configuration application to ConfigMerger for consistency.
        """
        if not ssh:
            # Validation: SSH options without host is an error
            if (
                ssh_key_file
                or ssh_password
                or (
                    ssh_strict_host_key_checking is not True
                    or ssh_no_strict_host_key_checking
                )
            ):
                output_handler.error(
                    "SSH options specified but no SSH host provided", echo=True
                )
                raise typer.Exit(1)
            return

        # Parse SSH host string (CLI-specific parsing)
        host, user, port = parse_ssh_connection_string(ssh)

        if host is None:
            output_handler.error(
                "Failed to parse SSH host from connection string", echo=True
            )
            raise typer.Exit(1)

        # Expand environment variables in SSH password (CLI-specific)
        expanded_password = None
        if ssh_password:
            expanded_password = os.path.expandvars(ssh_password)

        # Compute strict_host_key_checking from flags (CLI-specific logic)
        compute_strict_checking = (
            ssh_strict_host_key_checking and not ssh_no_strict_host_key_checking
        )

        # Apply merged SSH config using ConfigMerger
        ConfigMerger.apply_cli_ssh_config(
            global_config,
            host=host,
            user=user,
            port=port,
            key_file=ssh_key_file,
            password=expanded_password,
            strict_host_key_checking=compute_strict_checking,
        )

    def _create_plugin_config(
        self, plugin_class, check_config: dict, global_config: GlobalConfig
    ):
        """Create plugin configuration object with merged uptime_kuma and ssh settings."""
        merged_config = check_config.copy()

        # Merge configurations using ConfigMerger
        uptime_kuma_data = ConfigMerger.merge_uptime_kuma_config(
            global_config, check_config
        )
        ssh_data = ConfigMerger.merge_ssh_config(global_config, check_config)

        # Apply timeout from global config if not in check config
        ConfigMerger.apply_timeout(merged_config, global_config)

        # Remove uptime_kuma and ssh from merged_config for config creation
        merged_config.pop("uptime_kuma", None)
        merged_config.pop("ssh", None)

        check_config_obj = plugin_class.config_class(**merged_config)

        # Set uptime_kuma separately if available
        if uptime_kuma_data:
            check_config_obj.uptime_kuma = UptimeKumaConfig(**uptime_kuma_data)

        # Set ssh separately if available
        if ssh_data:
            from kuma_scout.plugins.models import SSHConfig

            check_config_obj.ssh = SSHConfig(**ssh_data)

        return check_config_obj

    def _execute_check_with_reporting(
        self,
        plugin_class,
        check_config_obj,
        global_config: GlobalConfig,
        output_handler,
    ) -> Optional[CheckResult]:
        """Execute a check and handle SSH setup and Uptime Kuma reporting.

        Sets execution context for structured error logging throughout the
        check execution chain.

        Returns:
            CheckResult from the check execution, or None if execution failed
        """
        # Create config snapshot for execution context (without sensitive data)
        config_snapshot = {
            "name": check_config_obj.name,
            "timeout": check_config_obj.timeout,
            "tags": check_config_obj.tags,
        }

        with execution_context_manager(
            check_name=check_config_obj.name,
            plugin_type=plugin_class.name,
            config_snapshot=config_snapshot,
        ):
            # Create SSH runner if needed - use check-level SSH config if available, fallback to global
            ssh_runner = None
            ssh_config = check_config_obj.ssh or global_config.ssh
            if ssh_config and ssh_config.host:
                # Parse SSH connection string to extract host, user, port
                parsed_host, parsed_user, parsed_port = parse_ssh_connection_string(
                    ssh_config.host
                )
                if parsed_host is None:
                    output_handler.error(
                        f"Failed to parse SSH host from connection string: {ssh_config.host}",
                        echo=True,
                    )
                    return None

                # Merge parsed values with explicit config fields (explicit fields win)
                host = parsed_host
                user = ssh_config.user if ssh_config.user is not None else parsed_user
                port = (
                    ssh_config.port
                    if ssh_config.port is not None
                    else (parsed_port or 22)
                )

                ssh_runner = SSHRunner(
                    host=host,
                    user=user,
                    port=port or 22,
                    key_file=ssh_config.key_file,
                    password=ssh_config.password,
                    strict_host_key_checking=ssh_config.strict_host_key_checking,
                )

            # Create plugin instance
            plugin = plugin_class(
                global_config=global_config,
                ssh_runner=ssh_runner,
                output_handler=output_handler,
            )

            # Execute the check
            result = plugin.execute_with_heartbeat(check_config_obj)

            # Attach tags to result for aggregation
            result.tags = check_config_obj.tags
            result.plugin_type = plugin_class.name
            output_handler.debug(
                f"Check '{check_config_obj.name}' completed with tags: {result.tags}",
                echo=False,
            )

            # Send to Uptime Kuma if configured
            # Config is already merged at load time, so uptime_kuma contains fallback values
            uptime_url = None
            uptime_token = None

            if check_config_obj.uptime_kuma:
                uptime_url = check_config_obj.uptime_kuma.url
                uptime_token = check_config_obj.uptime_kuma.token

            if uptime_url and uptime_token and not uptime_token.startswith("${"):
                status = result.status
                success = send_push(
                    uptime_kuma_url=str(uptime_url),
                    push_token=uptime_token,
                    message=DataSanitizer.sanitize_output(result.message),
                    command=DataSanitizer.sanitize_output(check_config_obj.name),
                    status=status,
                    ping_ms=int(result.duration_seconds * 1000),
                    output_handler=output_handler,
                )
                if success:
                    output_handler.info(
                        f"'{check_config_obj.name}' executed and reported", echo=True
                    )
                else:
                    output_handler.warning(
                        f"'{check_config_obj.name}' executed but failed to report",
                        echo=True,
                    )
            else:
                output_handler.info(
                    f"'{check_config_obj.name}' executed (no Uptime Kuma config)",
                    echo=True,
                )

            return result

    def _execute_single_check(
        self,
        check_type: str,
        check_config: dict,
        global_config: GlobalConfig,
        plugins: dict,
        output_handler,
    ) -> Optional[CheckResult]:
        """Execute a single check and handle reporting.

        Returns:
            CheckResult from the check execution, or None if execution failed
        """
        try:
            plugin_class = plugins.get(check_type)
            if not plugin_class:
                output_handler.error(f"Unknown plugin type: {check_type}", echo=True)
                return None

            check_config_obj = self._create_plugin_config(
                plugin_class, check_config, global_config
            )
            return self._execute_check_with_reporting(
                plugin_class, check_config_obj, global_config, output_handler
            )

        except Exception as e:
            output_handler.error(
                f"Failed to execute {check_config.get('name', check_type)}: {str(e)}",
                echo=True,
            )
            return None

    def generate_run_command(self) -> Callable:
        """Generate the 'run' command for running checks from config file."""

        def run_command(
            # Command-specific options
            config: str = typer.Argument(..., help="Path to config file"),
            tag: Optional[List[str]] = typer.Option(
                None, "--tag", help="Filter by tag (can be used multiple times)"
            ),
            name: Optional[List[str]] = typer.Option(
                None, "--name", help="Filter by check name (can be used multiple times)"
            ),
            plugin_type: Optional[List[str]] = typer.Option(
                None,
                "--type",
                help="Filter by plugin type (can be used multiple times)",
            ),
            exclude: Optional[List[str]] = typer.Option(
                None,
                "--exclude",
                help="Exclude checks by name (can be used multiple times)",
            ),
            dry_run: bool = typer.Option(
                False, "--dry-run", help="Show what would be run without executing"
            ),
            ignore_file_permissions: bool = typer.Option(
                False,
                "--ignore-file-permissions",
                help="Ignore file permission checks on config file",
            ),
            # Global options
            uptime_kuma_url: Optional[str] = typer.Option(
                None,
                "--uptime-kuma-url",
                help="Uptime Kuma push API URL (overrides config)",
            ),
            token: Optional[str] = typer.Option(
                None, "--token", help="Uptime Kuma push token (overrides config)"
            ),
            heartbeat_token: Optional[str] = typer.Option(
                None,
                "--heartbeat-token",
                help="Uptime Kuma token for heartbeat (overrides config) ",
            ),
            timeout: int = typer.Option(
                300, "--timeout", help="Global timeout for checks (seconds)"
            ),
            ssh: Optional[str] = typer.Option(
                None, "--ssh", help="SSH host (user@host or host) (overrides config)"
            ),
            ssh_key_file: Optional[str] = typer.Option(
                None,
                "--ssh-key-file",
                help="SSH private key file path (overrides config)",
            ),
            ssh_password: Optional[str] = typer.Option(
                None, "--ssh-password", help="SSH password (overrides config)"
            ),
            ssh_strict_host_key_checking: bool = typer.Option(
                True,
                "--ssh-strict-host-key-checking",
                help="Enable strict SSH host key checking (overrides config)",
            ),
            ssh_no_strict_host_key_checking: bool = typer.Option(
                False,
                "--ssh-no-strict-host-key-checking",
                help="Disable strict SSH host key checking (overrides config)",
            ),
            log_level: Optional[str] = typer.Option(
                None,
                "--log-level",
                help="Log level (DEBUG, INFO, WARNING, ERROR) (overrides config)",
            ),
            log_file: Optional[str] = typer.Option(
                None, "--log-file", help="Log file path (overrides config)"
            ),
            quiet: bool = typer.Option(
                False, "--quiet", help="Suppress all console output"
            ),
            verbose: bool = typer.Option(
                False,
                "--verbose",
                help="Enable verbose logging to console (DEBUG level)",
            ),
        ) -> None:
            """Run checks from a configuration file."""
            # Setup phase: logging, config loading, overrides, SSH
            output_handler, global_config, checks = self._setup_run_command(
                config,
                ignore_file_permissions,
                uptime_kuma_url,
                token,
                heartbeat_token,
                timeout,
                log_file,
                log_level,
                ssh,
                ssh_key_file,
                ssh_password,
                ssh_strict_host_key_checking,
                ssh_no_strict_host_key_checking,
                quiet,
                verbose,
            )

            # Log configuration summary
            self._log_config_summary(
                output_handler, global_config, tag, name, plugin_type, exclude
            )

            # Apply filters
            filtered_checks = self._filter_checks(
                checks, tag, name, plugin_type, exclude
            )

            # Handle dry run mode
            if dry_run:
                self._handle_dry_run(
                    output_handler,
                    filtered_checks,
                    config,
                    tag,
                    name,
                    plugin_type,
                    exclude,
                )
                return

            # Execute checks and collect results
            plugins = get_all_plugins()
            results_by_tag, all_results = self._execute_checks_and_collect_results(
                filtered_checks, global_config, plugins, output_handler
            )

            # Process results and generate reports
            self._process_results_and_report(
                results_by_tag, all_results, global_config, output_handler
            )

        return run_command

    def generate_list_plugins_command(self) -> Callable:
        """Generate the 'list-plugins' command for listing available plugins."""

        def list_plugins_command() -> None:
            """List available plugins."""
            # Initialize default logging
            setup_default_logging()

            plugins = get_all_plugins()
            print("Available plugins:")
            for plugin_type, plugin_class in sorted(plugins.items()):
                print(f"  - {plugin_type}: {plugin_class.description}")

        return list_plugins_command

    def generate_list_checks_command(self) -> Callable:
        """Generate the 'list-checks' command for listing checks in a config file."""

        def list_checks_command(
            config: str = typer.Argument(..., help="Config file path"),
            tag: Optional[List[str]] = typer.Option(
                None, "--tag", help="Filter by tag (can be used multiple times)"
            ),
            name: Optional[List[str]] = typer.Option(
                None, "--name", help="Filter by check name (can be used multiple times)"
            ),
            plugin_type: Optional[List[str]] = typer.Option(
                None,
                "--type",
                help="Filter by plugin type (can be used multiple times)",
            ),
            ignore_file_permissions: bool = typer.Option(
                False,
                "--ignore-file-permissions",
                help="Ignore file permission checks on config file",
            ),
        ) -> None:
            """List checks available in a configuration file."""
            # Initialize default logging
            setup_default_logging()

            try:
                global_config, checks = load_config(
                    config, ignore_file_permissions=ignore_file_permissions
                )
            except ValueError as e:
                print(f"Configuration error: {e}")
                raise typer.Exit(1) from e

            filtered_checks = self._filter_checks(checks, tag, name, plugin_type, None)

            print(f"Checks in {config}:")
            for check_type, check_config in filtered_checks:
                tags = check_config.get("tags", [])
                tags_str = f" [{', '.join(tags)}]" if tags else ""
                print(f"  - {check_config['name']} ({check_type}){tags_str}")

        return list_checks_command

    def generate_check_commands(self) -> List[Tuple[str, Callable]]:
        """Generate individual 'check <type>' subcommands for each plugin."""
        commands = []
        plugins = get_all_plugins()

        for plugin_type, plugin_class in plugins.items():
            command = self._create_simple_check_command(plugin_type, plugin_class)
            commands.append((plugin_type, command))

        return commands

    def _create_simple_check_command(self, plugin_type: str, plugin_class) -> Callable:
        """Generate a single check subcommand for a plugin."""

        def check_command(
            uptime_kuma_url: str = typer.Option(
                ...,
                "--uptime-kuma-url",
                help="Uptime Kuma push API URL [required] (e,g. http://localhost:3001/api/push)",
            ),
            token: str = typer.Option(
                ..., "--token", help="Uptime Kuma push token [required]"
            ),
            heartbeat_token: Optional[str] = typer.Option(
                None,
                "--heartbeat-token",
                help="Uptime Kuma token for heartbeat (heartbeat disabled if not provided)",
            ),
            timeout: int = typer.Option(
                300, "--timeout", help="Global timeout for checks (seconds)"
            ),
            ssh: Optional[str] = typer.Option(
                None,
                "--ssh",
                help="SSH host (user@host or host) (e.g. user@remotehost or remotehost or user@remotehost:2222)",
            ),
            ssh_key_file: Optional[str] = typer.Option(
                None,
                "--ssh-key-file",
                help="SSH private key file path (e.g. ~/.ssh/key.pem)",
            ),
            ssh_password: Optional[str] = typer.Option(
                None,
                "--ssh-password",
                help="SSH password (not recommended, use SSH key if possible)",
            ),
            ssh_strict_host_key_checking: bool = typer.Option(
                True,
                "--ssh-strict-host-key-checking",
                help="Enables strict SSH host key checking",
            ),
            ssh_no_strict_host_key_checking: bool = typer.Option(
                False,
                "--ssh-no-strict-host-key-checking",
                help="Disables strict SSH host key checking",
            ),
            log_level: Optional[str] = typer.Option(
                None,
                "--log-level",
                help="Log level (DEBUG, INFO, WARNING, ERROR)",
            ),
            log_file: Optional[str] = typer.Option(
                "/var/log/kuma-scout.log", "--log-file", help="Log file path"
            ),
            quiet: bool = typer.Option(
                False, "--quiet", help="Suppress all console output"
            ),
            verbose: bool = typer.Option(
                False,
                "--verbose",
                help="Enable verbose logging to console (DEBUG level)",
            ),
            name: Optional[str] = typer.Option(
                None, "--name", help="Check name (default: cli-check-<timestamp>)"
            ),
            retry_attempts: Optional[int] = typer.Option(
                0,
                "--retry-attempts",
                help="Number of retry attempts on failure (0 = no retry)",
            ),
            retry_delay_seconds: Optional[int] = typer.Option(
                5,
                "--retry-delay-seconds",
                help="Delay between retry attempts in seconds",
            ),
            # Global options
            **kwargs,
        ) -> None:
            """Execute a single {plugin_type} check."""
            self._execute_individual_check(
                plugin_class,
                name,
                log_level,
                log_file,
                uptime_kuma_url,
                token,
                heartbeat_token,
                timeout,
                ssh,
                ssh_key_file,
                ssh_password,
                ssh_strict_host_key_checking,
                ssh_no_strict_host_key_checking,
                retry_attempts,
                retry_delay_seconds,
                quiet,
                verbose,
                kwargs,
            )

        # Dynamically add parameters based on the plugin's config class
        config_class = plugin_class.config_class
        self._add_plugin_parameters_to_signature(
            check_command, config_class, plugin_type
        )

        return check_command

    def _execute_individual_check(
        self,
        plugin_class,
        name: Optional[str],
        log_level: Optional[str],
        log_file: Optional[str],
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        heartbeat_token: Optional[str],
        timeout: int,
        ssh: Optional[str],
        ssh_key_file: Optional[str],
        ssh_password: Optional[str],
        ssh_strict_host_key_checking: bool,
        ssh_no_strict_host_key_checking: bool,
        retry_attempts: Optional[int],
        retry_delay_seconds: Optional[int],
        quiet: bool = False,
        verbose: bool = False,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute a single check with the provided parameters."""
        if kwargs is None:
            kwargs = {}

        # Initialize default logging first
        setup_default_logging()

        # Setup logging based on options
        setup_logging(log_file, log_level, verbose=verbose)

        # Create output handler for unified logging and echoing
        output_handler = OutputHandler(Console(), quiet=quiet)

        # Log program version
        output_handler.info(f"Kuma Scout v{kuma_scout.__version__} starting", echo=True)

        # Create global config
        global_config = GlobalConfig(quiet=quiet, verbose=verbose)

        # Apply command-line overrides
        self._apply_command_line_overrides(
            global_config,
            uptime_kuma_url,
            token,
            heartbeat_token,
            timeout,
            log_file,
            log_level,
            quiet,
            verbose,
        )

        # Setup SSH configuration
        self._setup_ssh_config(
            global_config,
            ssh,
            ssh_key_file,
            ssh_password,
            ssh_strict_host_key_checking,
            ssh_no_strict_host_key_checking,
            output_handler,
        )

        # Validate Uptime Kuma options - both URL and token are required for individual checks
        if not uptime_kuma_url or not token:
            output_handler.error(
                "Both --uptime-kuma-url and --token are required for individual check commands",
                echo=True,
            )
            raise typer.Exit(1)

        # Generate default name if not provided
        if name is None:
            import time

            name = f"cli-check-{int(time.time())}"

        # Build config data from kwargs (plugin-specific parameters)
        check_config_data = self._build_check_config_data(
            name, retry_attempts, retry_delay_seconds, kwargs
        )

        # Create plugin config with merged settings (uptime_kuma, ssh, timeout)
        # Uses centralized _create_plugin_config for consistency with run command flow
        try:
            check_config_obj = self._create_plugin_config(
                plugin_class, check_config_data, global_config
            )
        except Exception as e:
            output_handler.error(f"Invalid configuration: {e}", echo=True)
            raise typer.Exit(1) from e

        # Show execution start
        if global_config.ssh and global_config.ssh.host:
            execution_type = f"remote: {global_config.ssh.host}"
        else:
            execution_type = "local"
        output_handler.info(
            f"Executing individual check: '{name}' ({plugin_class.name}) ({execution_type})",
            echo=True,
        )

        # Execute the check
        result = self._execute_check_with_reporting(
            plugin_class, check_config_obj, global_config, output_handler
        )

        # Show result
        if result:
            status_text = (
                "[green]UP[/green]" if result.status == "up" else "[red]DOWN[/red]"
            )
            tags_str = f" [{', '.join(result.tags)}]" if result.tags else ""
            output_handler.info(
                f"Check '{result.check_name}' ({result.plugin_type}){tags_str} completed: {status_text} - {result.message} ({result.duration_seconds:.2f}s)",
                echo=True,
            )

    def _build_check_config_data(
        self,
        name: str,
        retry_attempts: Optional[int],
        retry_delay_seconds: Optional[int],
        kwargs: dict,
    ) -> dict:
        """Build configuration data dictionary from command arguments."""
        check_config_data: dict = {"name": name}
        for key, value in kwargs.items():
            if value != "PydanticUndefined" and value is not None:
                # Skip retry as it's handled separately via CLI options
                if key == "retry":
                    continue
                check_config_data[key] = value

        # Add retry configuration if provided
        if retry_attempts is not None or retry_delay_seconds is not None:
            retry_config = {}
            if retry_attempts is not None:
                retry_config["attempts"] = retry_attempts
            if retry_delay_seconds is not None:
                retry_config["delay_seconds"] = retry_delay_seconds
            check_config_data["retry"] = retry_config

        return check_config_data

    def _add_plugin_parameters_to_signature(
        self, check_command, config_class, plugin_type: str
    ) -> None:
        """Add plugin-specific parameters to the command signature."""
        sig = inspect.signature(check_command)
        existing_param_names = {p.name for p in sig.parameters.values()}
        new_params = self._create_plugin_parameters(config_class, existing_param_names)

        # Extract base parameters from existing signature (exclude **kwargs)
        base_params = [
            param for param in sig.parameters.values() if param.name != "kwargs"
        ]

        # Separate positional and keyword-only parameters
        positional_params = []
        keyword_only_params = []

        # Add base parameters
        for param in base_params:
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional_params.append(param)
            else:
                keyword_only_params.append(param)

        # Add new parameters
        for param in new_params:
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional_params.append(param)
            else:
                keyword_only_params.append(param)

        # Combine: positional first, then keyword-only
        all_params = positional_params + keyword_only_params

        # Create new signature
        new_sig = inspect.Signature(all_params)
        check_command.__signature__ = new_sig

        # Update docstring
        check_command.__doc__ = f"Execute a single {plugin_type} check."

    def _create_plugin_parameters(self, config_class, existing_param_names) -> list:
        """Create plugin-specific parameters for the command signature."""
        required_params: list = []
        optional_params: list = []
        global_param_names = {
            "log_level",
            "log_file",
            "uptime_kuma_url",
            "token",
            "heartbeat_token",
            "timeout",
            "ssh",
            "ssh_key_file",
            "ssh_password",
            "ssh_strict_host_key_checking",
            "ssh_no_strict_host_key_checking",
        }

        for field_name, field_info in config_class.model_fields.items():
            if field_name in global_param_names or field_name in existing_param_names:
                continue

            if field_name == "name":  # name is now optional
                if "name" not in {
                    p.name for p in required_params + optional_params
                }:  # Avoid duplicates
                    param = inspect.Parameter(
                        field_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=typer.Argument(
                            None, help=f"{field_info.description} (optional)"
                        ),
                        annotation=Optional[str],
                    )
                    optional_params.append(param)
                continue
            elif field_name in ["uptime_kuma"]:  # Optional fields
                continue  # Skip uptime_kuma as it's handled globally

            # Skip tags for individual check commands - tags are for filtering multiple checks
            if field_name == "tags":
                continue

            # Skip snapshots for individual check commands - it's for YAML config only
            if field_name == "snapshots":
                continue

            # Skip retry for individual check commands - it's handled via CLI options
            if field_name == "retry":
                continue

            # Handle other fields based on type and requirement
            param = self._create_parameter_for_field(field_name, field_info)
            if field_info.is_required():
                required_params.append(param)
            else:
                optional_params.append(param)

        # Required parameters come first (as positional args), then optional (as options)
        return required_params + optional_params

    def _create_parameter_for_field(
        self, field_name: str, field_info
    ) -> inspect.Parameter:
        """Create a parameter for a specific field."""

        field_type = field_info.annotation
        is_required = field_info.is_required()
        from pydantic_core import PydanticUndefined

        default_value = (
            field_info.default if field_info.default is not PydanticUndefined else None
        )

        if hasattr(field_type, "__origin__") and field_type.__origin__ is list:
            # List types - use List[str] with multiple values
            from typing import List

            if is_required:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(..., help=field_info.description),
                    annotation=List[str],
                )
            else:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(
                        None,
                        f"--{field_name.replace('_', '-')}",
                        help=field_info.description,
                    ),
                    annotation=List[str],
                )
        elif field_type is str:
            if is_required:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(..., help=field_info.description),
                    annotation=str,
                )
            else:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(
                        default_value,
                        f"--{field_name.replace('_', '-')}",
                        help=field_info.description,
                    ),
                    annotation=str,
                )
        elif field_type is int:
            if is_required:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(..., help=field_info.description),
                    annotation=int,
                )
            else:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(
                        default_value,
                        f"--{field_name.replace('_', '-')}",
                        help=field_info.description,
                    ),
                    annotation=int,
                )
        elif field_type is bool:
            if is_required:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(..., help=field_info.description),
                    annotation=bool,
                )
            else:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(
                        default_value,
                        f"--{field_name.replace('_', '-')}",
                        help=field_info.description,
                    ),
                    annotation=bool,
                )
        else:
            # Unknown/complex types - treat as strings for CLI, validation happens in Pydantic
            if is_required:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=typer.Argument(..., help=field_info.description),
                    annotation=str,
                )
            else:
                return inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(
                        default_value if default_value is not None else None,
                        f"--{field_name.replace('_', '-')}",
                        help=field_info.description,
                    ),
                    annotation=str,
                )

    def _log_config_summary(
        self,
        output_handler,
        global_config: GlobalConfig,
        tags: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        excludes: Optional[List[str]] = None,
    ) -> None:
        """Log configuration summary for debugging."""
        output_handler.info("Configuration loaded:", echo=True)
        output_handler.info(
            f"  Uptime Kuma URL: {global_config.uptime_kuma.url if global_config.uptime_kuma else 'Not configured'}",
            echo=True,
        )
        output_handler.info(
            f"  Logging level: {global_config.logging.level} (effective)", echo=True
        )
        output_handler.info(
            f"  Log file: {global_config.logging.file or 'Console only'}", echo=True
        )
        output_handler.info(
            f"  Heartbeat: {'Enabled' if global_config.heartbeat.enabled else 'Disabled'}",
            echo=True,
        )
        if global_config.heartbeat.enabled:
            output_handler.info(
                f"    Interval: {global_config.heartbeat.interval}s", echo=True
            )
        output_handler.info(
            f"  SSH: {'Configured' if global_config.ssh else 'Not configured'}",
            echo=True,
        )
        if global_config.ssh:
            output_handler.info(f"    Host: {global_config.ssh.host}", echo=True)
            output_handler.info(
                f"    User: {global_config.ssh.user or 'Default'}", echo=True
            )
            output_handler.info(f"    Port: {global_config.ssh.port}", echo=True)

        # Log filters
        filters = []
        if tags:
            filters.append(f"tags: {', '.join(tags)}")
        if names:
            filters.append(f"names: {', '.join(names)}")
        if types:
            filters.append(f"types: {', '.join(types)}")
        if excludes:
            filters.append(f"excludes: {', '.join(excludes)}")

        if filters:
            output_handler.info(f"  Filters: {', '.join(filters)}", echo=False)
        else:
            output_handler.info("  Filters: None", echo=False)

    def _filter_checks(
        self,
        checks: List[tuple[str, dict]],
        tags: Optional[List[str]],
        names: Optional[List[str]],
        types: Optional[List[str]],
        excludes: Optional[List[str]],
    ) -> List[tuple[str, dict]]:
        """Filter checks based on various criteria."""
        filtered = []

        for check_type, check_config in checks:
            # Apply filters (union logic - include if matches any filter)
            should_include = True

            if excludes and check_config["name"] in excludes:
                should_include = False

            if should_include and tags:
                check_tags = check_config.get("tags", [])
                if not check_tags or not all(tag in check_tags for tag in tags):
                    should_include = False

            if should_include and names:
                if check_config["name"] not in names:
                    should_include = False

            if should_include and types:
                if check_type not in types:
                    should_include = False

            if should_include:
                filtered.append((check_type, check_config))

        return filtered
