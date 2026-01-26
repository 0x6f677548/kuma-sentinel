# Development Guide

## Quick Start

### 1. Clone and Setup

```bash
cd /code/projects/kuma-sentinel
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
kuma-sentinel --version
kuma-sentinel portscan --help
```

## Development Commands

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/kuma_sentinel

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
# - dist/kuma_sentinel-0.1.0-py3-none-any.whl
# - dist/kuma_sentinel-0.1.0.tar.gz
```

## Project Structure

```
kuma-sentinel/
├── src/kuma_sentinel/
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

**src/kuma_sentinel/cli/** - Click CLI commands
- Each command implements the `Command` interface
- Registers CLI options and calls `CommandExecutor`

**src/kuma_sentinel/core/config/** - Configuration management
- `base.py` - `ConfigBase` abstract class and `FieldMapping` declarative system
- Command-specific configs (e.g., `portscan_config.py`, `kopia_snapshot_config.py`)

**src/kuma_sentinel/core/checkers/** - Monitoring implementations
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
kuma-sentinel = "kuma_sentinel.cli.app:cli"
```

This creates the `kuma-sentinel` command that calls the `cli()` function in `app.py`.

## Configuration Architecture

### FieldMapping Design

Configuration values are managed through a declarative `FieldMapping` system in `src/kuma_sentinel/core/config/base.py`:

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
  log_file: /var/log/kuma-sentinel.log
  log_level: INFO

heartbeat:
  enabled: true
  interval: 300
  uptime_kuma:
    token: heartbeat-token

portscan:
  ports: 1-1000
  ip_ranges:
    - 192.168.1.0/24
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

This is loaded via the `FieldMapping` system in [src/kuma_sentinel/core/config/kopia_snapshot_config.py](src/kuma_sentinel/core/config/kopia_snapshot_config.py):

```python
"kopiasnapshotstatus_snapshots": FieldMapping(
    yaml_path="kopiasnapshotstatus.snapshots",
),
```

The checker iterates over snapshots and uses each snapshot's `max_age_hours` or falls back to the global default.

## Making Changes

### Adding a New Feature

1. **Implement the feature** in the appropriate module under `src/kuma_sentinel/`
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

You can also update [src/kuma_sentinel/__about__.py](src/kuma_sentinel/__about__.py) for reference in the package.

## Adding a New Command and Checker

### Architecture Overview

Kuma Sentinel uses a **Command-Driven Registration Pattern** for maximum simplicity and extensibility:

1. **Single decorator on the Command class** - Registers the command, checker, and config all at once
2. **Configuration Class** - Settings management (in `src/kuma_sentinel/core/config/`)
3. **Checker Class** - Monitoring logic (in `src/kuma_sentinel/core/checkers/`)
4. **Tests** - Unit tests for all components

**Key benefits:**
- Command explicitly declares its dependencies (checker and config)
- Automatic CLI registration via app.py
- Adding a new command requires zero changes to core files

### Step-by-Step: Adding a New Command

#### 1. Create the Configuration Class

Create `src/kuma_sentinel/core/config/mycheck_config.py`:

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
                env_var="KUMA_SENTINEL_MYCHECK_TOKEN",
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

Create `src/kuma_sentinel/core/checkers/mycheck_checker.py`:

```python
"""MyCheck monitoring implementation."""

from logging import Logger

from kuma_sentinel.core.config.mycheck_config import MyCheckConfig
from kuma_sentinel.core.models import CheckResult

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

#### 3. Create the Command Class

Create `src/kuma_sentinel/cli/commands/mycheck.py`:

```python
"""MyCheck monitoring command."""

from kuma_sentinel.cli.commands.executor import CommandExecutor
from kuma_sentinel.cli.commands import register_command
from kuma_sentinel.core.checkers.mycheck_checker import MyCheckChecker
from kuma_sentinel.core.config.mycheck_config import MyCheckConfig


@register_command(
    "mycheck",
    checker_class=MyCheckChecker,
    config_class=MyCheckConfig,
    help_text="Run mycheck monitoring",
)
class MyCheckCommand(CommandExecutor):
    """CLI command for mycheck monitoring using unified executor."""

    def get_builtin_command(
        self, base_command: click.Command
    ) -> click.Command:
        """Build mycheck command with arguments and options."""
        # Add arguments
        base_command = click.argument("uptime_kuma_url", required=False)(base_command)
        base_command = click.argument("mycheck_token", required=False)(base_command)

        # Add options
        base_command = click.option(
            "--config",
            type=click.Path(exists=True),
            help="YAML configuration file",
        )(base_command)

        base_command = click.option(
            "--timeout",
            type=int,
            help="Check timeout in seconds",
        )(base_command)

        return base_command

    def load_from_args(self, args: Dict) -> None:
        """Load command-specific arguments into config."""
        if args.get("timeout"):
            self.config.mycheck_timeout = args["timeout"]

    def get_summary_fields(self) -> Dict:
        """Get fields for config summary logging."""
        return {
            "mycheck_timeout": f"{self.config.mycheck_timeout}s",
        }
```

**Note:** The `@register_command("mycheck", ...)` decorator automatically:
- Stores `MyCheckChecker` as `_checker_class` on the command class
- Stores `MyCheckConfig` as `_config_class` on the command class
- Registers the command in `_COMMAND_REGISTRY` for auto-discovery

**That's it!** No manual registry modifications needed—the decorator handles everything.

#### 4. Import Your Command Class (REQUIRED for Registration)

The import below is **required** because it triggers the `@register_command()` decorator when the command class is imported.

Update `src/kuma_sentinel/cli/commands/__init__.py`:

```python
# Imports trigger registration via the decorator
from kuma_sentinel.cli.commands.portscan import PortscanCommand  # noqa: E402
from kuma_sentinel.cli.commands.kopiasnapshotstatus import KopiaSnapshotStatusCommand  # noqa: E402
from kuma_sentinel.cli.commands.mycheck import MyCheckCommand  # noqa: E402  # Add this
```

Once this import is added, the `app.py` auto-discovery will automatically find your command!

#### 5. Create Tests

Create `tests/checkers/test_mycheck_checker.py`:

```python
"""Tests for MyCheckChecker."""

import pytest
from unittest.mock import MagicMock

from kuma_sentinel.core.checkers.mycheck_checker import MyCheckChecker
from kuma_sentinel.core.config.mycheck_config import MyCheckConfig


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
uv run pytest --cov=src/kuma_sentinel

# Check types
uv run mypy src/ tests/

# Run full quality checks
hatch run check

# Try the new command
kuma-sentinel mycheck --help
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
export KUMA_SENTINEL_MYCHECK_TOKEN=your-token
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

If you get import errors like `ModuleNotFoundError: No module named 'kuma_sentinel'`:

```bash
# Ensure package is installed in development mode
uv sync
```

### Tests Not Found

If pytest can't find tests:

```bash
# Make sure you're in the project root
cd /code/projects/kuma-sentinel

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
uv run pytest --cov=src/kuma_sentinel --cov-report=html

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