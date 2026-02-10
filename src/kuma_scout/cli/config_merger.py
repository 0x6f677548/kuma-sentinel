"""Config merging utility for Kuma Scout CLI.

This module provides centralized configuration merging logic to handle the
configuration priority: CLI arguments > YAML config > defaults.

All config merging operations follow this standard pattern:
1. CLI arguments have highest priority
2. YAML config provides middle-level settings
3. Defaults apply when nothing else is specified
"""

from typing import Optional

from kuma_scout.plugins.models import GlobalConfig, UptimeKumaConfig


class ConfigMerger:
    """Centralized configuration merging for consistent priority handling."""

    @staticmethod
    def merge_uptime_kuma_config(
        global_config: GlobalConfig, check_config: dict
    ) -> Optional[dict]:
        """Merge uptime_kuma config from global and check-level sources.

        Args:
            global_config: Global configuration from YAML
            check_config: Check-level configuration dictionary

        Returns:
            Merged uptime_kuma config dict, or None if no config available

        Priority:
            1. Check-level config (highest)
            2. Global config (middle)
            3. None (lowest)
        """
        if "uptime_kuma" in check_config:
            # Merge check-level uptime_kuma with global config
            check_uptime = check_config["uptime_kuma"]
            global_uptime = (
                global_config.uptime_kuma.model_dump()
                if global_config.uptime_kuma
                else {}
            )
            return {**global_uptime, **check_uptime}
        elif global_config.uptime_kuma:
            # Use global uptime_kuma if check doesn't have one
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
            2. Global config (applied if global != 300)
            3. Default 300 seconds (implicit)
        """
        if "timeout" not in merged_config and global_config.timeout != 300:
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
    def apply_cli_overrides(
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
        """Apply CLI argument overrides to global configuration.

        Args:
            global_config: Global configuration to update
            uptime_kuma_url: CLI-provided Uptime Kuma URL
            token: CLI-provided Uptime Kuma token
            heartbeat_token: CLI-provided heartbeat token
            timeout: CLI-provided timeout in seconds
            log_file: CLI-provided log file path
            log_level: CLI-provided log level
            quiet: CLI-provided quiet flag
            verbose: CLI-provided verbose flag

        Note:
            CLI arguments represent the highest priority in config hierarchy.
            They completely override YAML config values where specified.
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
            global_config.heartbeat.token = heartbeat_token

        if timeout != 300:  # Only override if not default
            global_config.timeout = timeout

        if log_file is not None:
            global_config.logging.file = log_file

        if log_level is not None:
            global_config.logging.level = log_level

        # Apply quiet/verbose overrides
        ConfigMerger.apply_quiet_verbose_overrides(
            global_config, quiet, verbose, log_level
        )
