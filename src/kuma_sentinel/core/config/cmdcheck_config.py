"""Command check configuration."""

import re
from typing import Any, Dict, List, Optional

from .base import ConfigBase, FieldMapping


class CmdCheckConfig(ConfigBase):
    """Configuration for cmdcheck command.

    Commands are always stored as a list, even for single commands.
    Each command can override defaults for timeout, expect_exit_code,
    success_pattern, failure_pattern, and capture_output.
    """

    def __init__(self):
        """Initialize command check configuration with defaults."""
        super().__init__()

        # Command check-specific attributes - always a list
        self.cmdcheck_commands: List[Dict[str, Any]] = []

        # Default values used when not specified in individual commands
        self.cmdcheck_timeout = 30
        self.cmdcheck_expect_exit_code = 0
        self.cmdcheck_capture_output = True
        self.cmdcheck_success_pattern: Optional[str] = None
        self.cmdcheck_failure_pattern: Optional[str] = None
        self.cmdcheck_sanitize_output = True  # Mask sensitive data by default

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for command check configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "cmdcheck_commands": FieldMapping(
                    arg_key="command",
                    yaml_path="cmdcheck.commands",
                    converter=self._normalize_commands,
                ),
                "cmdcheck_timeout": FieldMapping(
                    arg_key="timeout",
                    yaml_path="cmdcheck.timeout",
                    converter=int,
                ),
                "cmdcheck_expect_exit_code": FieldMapping(
                    arg_key="expect_exit_code",
                    yaml_path="cmdcheck.expect_exit_code",
                    converter=int,
                ),
                "cmdcheck_capture_output": FieldMapping(
                    arg_key="capture_output",
                    yaml_path="cmdcheck.capture_output",
                    converter=self._parse_bool,
                ),
                "cmdcheck_success_pattern": FieldMapping(
                    arg_key="success_pattern",
                    yaml_path="cmdcheck.success_pattern",
                ),
                "cmdcheck_failure_pattern": FieldMapping(
                    arg_key="failure_pattern",
                    yaml_path="cmdcheck.failure_pattern",
                ),
                "cmdcheck_sanitize_output": FieldMapping(
                    arg_key="sanitize_output",
                    yaml_path="cmdcheck.sanitize_output",
                    converter=self._parse_bool,
                ),
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_CMDCHECK_TOKEN",
                    yaml_path="cmdcheck.uptime_kuma.token",
                ),
            }
        )
        return mappings

    @staticmethod
    def _normalize_commands(commands_input: Any) -> List[Dict[str, Any]]:
        """Normalize commands input to list of command dicts.

        Handles:
        - Single command string (wraps in list)
        - List of dicts from YAML
        - Tuple from Click CLI
        - Already converted lists

        Args:
            commands_input: Input in one of the formats above

        Returns:
            Normalized list of command dicts with defaults applied
        """
        if not commands_input:
            return []

        # Single command string from CLI
        if isinstance(commands_input, str):
            return [{"command": commands_input}]

        # List input
        if isinstance(commands_input, list):
            result = []
            for cmd in commands_input:
                if isinstance(cmd, dict):
                    result.append(cmd)
                elif isinstance(cmd, str):
                    result.append({"command": cmd})
                elif isinstance(cmd, (tuple, list)):
                    # Convert tuple/list to dict
                    cmd_dict = {"command": cmd[0]} if len(cmd) > 0 else {}
                    if len(cmd) > 1 and isinstance(cmd[1], dict):
                        cmd_dict.update(cmd[1])
                    result.append(cmd_dict)
            return result

        # Tuple from Click (repeatable argument)
        if isinstance(commands_input, tuple):
            return [{"command": str(item)} for item in commands_input]

        return []

    def validate(self):
        """Validate command check configuration."""
        super().validate()

        errors = []
        errors.extend(self._validate_command_specification())
        errors.extend(self._validate_timeout_and_exit_code())
        errors.extend(self._validate_regex_patterns())
        errors.extend(self._validate_individual_commands())

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def _validate_command_specification(self) -> List[str]:
        """Validate that at least one command is provided."""
        errors: List[str] = []

        if not self.cmdcheck_commands:
            errors.append("Must specify at least one command in 'commands' list")

        return errors

    def _validate_timeout_and_exit_code(self) -> List[str]:
        """Validate timeout and exit code values."""
        errors: List[str] = []

        if self.cmdcheck_timeout <= 0 or self.cmdcheck_timeout > 300:
            errors.append(
                f"Timeout must be between 1 and 300 seconds, got {self.cmdcheck_timeout}"
            )

        if self.cmdcheck_expect_exit_code < 0 or self.cmdcheck_expect_exit_code > 255:
            errors.append(
                f"Exit code must be between 0 and 255, got {self.cmdcheck_expect_exit_code}"
            )

        return errors

    def _validate_regex_patterns(self) -> List[str]:
        """Validate success and failure regex patterns."""
        errors: List[str] = []

        if self.cmdcheck_success_pattern:
            try:
                re.compile(self.cmdcheck_success_pattern)
            except re.error as e:
                errors.append(f"Invalid success_pattern regex: {e}")

        if self.cmdcheck_failure_pattern:
            try:
                re.compile(self.cmdcheck_failure_pattern)
            except re.error as e:
                errors.append(f"Invalid failure_pattern regex: {e}")

        return errors

    def _validate_individual_commands(self) -> List[str]:
        """Validate individual command configurations in multiple mode."""
        errors: List[str] = []

        if not self.cmdcheck_commands:
            return errors

        for idx, cmd_config in enumerate(self.cmdcheck_commands):
            if not isinstance(cmd_config, dict):
                errors.append(f"Command {idx} must be a dictionary")
                continue

            errors.extend(self._validate_command_config(idx, cmd_config))

        return errors

    def _validate_command_config(
        self, idx: int, cmd_config: Dict[str, Any]
    ) -> List[str]:
        """Validate a single command configuration."""
        errors: List[str] = []

        # Validate command field presence and value
        if "command" not in cmd_config:
            errors.append(f"Command {idx} missing 'command' field")
            return errors

        if not cmd_config["command"]:
            errors.append(f"Command {idx} has empty command string")

        errors.extend(self._validate_command_field(idx, "timeout", cmd_config))
        errors.extend(self._validate_command_field(idx, "expect_exit_code", cmd_config))
        errors.extend(
            self._validate_command_pattern(idx, "success_pattern", cmd_config)
        )
        errors.extend(
            self._validate_command_pattern(idx, "failure_pattern", cmd_config)
        )

        return errors

    def _validate_command_field(
        self, idx: int, field: str, cmd_config: Dict[str, Any]
    ) -> List[str]:
        """Validate numeric command fields (timeout, exit_code)."""
        errors: List[str] = []

        if field not in cmd_config:
            return errors

        value = cmd_config[field]
        if field == "timeout":
            if value <= 0 or value > 300:
                errors.append(f"Command {idx} timeout must be 1-300, got {value}")
        elif field == "expect_exit_code":
            if value < 0 or value > 255:
                errors.append(f"Command {idx} exit code must be 0-255, got {value}")

        return errors

    def _validate_command_pattern(
        self, idx: int, field: str, cmd_config: Dict[str, Any]
    ) -> List[str]:
        """Validate regex pattern command fields."""
        errors: List[str] = []

        if field not in cmd_config:
            return errors

        try:
            re.compile(cmd_config[field])
        except re.error as e:
            errors.append(f"Command {idx} invalid {field}: {e}")

        return errors

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get command check configuration summary for logging.

        Args:
            mask_tokens: Whether to mask sensitive tokens in output

        Returns:
            Dictionary with configuration summary
        """
        if not self.cmdcheck_commands:
            cmd_summary = "No commands configured"
        elif len(self.cmdcheck_commands) == 1:
            cmd_config = self.cmdcheck_commands[0]
            cmd_text = cmd_config.get("command", "")
            cmd_display = cmd_text[:60] + "..." if len(cmd_text) > 60 else cmd_text
            cmd_summary = f"1 command: '{cmd_display}'"
        else:
            cmd_summary = f"{len(self.cmdcheck_commands)} commands configured"

        return {
            "🔧 Command Configuration": {
                "Command(s)": cmd_summary,
                "Timeout": f"{self.cmdcheck_timeout}s",
                "Expected Exit Code": str(self.cmdcheck_expect_exit_code),
                "Capture Output": "Yes" if self.cmdcheck_capture_output else "No",
                "Success Pattern": self.cmdcheck_success_pattern or "None",
                "Failure Pattern": self.cmdcheck_failure_pattern or "None",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": self.uptime_kuma_url or "Not configured",
                "Heartbeat Enabled": "Yes" if self.heartbeat_enabled else "No",
                "Command Token": self._mask_token(self.command_token, mask_tokens),
            },
        }
