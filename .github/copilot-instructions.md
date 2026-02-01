# Kuma-Scout AI Coding Instructions

## Project Overview
Kuma-Scout is a Python CLI monitoring agent for Uptime Kuma that executes custom checks, port scans, backup monitoring, and storage checks—locally or via SSH remote execution. It reports results to Uptime Kuma's push API.

**Architecture**: Typer CLI → Config Classes → Checker Implementations → Uptime Kuma API

## Key Components
- **CLI Layer** (`src/kuma_scout/cli/`): Typer commands with unified executor pattern
- **Config System** (`src/kuma_scout/core/config/`): Declarative FieldMapping for YAML/CLI/env integration
- **Checkers** (`src/kuma_scout/core/checkers/`): Monitoring logic implementations
- **Core Models** (`src/kuma_scout/core/models.py`): `CheckResult` dataclass with status/message/duration

## Development Workflow
```bash
# Setup
uv sync --all-extras

# Test & Quality
hatch run test                    # pytest with coverage
hatch run lint --fix             # ruff auto-fix
hatch run format                 # black formatting
hatch run check                  # lint + format + mypy

# Build
uv build
```

## Adding New Commands
1. **Create Checker** (`src/kuma_scout/core/checkers/my_checker.py`): Extend `Checker` base class
2. **Create Config** (`src/kuma_scout/core/config/my_config.py`): Extend `ConfigBase` with FieldMapping
3. **Create Command** (`src/kuma_scout/cli/commands/mycheck.py`): Extend `CommandExecutor` with `@register_command`
4. **Add Tests** (`tests/commands/test_mycheck.py`): Mirror command structure

## Configuration Patterns
**Priority**: CLI args > YAML config > env vars (tokens only) > defaults

**YAML Structure**:
```yaml
command_name:
  setting: value
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: your-token
heartbeat:
  enabled: true
  interval: 300
ssh:
  connection: user@host
  key_file: /path/to/key
```

**Field Mapping Example**:
```python
def _get_field_mappings(self) -> Dict[str, FieldMapping]:
    return {
        "my_setting": FieldMapping(
            yaml_path="command.my_setting",
            arg_key="my-setting",
            env_var="KUMA_SCOUT_MY_TOKEN",
            converter=int,
        ),
    }
```

## SSH Remote Execution
All commands support `--ssh user@host` for remote execution. SSH settings configurable globally or per-command.

## Testing Patterns
- **Unit Tests**: Test checkers in isolation with mocked dependencies
- **Integration Tests**: Test full command execution with temp configs
- **CLI Tests**: Test argument parsing and validation
- Use `pytest` with coverage reporting to `htmlcov/`

## Code Quality
- **Linting**: ruff (E, W, F, I, C, B, UP rules)
- **Formatting**: black (88 char lines)
- **Typing**: mypy with `check_untyped_defs = true`
- **Imports**: isort via ruff

## Security Considerations
- Commands executed without shell interpretation (prevent injection)
- SSH strict host key checking enabled by default
- Token environment variables for sensitive auth
- File permission validation for config/key files

## Common Patterns
- **Error Handling**: Return `CheckResult(is_success=False, message=error)` on failures
- **Logging**: Use `self.logger` in checkers for debug/info messages
- **Validation**: Config classes validate settings in `validate()` method
- **Timeouts**: Respect `timeout` settings in long-running operations
- **Heartbeats**: Send periodic pings during extended checks via heartbeat service


# Other important notes that you should have in mind
## tests
- tests should always pass
- write tests for new features and changes
- always use hatch to run tests
- keep code coverage above 90% when possible.
## code style
- adhere to existing coding style and patterns
- ensure proper typing and docstrings for new code
- maintain security best practices, especially around command execution and sensitive data.
- follow the established project structure and conventions
- do not introduce any new dependencies without approval
- when introducing new features or making considerable refactors, ensure that code quality tools (ruff, black, mypy) report no issues. You may use auto fix where applicable, including hatch run lint --fix and hatch run format
- never apply fixes like ignoring errors from code quality tools unless explicitly instructed
  - if you find code that has ignored errors from code quality tools, try to fix the underlying issue instead of adding more ignores
  - never, ever, use solutions like ' # type: ignore[return]' or similar unless explicitly instructed
## security
- always use DataSanitizer to sanitize any output sent to Uptime Kuma
## documentation
- always update readme.md if there are macro changes
- update doc/CONFIGURATION_GUIDE.md for any config changes
- update doc/DEVELOPMENT.MD for any changes to development workflow or the main architecture (writing new commands, checkers, etc)

## backward compatibility
- don't worry about backward compatibility unless explicitly instructed
- if there are config breaking changes, document them clearly in doc/CONFIGURATION_GUIDE.md and doc/MIGRATION.md, only if it is a breaking change compared to the last released version


## planning
- every time you start working on a new feature or a considerable change, create a plan first if not provided
- always include the impact of the change on documentation, tests, and backward compatibility in your plan