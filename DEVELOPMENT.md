# Development Guide

## Quick Start

### 1. Clone and Setup

```bash
cd /code/projects/kuma-scout
```

### 2. Install in Development Mode

```bash
uv sync --all-extras
```

This installs:
- The package in editable mode
- All development dependencies (pytest, pytest-cov, black, ruff, mypy)

### 3. Verify Installation

```bash
kuma-scout --version
kuma-scout portscan --help
```

## Development Commands

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/kuma_scout

# Run specific test file
uv run pytest tests/test_config.py

# Run specific test
uv run pytest tests/test_config.py::test_config_defaults

# Verbose output
uv run pytest -v
```

### Code Formatting and Linting

```bash
# Check with ruff (linter)
uv run ruff check src/ tests/

# Fix linting issues automatically
uv run ruff check --fix src/ tests/

# Format with black
uv run black src/ tests/

# Check if formatting is needed
uv run black --check src/ tests/

# Type check with mypy (checks untyped function bodies)
uv run mypy src/ tests/

# Or use hatch scripts for convenience
hatch run lint          # Run ruff linter
hatch run format        # Format with black
hatch run format-check  # Check formatting without modifying
hatch run check         # Run ruff, black, and mypy checks
```

### Building the Package

```bash
# Build wheel and source distribution
uv build

# This creates:
# - dist/kuma_scout-x.y.z-py3-none-any.whl
# - dist/kuma_scout-x.y.z.tar.gz
```

## Project Structure

```
kuma-scout/
├── src/kuma_scout/
│   ├── cli/                    # CLI commands (portscan, kopiasnapshotstatus, etc.)
│   ├── core/                   # Core monitoring logic
│   │   ├── config/            # Configuration management (base + command configs)
│   │   ├── checkers/          # Monitoring implementations (portscan, kopia, zfs, etc.)
│   │   ├── models.py          # Data models (CheckResult, etc.)
│   │   ├── uptime_kuma.py     # Uptime Kuma API integration
│   │   ├── heartbeat.py       # Heartbeat service
│   │   └── logger.py          # Logging setup
│   ├── __init__.py            # Package exports
│   └── py.typed               # Type stub marker
│
├── tests/                      # Test suite (mirrors src structure)
│   ├── checkers/              # Checker unit tests
│   ├── commands/              # Command tests
│   └── test_config.py         # Configuration tests
│
├── pyproject.toml             # Project metadata, dependencies, tool configs
├── README.md                  # User documentation
├── CONFIGURATION_GUIDE.md     # Configuration examples for all commands
├── DEVELOPMENT.md             # This file - development guide
├── LICENSE                    # MIT License
├── example.config.yaml        # Example configuration template
```

### Directory Details

**src/kuma_scout/cli/** - Typer CLI commands
- `app.py` - Main entry point with `typer.Typer()` app
- `commands/` - Command implementations with unified executor pattern
- Each command implements the `Command` interface and returns a Typer-compatible function

**src/kuma_scout/core/config/** - Configuration management
- `base.py` - `ConfigBase` abstract class and `FieldMapping` declarative system
- Command-specific configs (e.g., `portscan_config.py`, `kopia_snapshot_config.py`)

**src/kuma_scout/core/checkers/** - Monitoring implementations
- `base.py` - `Checker` abstract base class
- Specific checkers (e.g., `port_checker.py`, `kopia_snapshot_checker.py`, `cmdcheck_checker.py`)

**tests/** - Test suite
- Mirrors the `src/` structure
## Key Configuration Files

### pyproject.toml

Main project configuration with:
- **[project]**: Package metadata, dependencies
- **[tool.black]**: Black formatter settings
- **[tool.ruff]**: Ruff linter configuration
- **[tool.mypy]**: Type checker configuration (with `check_untyped_defs = true`)
- **[tool.pytest.ini_options]**: pytest configuration

### Entry Point

The CLI entry point is defined in `pyproject.toml`:

```
[project.scripts]
kuma-scout = "kuma_scout.cli.app:app"
```

This creates the `kuma-scout` command that calls the `app` (Typer application) in `app.py`.

## Creating New Commands with Typer

This guide explains how to create new monitoring commands using the Kuma Scout framework with Typer CLI.

### Architecture Overview

Each command follows this architecture:

1. **Command Class** - Extends `CommandExecutor` with a `get_builtin_command()` method
2. **Typer Function** - Returns a function with type-hinted parameters for CLI arguments/options
3. **Config Class** - Handles configuration loading and validation
4. **Checker Class** - Implements the actual monitoring logic
5. **Registration** - Uses `@register_command` decorator for auto-discovery

### Step 1: Create a Checker (src/kuma_scout/core/checkers/my_checker.py)

```python
from kuma_scout.core.checkers.base import Checker
from kuma_scout.core.config.my_config import MyConfig

