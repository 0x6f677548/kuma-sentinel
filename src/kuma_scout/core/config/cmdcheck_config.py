"""Command check configuration."""

import re
from typing import Any, Dict, List, Optional

from .base import ConfigBase, FieldMapping


class CmdCheckConfig(ConfigBase):
    """Configuration for cmdcheck command.

    Commands are always stored as a list, even for single commands.
    Each command can override defaults for timeout, expect_exit_code,
    success_pattern, failure_pattern.
    """

    def __init__(self):
        """Initialize command check configuration with defaults."""
        super().__init__()

        # Command check-specific attributes - always a list
        self.cmdcheck_commands: List[Dict[str, Any]] = []

        # Default values used when not specified in individual commands
        self.cmdcheck_timeout = 30
        self.cmdcheck_expect_exit_code = 0
        self.cmdcheck_success_pattern: Optional[str] = None
        self.cmdcheck_failure_pattern: Optional[str] = None
        self.cmdcheck_sanitize_output = True  # Mask sensitive data by default

    def _get_command_name(self) -> str:
        """Get the command name for command-specific configuration."""
        return "cmdcheck"

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for command check configuration."""
        mappings = super()._get_field_mappings()
        mappings.update(
            {
                "cmdcheck_commands": FieldMapping(
                    arg_key="command",
                    yaml_path="cmdcheck.commands",
                    converter=self._normalize_commands,
                    expand_env_vars=True,
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
                    env_var="KUMA_SCOUT_CMDCHECK_TOKEN",
                    yaml_path="cmdcheck.uptime_kuma.token",
                    expand_env_vars=True,
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
        - Tuple from Typer CLI
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

        # Tuple from Typer (repeatable argument)
        if isinstance(commands_input, tuple):
            return [{"command": str(item)} for item in commands_input]

        return []

    def validate(self, validate_tokens: bool = True, validate_heartbeat_token: bool = True):
        """Validate command check configuration."""
        # For cmdcheck, we always validate URL but handle tokens specially
        # Skip base token validation and do our own
        super().validate(validate_tokens=False, validate_heartbeat_token=validate_heartbeat_token)

        # Custom token validation for cmdcheck (allows per-command tokens)
        token_errors = self._validate_cmdcheck_tokens()
        if token_errors:
            error_message = "Configuration validation failed:\n  " + "\n  ".join(token_errors)
            if self.logger:
                self.logger.error(
                    f"❌ Configuration validation failed with {len(token_errors)} error(s)"
                )
                for error in token_errors:
                    self.logger.error(f"   - {error}")
            raise ValueError(error_message)

        # Cmdcheck-specific validations
        errors = []
        errors.extend(self._validate_command_specification())
        errors.extend(self._validate_timeout_and_exit_code())
        errors.extend(self._validate_regex_patterns())
        errors.extend(self._validate_individual_commands())

        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def _validate_cmdcheck_tokens(self) -> List[str]:
        """Validate command tokens for cmdcheck, allowing per-command tokens.

        Note: Heartbeat token validation is handled by base class.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Command token validation: allow global token OR all commands having tokens
        if self.command_token:
            # Global token provided - use it
            pass
        else:
            # No global token - check that all commands have their own tokens
            token_errors = self._validate_per_command_tokens()
            errors.extend(token_errors)

        return errors

    def _validate_per_command_tokens(self) -> List[str]:
        """Validate that all commands have per-command tokens when no global token exists.

        Returns:
            List of error messages (empty if valid)
        """
        if not self.cmdcheck_commands:
            return ["Command push token not provided (use --token)"]

        commands_without_tokens = []
        for idx, cmd_config in enumerate(self.cmdcheck_commands):
            if not isinstance(cmd_config, dict):
                continue
            if not self._command_has_valid_token(cmd_config):
                commands_without_tokens.append(idx)

        if not commands_without_tokens:
            return []

        if len(commands_without_tokens) == 1:
            return [f"Command {commands_without_tokens[0]} missing uptime_kuma.token "
                   "(provide global --token or per-command token)"]
        else:
            cmd_list = ", ".join(str(i) for i in commands_without_tokens)
            return [f"Commands {cmd_list} missing uptime_kuma.token "
                   "(provide global --token or per-command tokens)"]

    def _command_has_valid_token(self, cmd_config: Dict[str, Any]) -> bool:
        """Check if a command configuration has a valid per-command token.

        Args:
            cmd_config: Command configuration dictionary

        Returns:
            True if command has valid token, False otherwise
        """
        if "uptime_kuma" not in cmd_config:
            return False

        uptime_kuma = cmd_config["uptime_kuma"]
        if not isinstance(uptime_kuma, dict):
            return False

        if "token" not in uptime_kuma:
            return False

        token = uptime_kuma["token"]
        return isinstance(token, str) and bool(token.strip())

    def _validate_command_specification(self) -> List[str]:
        """Validate that at least one command is provided."""
        errors: List[str] = []

        if not self.cmdcheck_commands:
            errors.append("Must specify at least one command (use --command)")

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
        errors.extend(self._validate_command_token(idx, cmd_config))

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

    def _validate_command_token(
        self, idx: int, cmd_config: Dict[str, Any]
    ) -> List[str]:
        """Validate per-command token field."""
        errors: List[str] = []

        if "uptime_kuma" not in cmd_config:
            return errors

        uptime_kuma = cmd_config["uptime_kuma"]
        if not isinstance(uptime_kuma, dict):
            errors.append(f"Command {idx} uptime_kuma must be a dictionary")
            return errors

        if "token" not in uptime_kuma:
            return errors

        token = uptime_kuma["token"]
        if not isinstance(token, str) or not token.strip():
            errors.append(f"Command {idx} uptime_kuma.token must be a non-empty string")

        return errors

    def get_summary(self) -> dict:
        """Get command check configuration summary for logging.

        Returns:
            Dictionary with configuration summary
        """
        if not self.cmdcheck_commands:
            pass
        elif len(self.cmdcheck_commands) == 1:
            cmd_config = self.cmdcheck_commands[0]
            cmd_text = cmd_config.get("command", "")
            cmd_text[:60] + "..." if len(cmd_text) > 60 else cmd_text
        else:
            f"{len(self.cmdcheck_commands)} commands configured"

        # Get base summary and add cmdcheck-specific fields
        summary = super().get_summary()
        summary.update(
            {
                "cmdcheck_total_commands": str(len(self.cmdcheck_commands)),
                "cmdcheck_timeout": f"{self.cmdcheck_timeout}s",
                "cmdcheck_expect_exit_code": str(self.cmdcheck_expect_exit_code),
                "cmdcheck_success_pattern": self.cmdcheck_success_pattern or "None",
                "cmdcheck_failure_pattern": self.cmdcheck_failure_pattern or "None",
            }
        )
        return summary
