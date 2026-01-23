"""Command check configuration."""

import re
from typing import Any, Dict, List, Optional

from .base import ConfigBase, FieldMapping


class CmdCheckConfig(ConfigBase):
    """Configuration for cmdcheck command."""

    def __init__(self):
        """Initialize command check configuration with defaults."""
        super().__init__()

        # Command check-specific attributes
        self.cmdcheck_command: Optional[str] = None
        self.cmdcheck_commands: List[Dict[str, Any]] = []
        self.cmdcheck_multiple = False
        self.cmdcheck_timeout = 30
        self.cmdcheck_expect_exit_code = 0
        self.cmdcheck_capture_output = True
        self.cmdcheck_success_pattern: Optional[str] = None
        self.cmdcheck_failure_pattern: Optional[str] = None

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for command check configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "cmdcheck_command": FieldMapping(
                    arg_key="command",
                    yaml_path="cmdcheck.command",
                ),
                "cmdcheck_commands": FieldMapping(
                    arg_key="commands",
                    yaml_path="cmdcheck.commands",
                    converter=self._commands_converter,
                ),
                "cmdcheck_multiple": FieldMapping(
                    yaml_path="cmdcheck.multiple",
                    converter=self._parse_bool,
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
                "command_token": FieldMapping(
                    env_var="KUMA_SENTINEL_CMDCHECK_TOKEN",
                    yaml_path="cmdcheck.uptime_kuma.token",
                ),
            }
        )
        return mappings

    @staticmethod
    def _commands_converter(commands_input: Any) -> List[Dict[str, Any]]:
        """Convert commands input to normalized format.

        Handles:
        - List of dicts from YAML
        - Tuple of tuples from Click CLI
        - Already converted lists

        Args:
            commands_input: Input in one of the formats above

        Returns:
            Normalized list of command dicts
        """
        if isinstance(commands_input, list):
            # From YAML or already converted
            result = []
            for cmd in commands_input:
                if isinstance(cmd, dict):
                    result.append(cmd)
                elif isinstance(cmd, (tuple, list)):
                    # Convert tuple to dict
                    cmd_dict = {"command": cmd[0]} if len(cmd) > 0 else {}
                    if len(cmd) > 1:
                        cmd_dict.update(cmd[1])  # Merge additional properties
                    result.append(cmd_dict)
            return result

        # Try to parse as Click tuples (from --command repeatable)
        try:
            if isinstance(commands_input, (tuple, list)):
                result = []
                for item in commands_input:
                    if isinstance(item, dict):
                        result.append(item)
                    else:
                        result.append({"command": str(item)})
                return result
        except (TypeError, ValueError):
            pass

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
        """Validate that exactly one command specification is provided."""
        errors: List[str] = []
        has_command = bool(self.cmdcheck_command)
        has_commands = bool(self.cmdcheck_commands)

        if not has_command and not has_commands:
            errors.append(
                "Must specify either 'command' (single) or 'commands' (multiple)"
            )

        if has_command and has_commands:
            errors.append(
                "Cannot specify both 'command' and 'commands' - use one or the other"
            )

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
        if self.cmdcheck_multiple:
            cmd_summary = f"{len(self.cmdcheck_commands)} commands configured"
        elif self.cmdcheck_command:
            # Truncate command to 60 chars for display
            cmd_display = (
                self.cmdcheck_command[:60] + "..."
                if len(self.cmdcheck_command) > 60
                else self.cmdcheck_command
            )
            cmd_summary = f"'{cmd_display}'"
        else:
            cmd_summary = "No command configured"

        return {
            "🔧 Command Configuration": {
                "Command(s)": cmd_summary,
                "Mode": "Multiple" if self.cmdcheck_multiple else "Single",
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