class MyChecker(Checker):
    \"\"\"My custom monitoring checker.\"\"\"
    
    def __init__(self, logger, config: MyConfig):
        self.logger = logger
        self.config = config
    
    def execute_with_heartbeat(self):
        \"\"\"Execute monitoring logic with heartbeat support.\"\"\"
        self.logger.info("Starting my check...")
        
        # Your monitoring logic here
        check_result = "success"  # or "failure"
        
        return CheckResult(
            check_name="my_command",
            status="up" if check_result == "success" else "down",
            message="Check completed successfully" if check_result == "success" else "Check failed",
            duration_seconds=1
        )
```

### Step 2: Create a Config Class (src/kuma_scout/core/config/my_config.py)

```python
from dataclasses import dataclass, field
from typing import Optional
from kuma_scout.core.config.base import ConfigBase, FieldMapping

@dataclass
class MyConfig(ConfigBase):
    \"\"\"Configuration for my custom command.\"\"\"
    
    # Command-specific settings
    my_option: Optional[str] = None
    my_timeout: int = 30
    
    def __init__(self):
        super().__init__()
        self.my_option = None
        self.my_timeout = 30
    
    def define_field_mappings(self):
        \"\"\"Define how config fields are loaded from all sources.\"\"\"
        self.field_mappings = {
            "my_option": FieldMapping(
                env_var="KUMA_SCOUT_MY_OPTION",
                arg_key="my_option",
                yaml_path="my_command.my_option"
            ),
            "my_timeout": FieldMapping(
                env_var="KUMA_SCOUT_MY_TIMEOUT",
                arg_key="my_timeout",
                yaml_path="my_command.my_timeout",
                converter=int
            ),
        }
```

### Step 3: Create a Command Class (src/kuma_scout/cli/commands/my_command.py)

```python
from typing import Callable, Dict, Optional
import typer
from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.my_checker import MyChecker
from kuma_scout.core.config.my_config import MyConfig

MY_EXAMPLES = \"\"\"
Examples:

  Basic usage:
  $ kuma-scout my-command \\\\
      http://uptimekuma:3001/api/push \\\\
      your-heartbeat-token your-cmd-token

  With options:
  $ kuma-scout my-command \\\\
      --my-option "value" \\\\
      --my-timeout 60 \\\\
      http://uptimekuma:3001/api/push \\\\
      your-heartbeat-token your-cmd-token

  Using configuration file:
  $ kuma-scout my-command --config /etc/kuma-scout/config.yaml
\"\"\"

@register_command(
    "my-command",
    checker_class=MyChecker,
    config_class=MyConfig,
    help_text="Description of my monitoring command",
)
class MyCommand(CommandExecutor):
    \"\"\"My custom monitoring command.\"\"\"

    def get_builtin_command(self) -> Callable:
        \"\"\"Build and return the Typer command function.\"\"\"

        def my_command(
            uptime_kuma_url: Optional[str] = typer.Argument(None, help="Uptime Kuma API URL (with no token. ex: http://uptimekuma:3001/api/push)"),
            heartbeat_token: Optional[str] = typer.Argument(None, help="Heartbeat token"),
            token: Optional[str] = typer.Argument(None, help="Command-specific token"),
            config: Optional[str] = typer.Option(None, "--config", help="Configuration file path"),
            log_file: Optional[str] = typer.Option(None, "--log-file", help="Log file path"),
            ignore_file_permissions: bool = typer.Option(False, "--ignore-file-permissions"),
            my_option: Optional[str] = typer.Option(None, "--my-option", help="My custom option"),
            my_timeout: Optional[int] = typer.Option(None, "--my-timeout", help="Timeout in seconds"),
        ):
            \"\"\"Description of my monitoring command.

\"\" + MY_EXAMPLES + \"\"\"
            args = {
                "uptime_kuma_url": uptime_kuma_url,
                "heartbeat_token": heartbeat_token,
                "token": token,
                "config": config,
                "log_file": log_file,
                "ignore_file_permissions": ignore_file_permissions,
                "my_option": my_option,
                "my_timeout": my_timeout,
            }
            self.execute_with_orchestration(args)

        return my_command

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        \"\"\"Get fields to display in config summary logging.\"\"\"
        return {
            "📋 My Command Configuration": {
                "Option": "my_option",
                "Timeout": "my_timeout",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
            },
        }
