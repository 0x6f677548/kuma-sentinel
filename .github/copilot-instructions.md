# Kuma-Scout AI Coding Instructions

## Project Overview
Kuma-Scout is a Python CLI monitoring agent for Uptime Kuma that executes custom checks, port scans, backup monitoring, and storage checks—locally or via SSH remote execution. It reports results to Uptime Kuma's push API.

**Architecture**: Plugin-based system with auto-discovery → Pydantic v2 config/CLI generation → Check execution → Uptime Kuma API

## Key Components
- **CLI Layer** (`src/kuma_scout/cli/`): Auto-generated Typer commands from Pydantic models
- **Plugin System** (`src/kuma_scout/plugins/`): Single-file plugins combining config, CLI, and execution logic
- **Config System** (`src/kuma_scout/core/config_loader.py`): YAML loading with Pydantic validation
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

## Adding New Plugins
1. **Create Plugin** (`src/kuma_scout/plugins/my_plugin.py`): Single file with config class extending `CheckConfig` and plugin class extending `Plugin`
2. **Add Tests** (`tests/plugins/test_my_plugin.py`): Test plugin execution and config validation
3. **Update Config** (`example.config.yaml`): Add example check configuration

**Total: ~60-80 lines** (vs ~525 lines in old architecture)

## Configuration Patterns
**Priority**: CLI args > YAML config > defaults (variable expansion via `${VAR}` supported for all values)

**YAML Structure**:
```yaml
# Global settings
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}

logging:
  level: INFO

ssh:
  host: user@server.local
  key_file: ~/.ssh/id_rsa

heartbeat:
  enabled: true
  interval: 300

# Checks list (flat structure)
checks:
  - name: nginx-health
    type: cmdcheck
    command: systemctl is-active nginx
    tags: [web, critical]

  - name: disk-space
    type: cmdcheck
    command: df -h /
    success_pattern: \b\d+%\b.*\b(?<90)
    tags: [storage]
```

## SSH Remote Execution
All plugins support `--ssh user@host` for remote execution. SSH settings configurable globally or per-check.

## Testing Patterns
- **Unit Tests**: Test plugins in isolation with mocked dependencies
- **Integration Tests**: Test full plugin execution with temp configs
- **CLI Tests**: Test auto-generated argument parsing and validation
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
- **Error Handling**: Return `CheckResult(status="down", message=error)` on failures
- **Logging**: Use `self.output_handler` in plugins for debug/info messages (echo=False for internal logs)
- **Validation**: Config classes use Pydantic validation automatically
- **Timeouts**: Respect `timeout` settings in long-running operations
- **Heartbeats**: Send periodic pings during extended checks via heartbeat service
- **Sanitization**: Always use `DataSanitizer` for output sent to Uptime Kuma


# Other important notes that you should have in mind
## tests
- tests should always pass
- write tests for new features and changes
- always use hatch to run tests
- keep code coverage above 90% when possible.
- if needing a yaml config file for tests, use pytest's tmp_path fixture to create it on the fly or the existing example.config.yaml in the root folder. never use the test.config.yaml file
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
- never use relative imports
## security
- always use DataSanitizer to sanitize any output sent to Uptime Kuma
## documentation
- always update readme.md if there are macro changes
- update doc/CONFIGURATION_GUIDE.md for any config changes
- update doc/DEVELOPMENT.MD for any changes to development workflow or the main architecture (writing new plugins, etc)
- make sure to update example.config.yaml for any config changes

## backward compatibility
- don't worry about backward compatibility unless explicitly instructed
- if there are config breaking changes, document them clearly in doc/CONFIGURATION_GUIDE.md and doc/MIGRATION.md, only if it is a breaking change compared to the last released version


## planning
- every time you start working on a new feature or a considerable change, create a plan first if not provided
- always include the impact of the change on documentation, tests, and backward compatibility in your plan