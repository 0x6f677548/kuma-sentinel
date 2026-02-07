"""CLI generator for the new plugin-based architecture."""

import inspect
import os
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import typer

from kuma_scout.core.config_loader import load_config
from kuma_scout.core.logger import setup_default_logging, setup_logging
from kuma_scout.core.models import CheckResult
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

        # Combine messages with check status
        check_summaries = [f"{r.check_name}: {r.status}" for r in results]
        message = f"Tag '{tag_name}' [{len([r for r in results if r.status == 'up'])}/{len(results)} healthy]: {' | '.join(check_summaries)}"

        # Total duration is sum of all check durations
        total_duration_ms = sum(r.duration_seconds for r in results) * 1000

        return overall_status, message, int(total_duration_ms)

    def _send_aggregated_results(
        self,
        results_by_tag: dict[str, list],
        requested_tags: Optional[List[str]],
        global_config: GlobalConfig,
        logger,
    ) -> None:
        """
        Send aggregated results to Uptime Kuma for each requested tag.

        Args:
            results_by_tag: Dict mapping tag_name -> list of CheckResults
            requested_tags: List of tag names passed via --tag flags
            global_config: Global configuration containing tag configs
            logger: Logger instance
        """
        if not requested_tags or not global_config.tags:
            logger.debug(
                f"No tag aggregation: requested_tags={requested_tags}, "
                f"global_config.tags={bool(global_config.tags)}"
            )
            return

        logger.debug(
            f"Starting tag aggregation for tags: {requested_tags}, "
            f"available results: {list(results_by_tag.keys())}"
        )

        for tag_name in requested_tags:
            if tag_name not in global_config.tags:
                logger.warning(
                    f"⚠️  Tag '{tag_name}' has no aggregation config, skipping aggregation"
                )
                continue

            tag_config = global_config.tags[tag_name]
            tag_results = results_by_tag.get(tag_name, [])

            if not tag_results:
                logger.debug(f"No checks found for tag '{tag_name}'")
                continue

            status, message, duration_ms = self._compute_aggregated_result(
                tag_results, tag_name
            )

            # Sanitize message before sending
            sanitized_message = DataSanitizer.sanitize_output(message)

            logger.info(
                f"📊 Aggregating {len(tag_results)} check(s) for tag '{tag_name}': {status}"
            )

            # Send to Uptime Kuma
            success = send_push(
                logger=logger,
                uptime_kuma_url=(
                    global_config.uptime_kuma.url if global_config.uptime_kuma else None
                ),
                push_token=tag_config.token,
                message=sanitized_message,
                command=f"tag-{tag_name}",
                status=status,
                ping_ms=duration_ms,
            )

            if success:
                logger.info(
                    f"✅ Aggregated result for tag '{tag_name}' sent to Uptime Kuma"
                )
            else:
                logger.error(
                    f"❌ Failed to send aggregated result for tag '{tag_name}' to Uptime Kuma"
                )

    def _apply_command_line_overrides(
        self,
        global_config: GlobalConfig,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        heartbeat_token: Optional[str],
        timeout: int,
        logger,
    ) -> None:
        """Apply command-line overrides to global configuration."""
        # Expand environment variables in tokens
        if token:
            token = os.path.expandvars(token)
        if heartbeat_token:
            heartbeat_token = os.path.expandvars(heartbeat_token)

        # Only set uptime_kuma config if both URL and token are provided
        if uptime_kuma_url and token:
            global_config.uptime_kuma = UptimeKumaConfig(
                url=uptime_kuma_url, token=token
            )

        if heartbeat_token:
            if not global_config.heartbeat:
                from kuma_scout.plugins.models import HeartbeatConfig

                global_config.heartbeat = HeartbeatConfig()
            global_config.heartbeat.token = heartbeat_token

        if timeout != 300:  # Only override if not default
            global_config.timeout = timeout

    def _setup_ssh_config(
        self,
        global_config: GlobalConfig,
        ssh: Optional[str],
        ssh_key_file: Optional[str],
        ssh_password: Optional[str],
        ssh_strict_host_key_checking: bool,
        ssh_no_strict_host_key_checking: bool,
        logger,
    ) -> None:
        """Setup SSH configuration from command-line options."""
        if not ssh:
            # Early return if no SSH host specified
            if (
                ssh_key_file
                or ssh_password
                or (
                    ssh_strict_host_key_checking is not True
                    or ssh_no_strict_host_key_checking
                )
            ):
                logger.error("SSH options specified but no SSH host provided")
                raise typer.Exit(1)
            return

        # Parse SSH host string using the utility function
        host, user, port = parse_ssh_connection_string(ssh)

        # Ensure host is not None (should not happen with valid input)
        if host is None:
            logger.error("❌ Failed to parse SSH host from connection string")
            raise typer.Exit(1)

        if not global_config.ssh:
            from kuma_scout.plugins.models import SSHConfig

            global_config.ssh = SSHConfig(host=host, user=user, port=port or 22)
        else:
            global_config.ssh.host = host
            if user:
                global_config.ssh.user = user
            if port:
                global_config.ssh.port = port

        # Set additional SSH options
        if ssh_key_file:
            global_config.ssh.key_file = ssh_key_file

        if ssh_password:
            ssh_password = os.path.expandvars(ssh_password)
            global_config.ssh.password = ssh_password

        if ssh_strict_host_key_checking is not True or ssh_no_strict_host_key_checking:
            global_config.ssh.strict_host_key_checking = (
                ssh_strict_host_key_checking and not ssh_no_strict_host_key_checking
            )

    def _create_plugin_config(
        self, plugin_class, check_config: dict, global_config: GlobalConfig
    ):
        """Create plugin configuration object with merged uptime_kuma and ssh settings."""
        # First, handle uptime_kuma merging: check-level config can override global
        merged_config = check_config.copy()
        uptime_kuma_data = None
        if "uptime_kuma" in check_config:
            # Merge check-level uptime_kuma with global config
            check_uptime = check_config["uptime_kuma"]
            global_uptime = (
                global_config.uptime_kuma.model_dump()
                if global_config.uptime_kuma
                else {}
            )
            uptime_kuma_data = {**global_uptime, **check_uptime}
        elif global_config.uptime_kuma:
            # Use global uptime_kuma if check doesn't have one
            uptime_kuma_data = global_config.uptime_kuma.model_dump()

        # Handle SSH merging: check-level config can override global
        ssh_data = None
        if "ssh" in check_config:
            # Merge check-level ssh with global config
            check_ssh = check_config["ssh"]
            global_ssh = global_config.ssh.model_dump() if global_config.ssh else {}
            ssh_data = {**global_ssh, **check_ssh}
        elif global_config.ssh:
            # Use global ssh if check doesn't have one
            ssh_data = global_config.ssh.model_dump()

        # Handle timeout merging: check-level config can override global
        if "timeout" not in merged_config and global_config.timeout != 300:
            merged_config["timeout"] = global_config.timeout

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
        logger,
    ) -> Optional[CheckResult]:
        """Execute a check and handle SSH setup and Uptime Kuma reporting.

        Returns:
            CheckResult from the check execution, or None if execution failed
        """
        # Create SSH runner if needed - use check-level SSH config if available, fallback to global
        ssh_runner = None
        ssh_config = check_config_obj.ssh or global_config.ssh
        if ssh_config and ssh_config.host:
            # Parse user@host format
            host = ssh_config.host
            user = None
            if "@" in host:
                user, host = host.split("@", 1)

            ssh_runner = SSHRunner(
                host=host,
                user=user,
                port=ssh_config.port or 22,
                key_file=ssh_config.key_file,
                password=ssh_config.password,
                strict_host_key_checking=ssh_config.strict_host_key_checking,
            )

        # Create plugin instance
        plugin = plugin_class(
            global_config=global_config,
            ssh_runner=ssh_runner,
            logger=logger,
        )

        # Execute the check
        result = plugin.execute_with_heartbeat(check_config_obj)

        # Attach tags to result for aggregation
        result.tags = check_config_obj.tags
        logger.debug(
            f"Check '{check_config_obj.name}' completed with tags: {result.tags}"
        )

        # Send to Uptime Kuma if configured
        uptime_config = check_config_obj.uptime_kuma or global_config.uptime_kuma
        if (
            uptime_config
            and uptime_config.url
            and uptime_config.token
            and not uptime_config.token.startswith("${")
        ):
            status = result.status
            success = send_push(
                logger=plugin.logger,
                uptime_kuma_url=str(uptime_config.url),
                push_token=uptime_config.token,
                message=result.message,
                command=check_config_obj.name,
                status=status,
                ping_ms=int(result.duration_seconds * 1000),
            )
            if success:
                logger.info(f"✅ {check_config_obj.name} executed and reported")
            else:
                logger.warning(
                    f"⚠️  {check_config_obj.name} executed but failed to report"
                )
        else:
            logger.info(f"✅ {check_config_obj.name} executed (no Uptime Kuma config)")

        return result

    def _execute_single_check(
        self,
        check_type: str,
        check_config: dict,
        global_config: GlobalConfig,
        plugins: dict,
        logger,
    ) -> Optional[CheckResult]:
        """Execute a single check and handle reporting.

        Returns:
            CheckResult from the check execution, or None if execution failed
        """
        try:
            plugin_class = plugins.get(check_type)
            if not plugin_class:
                logger.error(f"❌ Unknown plugin type: {check_type}")
                return None

            check_config_obj = self._create_plugin_config(
                plugin_class, check_config, global_config
            )
            return self._execute_check_with_reporting(
                plugin_class, check_config_obj, global_config, logger
            )

        except Exception as e:
            logger.error(
                f"❌ Failed to execute {check_config.get('name', check_type)}: {str(e)}"
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
            log_level: str = typer.Option(
                "INFO",
                "--log-level",
                help="Log level (DEBUG, INFO, WARNING, ERROR) (overrides config)",
            ),
            log_file: Optional[str] = typer.Option(
                None, "--log-file", help="Log file path (overrides config)"
            ),
        ) -> None:
            """Run checks from a configuration file."""
            # Initialize default logging first
            setup_default_logging()

            # Setup logging based on options (do this early so logger is available for errors)
            logger = setup_logging(log_file, log_level)

            # Load config with global options
            try:
                global_config, checks = load_config(
                    config, ignore_file_permissions=ignore_file_permissions
                )
            except ValueError as e:
                logger.error(f"Configuration error: {e}")
                raise typer.Exit(1) from e

            # Apply command-line overrides
            self._apply_command_line_overrides(
                global_config, uptime_kuma_url, token, heartbeat_token, timeout, logger
            )

            # Setup SSH configuration
            self._setup_ssh_config(
                global_config,
                ssh,
                ssh_key_file,
                ssh_password,
                ssh_strict_host_key_checking,
                ssh_no_strict_host_key_checking,
                logger,
            )

            # Setup logging based on options
            logger = setup_logging(log_file, log_level)

            # Log configuration summary
            self._log_config_summary(logger, global_config, log_level)

            # Apply filters
            filtered_checks = self._filter_checks(
                checks, tag, name, plugin_type, exclude
            )

            if dry_run:
                logger.info("Dry run - would execute the following checks:")
                for check_type, check_config in filtered_checks:
                    logger.info(f"  - {check_config['name']} ({check_type})")
                return

            # Execute the checks
            plugins = get_all_plugins()
            logger.info(f"🚀 Starting execution of {len(filtered_checks)} checks")

            # Collect results for aggregation
            results_by_tag: dict[str, list] = {}
            all_results = []

            for check_type, check_config in filtered_checks:
                result = self._execute_single_check(
                    check_type, check_config, global_config, plugins, logger
                )
                if result:
                    all_results.append(result)
                    # Organize results by tag for aggregation
                    for result_tag in result.tags:
                        if result_tag not in results_by_tag:
                            results_by_tag[result_tag] = []
                        results_by_tag[result_tag].append(result)

            # Send aggregated results for all tags found in executed checks
            if results_by_tag and all_results:
                all_tags = list(results_by_tag.keys())
                logger.debug(
                    f"Auto-aggregating results for tags: {all_tags}, "
                    f"total checks: {len(all_results)}"
                )
                self._send_aggregated_results(
                    results_by_tag, all_tags, global_config, logger
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
            log_level: str = typer.Option(
                "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)"
            ),
            log_file: Optional[str] = typer.Option(
                "/var/log/kuma-scout.log", "--log-file", help="Log file path"
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
        log_level: str,
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
        kwargs: dict,
    ) -> None:
        """Execute a single check with the provided parameters."""
        # Initialize default logging first
        setup_default_logging()

        # Setup logging based on options
        logger = setup_logging(log_file, log_level)

        # Create global config
        global_config = GlobalConfig()

        # Apply command-line overrides
        self._apply_command_line_overrides(
            global_config, uptime_kuma_url, token, heartbeat_token, timeout, logger
        )

        # Setup SSH configuration
        self._setup_ssh_config(
            global_config,
            ssh,
            ssh_key_file,
            ssh_password,
            ssh_strict_host_key_checking,
            ssh_no_strict_host_key_checking,
            logger,
        )

        # Validate Uptime Kuma options - both URL and token are required for individual checks
        if not uptime_kuma_url or not token:
            logger.error(
                "❌ Both --uptime-kuma-url and --token are required for individual check commands"
            )
            raise typer.Exit(1)

        # Generate default name if not provided
        if name is None:
            import time

            name = f"cli-check-{int(time.time())}"

        # Build config data from kwargs (plugin-specific parameters)
        config_class = plugin_class.config_class
        check_config_data = self._build_check_config_data(
            name, retry_attempts, retry_delay_seconds, kwargs
        )

        # Validate required fields
        try:
            check_config_obj = config_class(**check_config_data)
        except Exception as e:
            logger.error(f"❌ Invalid configuration: {e}")
            raise typer.Exit(1) from e

        # Set uptime_kuma config if both URL and token are provided
        if uptime_kuma_url and token:
            from kuma_scout.plugins.models import UptimeKumaConfig

            check_config_obj.uptime_kuma = UptimeKumaConfig(
                url=uptime_kuma_url, token=token
            )

        self._execute_check_with_reporting(
            plugin_class, check_config_obj, global_config, logger
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
        self, logger, global_config: GlobalConfig, effective_log_level: str
    ) -> None:
        """Log configuration summary for debugging."""
        logger.info("🔧 Configuration loaded:")
        logger.info(
            f"  📊 Uptime Kuma URL: {global_config.uptime_kuma.url if global_config.uptime_kuma else 'Not configured'}"
        )
        logger.info(f"  📝 Logging level: {effective_log_level} (effective)")
        logger.info(f"  📁 Log file: {global_config.logging.file or 'Console only'}")
        logger.info(
            f"  🔄 Heartbeat: {'Enabled' if global_config.heartbeat.enabled else 'Disabled'}"
        )
        if global_config.heartbeat.enabled:
            logger.info(f"    ⏱️  Interval: {global_config.heartbeat.interval}s")
        logger.info(
            f"  🔌 SSH: {'Configured' if global_config.ssh else 'Not configured'}"
        )
        if global_config.ssh:
            logger.info(f"    🖥️  Host: {global_config.ssh.host}")
            logger.info(f"    👤 User: {global_config.ssh.user or 'Default'}")
            logger.info(f"    🔢 Port: {global_config.ssh.port}")

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
                if not check_tags or not any(tag in check_tags for tag in tags):
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