```

### Step 4: Register Tests (tests/commands/test_my_command.py)

```python
from unittest.mock import MagicMock, patch
import pytest
from kuma_scout.cli.commands.my_command import MyCommand
from kuma_scout.core.config.my_config import MyConfig

class TestMyCommand:
    \"\"\"Test my custom command.\"\"\"

    def test_get_builtin_command_returns_callable(self):
        \"\"\"Test command function is callable.\"\"\"
        command = MyCommand()
        command._command_name = "my-command"
        command._config_class = MyConfig
        command._checker_class = MagicMock()
        
        cmd = command.register_command()
        assert callable(cmd)
    
    def test_config_loading(self):
        \"\"\"Test configuration loads correctly.\"\"\"
        config = MyConfig()
        assert config.my_timeout == 30
```

### Step 5: Update CLI Commands Registration

The command is automatically registered via the `@register_command` decorator in `src/kuma_scout/cli/commands/__init__.py`. No additional registration needed!

When you run `kuma-scout --help`, your new command will appear automatically.

### Key Concepts for Typer Commands

**Typer Function Parameters:**
- **Argument**: `typer.Argument()` - Positional parameters (e.g., URL, tokens)
- **Option**: `typer.Option()` - Named parameters with `--flag` syntax
- **Type Hints**: Python's built-in types define parameter types (str, int, bool, Optional[], List[])
- **Defaults**: Set in parameter definition with `= value`

**Typer Features:**
- **Automatic Type Conversion**: Strings to int, bool, enums based on type hints
- **Automatic Help**: Generated from docstrings and parameter help text
- **Tab Completion**: Built-in for bash, zsh, fish via `--install-completion`
- **Rich Output**: Typer uses Rich library for colored, formatted help text
- **Example Integration**: Add examples in docstrings using triple-quoted strings

**Best Practices:**
1. Always include `--config` option for YAML configuration
2. Always include common options: `--log-file`, `--ignore-file-permissions`
3. Use type hints for all parameters
4. Include comprehensive examples in docstrings
5. Handle `None` values for optional parameters
6. Follow naming convention: `--flag-name` (kebab-case) maps to `flag_name` (snake_case)

## Configuration Architecture

### FieldMapping Design

Configuration values are managed through a declarative `FieldMapping` system in `src/kuma_scout/core/config/base.py`:

```python
@dataclass
class FieldMapping:
    """Declarative mapping for a config field across all loading sources."""
    env_var: Optional[str] = None           # Environment variable name
    arg_key: Optional[str] = None           # CLI argument key
    yaml_path: Optional[str] = None         # YAML path (dot-separated: "section.key")
    converter: Callable[[str], Any] = str   # Type converter function
```

### Configuration Loading

Configuration is loaded in priority order:

1. **Defaults** - Set in `ConfigBase.__init__()` and subclass `__init__()` methods
2. **Environment Variables** - Via `load_from_env()` using `env_var` field mapping
3. **YAML File** - Via `load_from_yaml()` using `yaml_path` mapping
4. **CLI Arguments** - Via `load_from_args()` using `arg_key` mapping

Each layer can override values from previous layers through declarative `FieldMapping` definitions.

### YAML Configuration Format

Configuration files use YAML with nested structures:

```yaml
logging:
  log_file: /var/log/kuma-scout.log
  log_level: INFO

heartbeat:
  enabled: true
  interval: 300
  uptime_kuma:
    token: heartbeat-token

my_command:
  my_option: "value"
  my_timeout: 60
```

Lists are natively supported in YAML, eliminating need for comma-separated string parsing.

### Kopia Snapshot Configuration Example

The Kopia snapshot checker demonstrates advanced configuration with **per-path thresholds**:

```yaml
kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token
  # Structured list with path and per-path max_age_hours
  snapshots:
    - path: /data
      max_age_hours: 24          # Critical: must be fresh daily
    - path: /backups
      max_age_hours: 48          # Important: allow 2 days
    - path: /archive
      # Omit max_age_hours to use global default
  # Global default for snapshots without explicit threshold
  max_age_hours: 24
