"""CLI generator for the new plugin-based architecture."""

from typing import TYPE_CHECKING, Callable, List, Optional

import typer

from ..core.config_loader import load_config
from ..core.logger import setup_default_logging, setup_logging
from ..plugins import get_all_plugins
from ..plugins.models import GlobalConfig, UptimeKumaConfig

if TYPE_CHECKING:
    pass


class CLIGenerator:
    """Generates CLI commands for the new plugin architecture."""

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
        if uptime_kuma_url:
            if not global_config.uptime_kuma:
                global_config.uptime_kuma = UptimeKumaConfig(url=uptime_kuma_url)
            else:
                global_config.uptime_kuma.url = uptime_kuma_url

        if token:
            if not global_config.uptime_kuma:
                global_config.uptime_kuma = UptimeKumaConfig(token=token)
            else:
                global_config.uptime_kuma.token = token

        if heartbeat_token:
            if not global_config.heartbeat:
                from ..plugins.models import HeartbeatConfig
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
            if ssh_key_file or ssh_password or (ssh_strict_host_key_checking is not True or ssh_no_strict_host_key_checking):
                logger.error("SSH options specified but no SSH host provided")
                raise typer.Exit(1)
            return

        # Parse SSH host string using the utility function
        from ..core.utils.ssh_runner import parse_ssh_connection_string
        host, user, port = parse_ssh_connection_string(ssh)

        if not global_config.ssh:
            from ..plugins.models import SSHConfig
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
            global_config.ssh.password = ssh_password

        if ssh_strict_host_key_checking is not True or ssh_no_strict_host_key_checking:
            global_config.ssh.strict_host_key_checking = ssh_strict_host_key_checking and not ssh_no_strict_host_key_checking

    def _create_plugin_config(self, plugin_class, check_config: dict, global_config: GlobalConfig):
        """Create plugin configuration object with merged uptime_kuma settings."""
        # First, handle uptime_kuma merging: check-level config can override global
        merged_config = check_config.copy()
        uptime_kuma_data = None
        if 'uptime_kuma' in check_config:
            # Merge check-level uptime_kuma with global config
            check_uptime = check_config['uptime_kuma']
            global_uptime = global_config.uptime_kuma.model_dump() if global_config.uptime_kuma else {}
            uptime_kuma_data = {**global_uptime, **check_uptime}
        elif global_config.uptime_kuma:
            # Use global uptime_kuma if check doesn't have one
            uptime_kuma_data = global_config.uptime_kuma.model_dump()

        # Remove uptime_kuma from merged_config for config creation
        merged_config.pop('uptime_kuma', None)

        check_config_obj = plugin_class.config_class(**merged_config)

        # Set uptime_kuma separately if available
        if uptime_kuma_data:
            check_config_obj.uptime_kuma = UptimeKumaConfig(**uptime_kuma_data)

        return check_config_obj

    def _execute_check_with_reporting(
        self,
        plugin_class,
        check_config_obj,
        global_config: GlobalConfig,
        logger,
    ) -> None:
        """Execute a check and handle SSH setup and Uptime Kuma reporting."""
        # Create SSH runner if needed
        ssh_runner = None
        if global_config.ssh and global_config.ssh.host:
            # Parse user@host format
            host = global_config.ssh.host
            user = None
            if "@" in host:
                user, host = host.split("@", 1)

            from ..core.utils.ssh_runner import SSHRunner
            ssh_runner = SSHRunner(
                host=host,
                user=user,
                port=global_config.ssh.port or 22,
                key_file=global_config.ssh.key_file,
                password=global_config.ssh.password,
                strict_host_key_checking=global_config.ssh.strict_host_key_checking,
            )

        # Create plugin instance
        plugin = plugin_class(
            global_config=global_config,
            ssh_runner=ssh_runner,
            logger=logger,
        )

        # Execute the check
        result = plugin.execute_with_heartbeat(check_config_obj)

        # Send to Uptime Kuma if configured
        uptime_config = check_config_obj.uptime_kuma or global_config.uptime_kuma
        if uptime_config and uptime_config.url and uptime_config.token and not uptime_config.token.startswith('${'):
            from ..core.uptime_kuma import send_push
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
                logger.warning(f"⚠️  {check_config_obj.name} executed but failed to report")
        else:
            logger.info(f"✅ {check_config_obj.name} executed (no Uptime Kuma config)")

    def _execute_single_check(
        self,
        check_type: str,
        check_config: dict,
        global_config: GlobalConfig,
        plugins: dict,
        logger,
    ) -> None:
        """Execute a single check and handle reporting."""
        try:
            plugin_class = plugins.get(check_type)
            if not plugin_class:
                logger.error(f"❌ Unknown plugin type: {check_type}")
                return

            check_config_obj = self._create_plugin_config(plugin_class, check_config, global_config)
            self._execute_check_with_reporting(plugin_class, check_config_obj, global_config, logger)

        except Exception as e:
            logger.error(f"❌ Failed to execute {check_config.get('name', check_type)}: {str(e)}")

    def generate_run_command(self) -> Callable:
        """Generate the 'run' command for running checks from config file."""

        def run_command(
            # Global options (also available via @app.callback(), but can be overridden per command)
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
            # Command-specific options
            config: str = typer.Option(..., "--config", help="Path to config file"),
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
                False, "--ignore-file-permissions", help="Ignore file permission checks on config file"
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
                    config,
                    ignore_file_permissions=ignore_file_permissions
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
                global_config, ssh, ssh_key_file, ssh_password,
                ssh_strict_host_key_checking, ssh_no_strict_host_key_checking, logger
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

            for check_type, check_config in filtered_checks:
                self._execute_single_check(check_type, check_config, global_config, plugins, logger)

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
            config: str = typer.Option(..., "--config", help="Config file path"),
            tag: Optional[List[str]] = typer.Option(
                None, "--tag", help="Filter by tag (can be used multiple times)"
            ),
            name: Optional[List[str]] = typer.Option(
                None, "--name", help="Filter by check name (can be used multiple times)"
            ),
            plugin_type: Optional[List[str]] = typer.Option(
                None, "--type", help="Filter by plugin type (can be used multiple times)"
            ),
            ignore_file_permissions: bool = typer.Option(
                False, "--ignore-file-permissions", help="Ignore file permission checks on config file"
            ),
        ) -> None:
            """List checks available in a configuration file."""
            # Initialize default logging
            setup_default_logging()

            try:
                global_config, checks = load_config(
                    config,
                    ignore_file_permissions=ignore_file_permissions
                )
            except ValueError as e:
                print(f"Configuration error: {e}")
                raise typer.Exit(1) from e

            filtered_checks = self._filter_checks(
                checks, tag, name, plugin_type, None
            )

            print(f"Checks in {config}:")
            for check_type, check_config in filtered_checks:
                tags = check_config.get("tags", [])
                tags_str = f" [{', '.join(tags)}]" if tags else ""
                print(f"  - {check_config['name']} ({check_type}){tags_str}")

        return list_checks_command

    def generate_check_commands(self) -> List[Callable]:
        """Generate individual 'check <type>' subcommands for each plugin."""
        commands = []
        plugins = get_all_plugins()

        for plugin_type, plugin_class in plugins.items():
            # For now, create a simple command that takes name and basic parameters
            # TODO: Auto-generate full parameter lists
            command = self._create_simple_check_command(plugin_type, plugin_class)
            commands.append((plugin_type, command))

        return commands

    def _create_simple_check_command(self, plugin_type: str, plugin_class) -> Callable:
        """Generate a single check subcommand for a plugin."""
        import inspect

        def check_command(
            name: str = typer.Argument(..., help="Check name"),
            # Global options
            log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
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
            **kwargs
        ) -> None:
            """Execute a single {plugin_type} check."""
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
                global_config, ssh, ssh_key_file, ssh_password,
                ssh_strict_host_key_checking, ssh_no_strict_host_key_checking, logger
            )

            # Build config data from kwargs (plugin-specific parameters)
            # Filter out PydanticUndefined and None values for optional fields
            check_config_data = {'name': name}
            for key, value in kwargs.items():
                if value != 'PydanticUndefined' and not (value is None and key in ['tags', 'uptime_kuma']):
                    check_config_data[key] = value

            # Validate required fields
            try:
                check_config_obj = config_class(**check_config_data)
            except Exception as e:
                logger.error(f"❌ Invalid configuration: {e}")
                raise typer.Exit(1) from e

            # Set uptime_kuma config if provided
            if uptime_kuma_url or token:
                from ..plugins.models import UptimeKumaConfig
                check_config_obj.uptime_kuma = UptimeKumaConfig(
                    url=uptime_kuma_url,
                    token=token
                )

            self._execute_check_with_reporting(plugin_class, check_config_obj, global_config, logger)

        # Dynamically add parameters based on the plugin's config class
        config_class = plugin_class.config_class
        sig = inspect.signature(check_command)

        # Add parameters for each field in the config class
        new_params = []
        existing_param_names = {p.name for p in sig.parameters.values()}
        global_param_names = {'log_level', 'log_file', 'uptime_kuma_url', 'token', 'heartbeat_token', 'timeout', 'ssh', 'ssh_key_file', 'ssh_password', 'ssh_strict_host_key_checking', 'ssh_no_strict_host_key_checking'}

        for field_name, field_info in config_class.model_fields.items():
            if field_name in global_param_names or field_name in existing_param_names:  # Skip global and existing parameters
                continue
            if field_name == 'name':  # name is always required
                if 'name' not in {p.name for p in new_params}:  # Avoid duplicates
                    param = inspect.Parameter(
                        field_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=typer.Argument(..., help=field_info.description),
                        annotation=str
                    )
                    new_params.append(param)
                continue
            elif field_name in ['uptime_kuma']:  # Optional fields
                # Skip uptime_kuma as it's handled globally
                continue

            # Skip tags for individual check commands - tags are for filtering multiple checks
            if field_name == 'tags':
                continue

            # Skip snapshots for individual check commands - it's for YAML config only
            if field_name == 'snapshots':
                continue

            # Handle other fields based on type
            field_type = field_info.annotation
            default_value = field_info.default if not field_info.is_required() else None

            if hasattr(field_type, '__origin__') and field_type.__origin__ is list:
                # List types - use List[str] with multiple values
                from typing import List
                param = inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(None, f"--{field_name.replace('_', '-')}", help=field_info.description),
                    annotation=List[str]
                )
            elif field_type is str:
                param = inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(default_value, f"--{field_name.replace('_', '-')}", help=field_info.description),
                    annotation=str
                )
            elif field_type is int:
                param = inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(default_value, f"--{field_name.replace('_', '-')}", help=field_info.description),
                    annotation=int
                )
            elif field_type is bool:
                param = inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(default_value, f"--{field_name.replace('_', '-')}", help=field_info.description),
                    annotation=bool
                )
            else:
                # Unknown types - use string
                param = inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=typer.Option(default_value, f"--{field_name.replace('_', '-')}", help=field_info.description),
                    annotation=str
                )
            new_params.append(param)

        # Create a new signature with all parameters
        base_params = [
            inspect.Parameter('name', inspect.Parameter.POSITIONAL_OR_KEYWORD, default=typer.Argument(..., help="Check name")),
            inspect.Parameter('log_level', inspect.Parameter.KEYWORD_ONLY, default=typer.Option("INFO", "--log-level", help="Log level")),
            inspect.Parameter('log_file', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--log-file", help="Log file path")),
            inspect.Parameter('uptime_kuma_url', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--uptime-kuma-url", help="Uptime Kuma push API URL")),
            inspect.Parameter('token', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--token", help="Uptime Kuma push token")),
            inspect.Parameter('heartbeat_token', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--heartbeat-token", help="Uptime Kuma token for heartbeat")),
            inspect.Parameter('timeout', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(300, "--timeout", help="Global timeout for checks (seconds)")),
            inspect.Parameter('ssh', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--ssh", help="SSH host (user@host or host)")),
            inspect.Parameter('ssh_key_file', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--ssh-key-file", help="SSH private key file path")),
            inspect.Parameter('ssh_password', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(None, "--ssh-password", help="SSH password")),
            inspect.Parameter('ssh_strict_host_key_checking', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(True, "--ssh-strict-host-key-checking", help="Enable strict SSH host key checking")),
            inspect.Parameter('ssh_no_strict_host_key_checking', inspect.Parameter.KEYWORD_ONLY, default=typer.Option(False, "--ssh-no-strict-host-key-checking", help="Disable strict SSH host key checking")),
        ]

        # Add plugin-specific parameters
        all_params = base_params + new_params

        # Create new signature
        new_sig = inspect.Signature(all_params)
        check_command.__signature__ = new_sig

        # Update docstring
        check_command.__doc__ = f"Execute a single {plugin_type} check."

        return check_command

    def _log_config_summary(self, logger, global_config: GlobalConfig, effective_log_level: str) -> None:
        """Log configuration summary for debugging."""
        logger.info("🔧 Configuration loaded:")
        logger.info(f"  📊 Uptime Kuma URL: {global_config.uptime_kuma.url if global_config.uptime_kuma else 'Not configured'}")
        logger.info(f"  📝 Logging level: {effective_log_level} (effective)")
        logger.info(f"  📁 Log file: {global_config.logging.file or 'Console only'}")
        logger.info(f"  🔄 Heartbeat: {'Enabled' if global_config.heartbeat.enabled else 'Disabled'}")
        if global_config.heartbeat.enabled:
            logger.info(f"    ⏱️  Interval: {global_config.heartbeat.interval}s")
        logger.info(f"  🔌 SSH: {'Configured' if global_config.ssh else 'Not configured'}")
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
                if not check_tags or not any(
                    tag in check_tags for tag in tags
                ):
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
