"""Config merging utility for Kuma Scout CLI.

This module provides centralized configuration merging logic to handle the
configuration priority: CLI arguments > YAML config > defaults.

All config merging operations follow this standard pattern:
1. CLI arguments have highest priority
2. YAML config provides middle-level settings
3. Defaults apply when nothing else is specified
"""

from typing import Optional

from kuma_scout.plugins.models import (
    DEFAULT_TIMEOUT,
    GlobalConfig,
    SSHConfig,
    UptimeKumaConfig,
)


class ConfigMerger:
    """Centralized configuration merging for consistent priority handling."""

    @staticmethod
    def merge_uptime_kuma_config(
        global_config: GlobalConfig, check_config: dict
    ) -> Optional[dict]:
        """Merge uptime_kuma config from global and check-level sources.

        Supports field-level merging, allowing independent override of 'url' and 'token'.
        For example, a check can override only the token while using the global url,
        or vice versa.

        Args:
            global_config: Global configuration from YAML
            check_config: Check-level configuration dictionary

        Returns:
            Merged uptime_kuma config dict with both url and token, or None if no config available

        Priority (per field):
            1. Check-level value (highest) - if present, overrides global
            2. Global value (middle) - used as fallback if check-level not present
            3. None (lowest) - if neither check nor global has the field

        Examples:
            - Check has token only, global has both: result has both (check's token + global's url)
            - Check has url only, global has both: result has both (check's url + global's token)
            - Check has both, global has both: result uses all check values (complete override)
        """
        if "uptime_kuma" in check_config:
            # Merge check-level uptime_kuma with global config (field-level merging)
            check_uptime = check_config["uptime_kuma"] or {}
            global_uptime = (
                global_config.uptime_kuma.model_dump()
                if global_config.uptime_kuma
                else {}
            )
            # Merge: use check values only if they're not None, else fall back to global
            merged = {**global_uptime}
            for key, value in check_uptime.items():
                if value is not None:
                    merged[key] = value
            return merged if merged else None
        elif global_config.uptime_kuma:
            # Use global uptime_kuma if check doesn't have one
            return global_config.uptime_kuma.model_dump()

        return None

    @staticmethod
    def merge_tag_uptime_kuma_config(
        global_config: GlobalConfig, tag_config: dict
    ) -> Optional[dict]:
        """Merge uptime_kuma config for tags from tag-level and global sources.

        Supports field-level merging, allowing independent override of 'url' and 'token'.

        Args:
            global_config: Global configuration from YAML
            tag_config: Tag-level configuration dictionary

        Returns:
            Merged uptime_kuma config dict with both url and token, or None if no config available

        Priority (per field):
            1. Tag-level value (highest) - if present and not None, overrides global
            2. Global value (middle) - used as fallback if tag-level not present or is None
            3. None (lowest) - if neither tag nor global has the field
        """
        if "uptime_kuma" in tag_config:
            # Merge tag-level uptime_kuma with global config (field-level merging)
            tag_uptime = tag_config["uptime_kuma"] or {}
            global_uptime = (
                global_config.uptime_kuma.model_dump()
                if global_config.uptime_kuma
                else {}
            )
            # Merge: use tag values only if they're not None, else fall back to global
            merged = {**global_uptime}
            for key, value in tag_uptime.items():
                if value is not None:
                    merged[key] = value
            return merged if merged else None
        elif global_config.uptime_kuma:
            # Use global uptime_kuma if tag doesn't have one
            return global_config.uptime_kuma.model_dump()

        return None

    @staticmethod
    def merge_ssh_config(
        global_config: GlobalConfig, check_config: dict
    ) -> Optional[dict]:
        """Merge SSH config from global and check-level sources.

        Args:
            global_config: Global configuration from YAML
            check_config: Check-level configuration dictionary

        Returns:
            Merged SSH config dict, or None if no config available

        Priority:
            1. Check-level config (highest)
            2. Global config (middle)
            3. None (lowest)
        """
        if "ssh" in check_config:
            # Merge check-level ssh with global config
            check_ssh = check_config["ssh"]
            global_ssh = global_config.ssh.model_dump() if global_config.ssh else {}
            return {**global_ssh, **check_ssh}
        elif global_config.ssh:
            # Use global ssh if check doesn't have one
            return global_config.ssh.model_dump()

        return None

    @staticmethod
    def merge_heartbeat_uptime_kuma_config(
        global_config: GlobalConfig,
    ) -> tuple[Optional[str], Optional[str]]:
        """Merge heartbeat uptime_kuma config with global uptime_kuma.

        Returns merged URL and token for heartbeat initialization.

        Logic:
            URL: Use heartbeat.uptime_kuma.url if set, else fall back to global.uptime_kuma.url
            Token: Use heartbeat.uptime_kuma.token if set (required for heartbeat)

        Args:
            global_config: Global configuration with heartbeat and uptime_kuma settings

        Returns:
            Tuple of (url, token) both Optional[str]. Token can be None (caller must handle).
        """
        heartbeat_config = global_config.heartbeat
        global_uptime = global_config.uptime_kuma
        heartbeat_uptime = heartbeat_config.uptime_kuma

        # Determine URL: heartbeat-specific first, then fall back to global
        url: Optional[str] = None
        if heartbeat_uptime and heartbeat_uptime.url:
            url = heartbeat_uptime.url
        elif global_uptime and global_uptime.url:
            url = global_uptime.url

        # Determine token: heartbeat-specific only (required field)
        token: Optional[str] = heartbeat_uptime.token if heartbeat_uptime else None

        return url, token

    @staticmethod
    def apply_timeout(merged_config: dict, global_config: GlobalConfig) -> None:
        """Apply timeout from global config if not in check config.

        Args:
            merged_config: Check configuration dictionary to update
            global_config: Global configuration providing defaults

        Note:
            Only applies timeout if:
            1. Not already in merged_config (check-level takes precedence)
            2. Not default value (300 seconds)

        Priority:
            1. Check-level config (already in merged_config)
            2. Global config (applied if global != DEFAULT_TIMEOUT)
            3. Default timeout (implicit)
        """
        if "timeout" not in merged_config and global_config.timeout != DEFAULT_TIMEOUT:
            merged_config["timeout"] = global_config.timeout

    @staticmethod
    def apply_quiet_verbose_overrides(
        global_config: GlobalConfig,
        quiet: bool,
        verbose: bool,
        log_level: Optional[str],
    ) -> None:
        """Apply quiet and verbose flags to global configuration.

        Args:
            global_config: Global configuration to update
            quiet: CLI-provided quiet flag
            verbose: CLI-provided verbose flag
            log_level: CLI-provided log level (may affect verbose behavior)

        Note:
            quiet and verbose are mutually exclusive and validated by GlobalConfig.
        """
        if quiet:
            global_config.quiet = True
        if verbose:
            global_config.verbose = True
            # Verbose mode sets log level to DEBUG if not already explicitly set
            if log_level is None:
                global_config.logging.level = "DEBUG"

    @staticmethod
    def apply_cli_to_global_config(
        global_config: GlobalConfig,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        heartbeat_token: Optional[str],
        timeout: Optional[int],
        log_file: Optional[str],
        log_level: Optional[str],
        quiet: bool = False,
        verbose: bool = False,
    ) -> None:
        """Apply CLI argument overrides to the global configuration.

        Args:
            global_config: Global configuration to update
            uptime_kuma_url: CLI-provided Uptime Kuma URL
            token: CLI-provided Uptime Kuma token
            heartbeat_token: CLI-provided heartbeat token
            timeout: CLI-provided timeout in seconds (None if not provided)
            log_file: CLI-provided log file path
            log_level: CLI-provided log level
            quiet: CLI-provided quiet flag
            verbose: CLI-provided verbose flag

        Note:
            This applies CLI values to the global config (fallback layer).
            Per-check precedence is enforced separately by apply_cli_to_checks().
            quiet and verbose are mutually exclusive and validated by GlobalConfig.
        """
        if uptime_kuma_url:
            if not global_config.uptime_kuma:
                global_config.uptime_kuma = UptimeKumaConfig(
                    url=uptime_kuma_url, token=token
                )
            else:
                global_config.uptime_kuma.url = uptime_kuma_url
                if token:
                    global_config.uptime_kuma.token = token

        if heartbeat_token:
            if not global_config.heartbeat.uptime_kuma:
                global_config.heartbeat.uptime_kuma = UptimeKumaConfig(
                    token=heartbeat_token
                )
            else:
                global_config.heartbeat.uptime_kuma.token = heartbeat_token

        if timeout is not None:
            global_config.timeout = timeout

        if log_file is not None:
            global_config.logging.file = log_file

        if log_level is not None:
            global_config.logging.level = log_level

        # Apply quiet/verbose overrides
        ConfigMerger.apply_quiet_verbose_overrides(
            global_config, quiet, verbose, log_level
        )

    @staticmethod
    def _check_config(check) -> dict:
        """Unpack a check tuple into its config dict.

        Accepts both (plugin_type, config_dict) tuples and plain config dicts.
        """
        if isinstance(check, tuple) and len(check) == 2:
            return check[1]
        return check

    @staticmethod
    def _cli_ssh_config(
        global_config: GlobalConfig, cli_ssh: bool
    ) -> Optional["SSHConfig"]:
        """Resolve the CLI-derived global SSH config, if a CLI SSH host was given.

        Raises:
            ValueError: if a CLI SSH host was given but no global SSH config exists
        """
        if not cli_ssh:
            return None
        # Invariant: a CLI SSH host implies global ssh config was created by the
        # CLI SSH setup (validation rejects ssh options without a host).
        if global_config.ssh is None:
            raise ValueError(
                "CLI SSH host provided but no SSH config was created "
                "(internal invariant violated)"
            )
        return global_config.ssh

    @staticmethod
    def apply_cli_to_checks(
        checks: list,
        global_config: GlobalConfig,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
        timeout: Optional[int],
        ssh: Optional[str],
    ) -> None:
        """Enforce CLI values as highest priority over per-check and per-tag config.

        Runs after all merging so the downstream per-check merge respects the
        CLI values written into the per-check configs.

        Args:
            checks: List of check tuples (plugin_type, config_dict)
            global_config: Global configuration (CLI already applied)
            uptime_kuma_url: CLI-provided Uptime Kuma URL
            token: CLI-provided Uptime Kuma token
            timeout: CLI-provided timeout in seconds (None if not provided)
            ssh: CLI-provided SSH connection string

        Note:
            Applies only when the CLI value is provided and non-empty:
            - timeout is forced onto every check when provided (including the
              DEFAULT_TIMEOUT value, which is no longer used as a sentinel)
            - uptime_kuma url/token are forced onto checks and tags when a CLI
              url is given; token requires the CLI url (mirrors
              apply_cli_to_global_config)
            - ssh replaces per-check ssh entirely with the CLI-derived global ssh
        """
        cli_uptime = bool(uptime_kuma_url)
        cli_ssh_config = ConfigMerger._cli_ssh_config(global_config, bool(ssh))

        for check in checks:
            check_config = ConfigMerger._check_config(check)

            if timeout is not None:
                check_config["timeout"] = timeout
            if cli_uptime:
                uptime_kuma = check_config.setdefault("uptime_kuma", {})
                uptime_kuma["url"] = uptime_kuma_url
                if token:
                    uptime_kuma["token"] = token
            if cli_ssh_config is not None:
                check_config["ssh"] = cli_ssh_config.model_dump()

        if cli_uptime:
            ConfigMerger._apply_cli_uptime_to_tags(
                global_config, uptime_kuma_url, token
            )

    @staticmethod
    def _apply_cli_uptime_to_tags(
        global_config: GlobalConfig,
        uptime_kuma_url: Optional[str],
        token: Optional[str],
    ) -> None:
        """Enforce CLI uptime_kuma url/token over tag aggregation config."""
        if not uptime_kuma_url or not global_config.tags:
            return
        for tag in global_config.tags.values():
            uptime_kuma = tag.uptime_kuma or UptimeKumaConfig()
            uptime_kuma.url = uptime_kuma_url
            if token:
                uptime_kuma.token = token
            tag.uptime_kuma = uptime_kuma

    @staticmethod
    def apply_cli_ssh_config(
        global_config: GlobalConfig,
        host: str,
        user: Optional[str],
        port: Optional[int],
        key_file: Optional[str],
        password: Optional[str],
        strict_host_key_checking: bool,
    ) -> None:
        """Apply parsed SSH CLI arguments to global configuration.

        Args:
            global_config: Global configuration to update
            host: SSH host (required, already validated)
            user: SSH username (optional)
            port: SSH port (optional)
            key_file: Path to SSH private key (optional)
            password: SSH password (optional, discouraged)
            strict_host_key_checking: Whether to verify host keys

        Note:
            This method expects pre-parsed SSH connection data.
            Use parse_ssh_connection_string() to extract components from "user@host:port" format.
        """
        if not global_config.ssh:
            global_config.ssh = SSHConfig(host=host, user=user, port=port or 22)
        else:
            global_config.ssh.host = host
            if user:
                global_config.ssh.user = user
            if port:
                global_config.ssh.port = port

        # Set additional SSH options if provided
        if key_file:
            global_config.ssh.key_file = key_file

        if password:
            global_config.ssh.password = password

        global_config.ssh.strict_host_key_checking = strict_host_key_checking

    @staticmethod
    def merge_all_tags_configs(global_config: GlobalConfig) -> None:
        """Merge uptime_kuma config for all tags with global config.

        Modifies global_config.tags in-place, replacing each tag's uptime_kuma
        config with fully merged version (field-level merging from check and global).

        Args:
            global_config: Global configuration containing tags to merge
        """
        if not global_config.tags:
            return

        for _tag_name, tag_config in global_config.tags.items():
            # Build tag config dict with uptime_kuma if present
            tag_config_dict = {}
            if tag_config.uptime_kuma:
                tag_config_dict["uptime_kuma"] = tag_config.uptime_kuma.model_dump()

            # Merge with global config
            merged_uptime = ConfigMerger.merge_tag_uptime_kuma_config(
                global_config, tag_config_dict
            )

            # Update tag config with merged uptime_kuma
            if merged_uptime:
                tag_config.uptime_kuma = UptimeKumaConfig(**merged_uptime)
            else:
                tag_config.uptime_kuma = None

    @staticmethod
    def merge_all_checks_configs(checks: list, global_config: GlobalConfig) -> None:
        """Merge uptime_kuma config for all checks with global config.

        Modifies each check dict in-place, replacing its uptime_kuma config with
        fully merged version (field-level merging from check and global).

        Args:
            checks: List of check tuples (plugin_type, config_dict) from load_config()
            global_config: Global configuration to merge from
        """
        if not checks:
            return

        for check_tuple in checks:
            # Unpack check tuple: (plugin_type, check_config)
            check_config = ConfigMerger._check_config(check_tuple)

            # Merge uptime_kuma for this check
            merged_uptime = ConfigMerger.merge_uptime_kuma_config(
                global_config, check_config
            )

            # Update check config with merged uptime_kuma
            if merged_uptime:
                check_config["uptime_kuma"] = merged_uptime
            else:
                check_config.pop("uptime_kuma", None)