```

**For detailed Kopia snapshot configuration examples and advanced usage, see [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)**

This is loaded via the `FieldMapping` system in [src/kuma_scout/core/config/kopia_snapshot_config.py](src/kuma_scout/core/config/kopia_snapshot_config.py):

```python
"kopiasnapshotstatus_snapshots": FieldMapping(
    yaml_path="kopiasnapshotstatus.snapshots",
),
```

The checker iterates over snapshots and uses each snapshot's `max_age_hours` or falls back to the global default.

## Making Changes

### Adding a New Feature

1. **Implement the feature** in the appropriate module under `src/kuma_scout/`
2. **Write tests** for the feature in `tests/`
3. **Run tests** to ensure nothing breaks: `uv run pytest`
4. **Format code**: `uv run black src/ tests/`
5. **Check linting**: `uv run ruff check --fix src/ tests/`
6. **Check types**: `uv run mypy src/ tests/`
7. **Run all checks**: `hatch run check`

### Updating Version

Edit [pyproject.toml](pyproject.toml) and update the version field in the `[project]` section:

```toml
version = "0.2.0"  # Update this
```

You can also update [src/kuma_scout/__about__.py](src/kuma_scout/__about__.py) for reference in the package.

## Adding a New Command and Checker

### Architecture Overview

Kuma Scout uses a **Command-Driven Registration Pattern** for maximum simplicity and extensibility:

1. **Single decorator on the Command class** - Registers the command, checker, and config all at once
2. **Configuration Class** - Settings management (in `src/kuma_scout/core/config/`)
3. **Checker Class** - Monitoring logic (in `src/kuma_scout/core/checkers/`)
4. **Tests** - Unit tests for all components

**Key benefits:**
- Command explicitly declares its dependencies (checker and config)
- Automatic CLI registration via app.py
- Adding a new command requires zero changes to core files

### Step-by-Step: Adding a New Command

#### 1. Create the Configuration Class

Create `src/kuma_scout/core/config/mycheck_config.py`:

```python
"""MyCheck command configuration."""

from typing import Dict

from .base import ConfigBase, FieldMapping


class MyCheckConfig(ConfigBase):
    """Configuration for mycheck command."""

    def __init__(self):
        """Initialize mycheck configuration with defaults."""
        super().__init__()

        # MyCheck-specific attributes
        self.mycheck_enabled = True
        self.mycheck_timeout = 300

    def _get_field_mappings(self) -> Dict[str, FieldMapping]:
        """Get field mappings for mycheck configuration."""
        mappings = super()._get_field_mappings()
        mappings.update({
            "mycheck_enabled": FieldMapping(
                yaml_path="mycheck.enabled",
                arg_key="enabled",
                converter=self._parse_bool,
            ),
            "mycheck_timeout": FieldMapping(
                yaml_path="mycheck.timeout",
                arg_key="timeout",
                converter=int,
            ),
            "command_token": FieldMapping(
                env_var="KUMA_SCOUT_MYCHECK_TOKEN",
                arg_key="mycheck_token",
                yaml_path="mycheck.uptime_kuma.token",
            ),
        })
        return mappings

    def validate(self):
        """Validate mycheck configuration."""
        super().validate()
        errors = []
        
        if self.mycheck_timeout <= 0:
            errors.append("mycheck_timeout must be positive")
        
        if errors:
            raise ValueError(
                "Configuration validation failed:\n  " + "\n  ".join(errors)
            )

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get mycheck configuration summary for logging."""
        return {
            "log_file": self.log_file,
            "mycheck_enabled": self.mycheck_enabled,
            "mycheck_timeout": f"{self.mycheck_timeout}s",
            "uptime_kuma_url": self.uptime_kuma_url,
            "heartbeat_enabled": self.heartbeat_enabled,
            "heartbeat_interval": f"{self.heartbeat_interval}s",
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "mycheck_token": self._mask_token(self.command_token, mask_tokens),
        }
```

#### 2. Create the Checker Class

Create `src/kuma_scout/core/checkers/mycheck_checker.py`:

```python
"""MyCheck monitoring implementation."""

from logging import Logger

from kuma_scout.core.config.mycheck_config import MyCheckConfig
from kuma_scout.core.models import CheckResult

from .base import Checker


class MyCheckChecker(Checker):
    """Checker for monitoring custom conditions."""

    name = "mycheck"
    description = "Monitor custom condition or service"

    def __init__(self, logger: Logger, config):
        """Initialize mycheck checker."""
        super().__init__(logger, config)
        self.config: MyCheckConfig = config

    def execute(self) -> CheckResult:
        """Execute the mycheck check.
        
        Returns:
            CheckResult with status and message
        """
        try:
            # Implement your monitoring logic here
            condition_met = self._check_condition()
            
            if condition_met:
                return CheckResult(
                    is_success=True,
                    duration_seconds=0,
                    message="Check passed",
                )
            else:
                return CheckResult(
                    is_success=False,
                    duration_seconds=0,
                    message="Check failed",
                )
        except Exception as e:
            self.logger.error(f"MyCheck error: {e}")
            return CheckResult(
                is_success=False,
                duration_seconds=0,
                message=f"Error: {e}",
            )

    def _check_condition(self) -> bool:
        """Implement your custom check logic here."""
        # Example: check if a service is running, file exists, etc.
        return True
```

#### 3. Create the Command Class (with Typer)

Create `src/kuma_scout/cli/commands/mycheck.py`:

```python
"""MyCheck monitoring command."""

from typing import Callable, Dict, Optional

import typer

from kuma_scout.cli.commands import register_command
from kuma_scout.cli.commands.executor import CommandExecutor
from kuma_scout.core.checkers.mycheck_checker import MyCheckChecker
from kuma_scout.core.config.mycheck_config import MyCheckConfig

MYCHECK_EXAMPLES = """
Examples:

  Basic usage:
  $ kuma-scout mycheck \\
      http://uptimekuma:3001/api/push \\
      your-heartbeat-token your-mycheck-token

  With custom timeout:
  $ kuma-scout mycheck \\
      --timeout 60 \\
      http://uptimekuma:3001/api/push \\
      your-heartbeat-token your-mycheck-token

  Using configuration file:
  $ kuma-scout mycheck --config /etc/kuma-scout/config.yaml
"""

@register_command(
    "mycheck",
    checker_class=MyCheckChecker,
    config_class=MyCheckConfig,
    help_text="Run mycheck monitoring",
)
class MyCheckCommand(CommandExecutor):
    """CLI command for mycheck monitoring using unified executor."""

    def get_builtin_command(self) -> Callable:
        """Build and return mycheck command function with Typer parameters."""

        def mycheck_cmd(
            uptime_kuma_url: Optional[str] = typer.Argument(None, help="Uptime Kuma API URL (with no token. ex: http://uptimekuma:3001/api/push)"),
            heartbeat_token: Optional[str] = typer.Argument(None, help="Heartbeat token"),
            token: Optional[str] = typer.Argument(None, help="Command-specific token"),
            config: Optional[str] = typer.Option(None, "--config", help="Configuration file path"),
            log_file: Optional[str] = typer.Option(None, "--log-file", help="Log file path"),
            ignore_file_permissions: bool = typer.Option(False, "--ignore-file-permissions", help="Skip config file permission validation"),
            timeout: Optional[int] = typer.Option(None, "--timeout", help="Check timeout in seconds"),
        ):
            """Run mycheck monitoring.

""" + MYCHECK_EXAMPLES + """
            args = {
                "uptime_kuma_url": uptime_kuma_url,
                "heartbeat_token": heartbeat_token,
                "token": token,
                "config": config,
                "log_file": log_file,
                "ignore_file_permissions": ignore_file_permissions,
                "timeout": timeout,
            }
            self.execute_with_orchestration(args)

        return mycheck_cmd

    def get_summary_fields(self) -> Dict[str, Dict[str, str]]:
        """Get fields to display in config summary logging."""
        return {
            "🔧 MyCheck Configuration": {
                "Timeout": "mycheck_timeout",
            },
            "🔔 Uptime Kuma Integration": {
                "URL": "uptime_kuma_url",
                "Heartbeat Enabled": "heartbeat_enabled",
            },
        }
```

**Note:** The `@register_command("mycheck", ...)` decorator automatically:
- Stores `MyCheckChecker` as `_checker_class` on the command class
- Stores `MyCheckConfig` as `_config_class` on the command class
- Registers the command in `_COMMAND_REGISTRY` for auto-discovery

**That's it!** No manual registry modifications needed—the decorator handles everything.

#### 4. Register Your Command (CRITICAL STEP!)

The `@register_command()` decorator handles registration, but you **MUST import** your command class in `src/kuma_scout/cli/commands/__init__.py` for the decorator to execute and register the command.

Update `src/kuma_scout/cli/commands/__init__.py` and add your import in the imports section:

```python
# Imports trigger registration via the decorator
from kuma_scout.cli.commands.cmdcheck import CmdCheckCommand  # noqa: E402
from kuma_scout.cli.commands.kopiasnapshotstatus import (  # noqa: E402
    KopiaSnapshotStatusCommand,
)  # noqa: E402
from kuma_scout.cli.commands.portscan import PortscanCommand  # noqa: E402
from kuma_scout.cli.commands.mycheck import MyCheckCommand  # noqa: E402  # ADD THIS LINE
from kuma_scout.cli.commands.zfspoolstatus import ZfsPoolStatusCommand  # noqa: E402

__all__ = [
    "CmdCheckCommand",
    "PortscanCommand",
    "KopiaSnapshotStatusCommand",
    "ZfsPoolStatusCommand",
    "MyCheckCommand",  # ADD THIS
    "register_command",
    "_COMMAND_REGISTRY",
]
```

**Why this is required:**
- The `@register_command()` decorator executes when the class is imported
- Without the import, the decorator never runs and the command won't be registered
- `app.py` discovers commands by reading `_COMMAND_REGISTRY` which is populated by the decorator
- Once imported, `app.py` automatically registers it with Typer

**How it works:**
1. Your command file imports `@register_command` and decorates the class
2. `__init__.py` imports your command class
3. The decorator executes and adds the class to `_COMMAND_REGISTRY`
4. `app.py` reads the registry and calls `app.command()` for each one
5. Your command is instantly available: `kuma-scout mycheck --help`

#### 5. Create Tests

Create `tests/checkers/test_mycheck_checker.py`:

```python
"""Tests for MyCheckChecker."""

import pytest
from unittest.mock import MagicMock

from kuma_scout.core.checkers.mycheck_checker import MyCheckChecker
from kuma_scout.core.config.mycheck_config import MyCheckConfig


def test_mycheck_execute_success():
    """Test successful mycheck execution."""
    logger = MagicMock()
    config = MyCheckConfig()
    config.uptime_kuma_url = "http://example.com"
    config.mycheck_enabled = True
    
    checker = MyCheckChecker(logger, config)
    result = checker.execute()
    
    assert result.is_success is True
    assert "Check passed" in result.message


def test_mycheck_config_validation():
    """Test mycheck config validation."""
    config = MyCheckConfig()
    config.uptime_kuma_url = "http://example.com"
    config.mycheck_timeout = -1  # Invalid
    
    with pytest.raises(ValueError):
        config.validate()
```

### Testing Your New Command

```bash
# Run all tests
uv run pytest

# Run tests for your specific command
uv run pytest tests/checkers/test_mycheck_checker.py -v

# Run with coverage
uv run pytest --cov=src/kuma_scout

# Check types
uv run mypy src/ tests/

# Run full quality checks
hatch run check

# Try the new command
kuma-scout mycheck --help
```

### Configuration File Example

Add to `example.config.yaml`:

```yaml
mycheck:
  enabled: true
  timeout: 300
  uptime_kuma:
    token: your-mycheck-token
```

### Authentication Token Example

```bash
export KUMA_SCOUT_MYCHECK_TOKEN=your-token
```

**Note:** Only authentication tokens (suffixed with `_TOKEN`) are supported via environment variables. All other configuration must use YAML files or CLI arguments.

### What Happens Automatically

1. **Registry Pattern** - Your `@register_*` decorators add components to their respective registries
2. **No Factory Method Changes** - Configs, checkers, and commands are discovered from registries
3. **CLI Auto-Discovery** - `app.py` automatically registers all commands from the registry
4. **Extensibility** - New features are added without touching core files

### Documentation

Don't forget to update:
- **README.md** - Add usage examples for the new command
- **DEVELOPMENT.md** - Document new checkers or commands if they're complex
- **Docstrings** - Add comprehensive docstrings to all classes and methods


## Troubleshooting

### Import Errors

If you get import errors like `ModuleNotFoundError: No module named 'kuma_scout'`:

```bash
# Ensure package is installed in development mode
uv sync
```

### Tests Not Found

If pytest can't find tests:

```bash
# Make sure you're in the project root
cd /code/projects/kuma-scout

# Run pytest
uv run pytest
```

### Linting Errors

Before committing, always run:

```bash
uv run ruff check --fix src/ tests/
uv run black src/ tests/
uv run pytest
```

## Useful Commands Reference

```bash
# Development install
uv sync --all-extras

# Run tests with coverage
uv run pytest --cov=src/kuma_scout --cov-report=html

# Format code
uv run black src/ tests/

# Lint code
uv run ruff check src/ tests/

# Fix linting issues
uv run ruff check --fix src/ tests/

# Type check code (checks untyped function bodies)
uv run mypy src/ tests/

# Run all quality checks
hatch run check

# Build package
uv build

# Build wheel only
uv build --wheel
```