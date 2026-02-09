# Development Guide

## Quick Start

### Setup

```bash
# Install dependencies
uv sync --all-extras

# Verify installation
kuma-scout --version
kuma-scout cmdcheck --help
```

## Development Commands

```bash
# Run tests
hatch run test

# Run with coverage
hatch run test --cov=src/kuma_scout

# Format code
hatch run format

# Lint and fix issues
hatch run lint --fix

# Type check
hatch run check  # Runs lint, format, and mypy

# Build package
uv build
```

## Project Structure

```
kuma-scout/
├── src/kuma_scout/
│   ├── cli/                  # CLI auto-generation from Pydantic
│   ├── core/                 # Core functionality (config, API, logging)
│   ├── plugins/              # Monitoring plugins (auto-discovered)
│   └── __init__.py
├── tests/                    # Test suite (mirrors src/)
├── doc/                      # Documentation
├── example.config.yaml       # Configuration template
└── pyproject.toml            # Project configuration
```

## Creating a New Plugin

Plugins are simple, self-contained monitoring components. Each plugin defines configuration via Pydantic and execution logic.

### Step 1: Create Plugin File

Create `src/kuma_scout/plugins/my_check.py`:

```python
"""My custom monitoring plugin."""
from pydantic import Field
from kuma_scout.core.models import CheckResult
from kuma_scout.plugins.base import CheckConfig, Plugin


class MyCheckConfig(CheckConfig):
    """Configuration for my custom check."""
    
    target: str = Field(description="Target to monitor")
    timeout: int = Field(default=30, ge=1, le=3600, description="Timeout in seconds")


class MyCheckPlugin(Plugin):
    """Custom monitoring plugin."""
    
    name = "my_check"
    description = "Monitor custom target"
    config_class = MyCheckConfig

    def execute(self, config: CheckConfig) -> CheckResult:
        """Execute the check."""
        cfg = config  # type: ignore
        try:
            # Your monitoring logic here
            is_up = self._check_target(cfg.target)
            
            return CheckResult(
                status="up" if is_up else "down",
                message="Check passed" if is_up else "Check failed",
                duration_seconds=1.0,
            )
        except Exception as e:
            return CheckResult(
                status="down",
                message=f"Error: {str(e)}",
                duration_seconds=1.0,
            )

    def _check_target(self, target: str) -> bool:
        """Your check logic here."""
        return True
```

### Step 2: Add Tests

Create `tests/plugins/test_my_check.py`:

```python
"""Tests for my_check plugin."""
from kuma_scout.plugins.my_check import MyCheckPlugin, MyCheckConfig


def test_plugin_attributes():
    """Test plugin has required attributes."""
    assert MyCheckPlugin.name == "my_check"
    assert MyCheckPlugin.config_class == MyCheckConfig


def test_execute_success():
    """Test successful execution."""
    plugin = MyCheckPlugin()
    config = MyCheckConfig(name="test", target="example.com")
    result = plugin.execute(config)
    
    assert result.status == "up"
    assert "passed" in result.message
```

### Step 3: Update Configuration Example

Add to `example.config.yaml`:

```yaml
checks:
  - name: my-custom-check
    type: my_check
    target: example.com
    timeout: 30
    tags: [custom]
```

### Step 4: Document It

- Add examples to `README.md`
- Add configuration details to `doc/CONFIGURATION_GUIDE.md`

## Before You Submit a Pull Request

1. **Write tests** - Cover happy path and error cases
2. **Run tests** - Ensure all tests pass:
   ```bash
   hatch run test
   ```
3. **Format code**:
   ```bash
   hatch run format
   hatch run lint --fix
   ```
4. **Check types**:
   ```bash
   uv run mypy src/ tests/
   ```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with tests
4. Ensure all tests pass and code is formatted
5. Push to your fork
6. Open a pull request with clear description

## Plugin Best Practices

- **Single Responsibility** - Each plugin monitors one thing
- **Clear Configuration** - Use descriptive field names and help text
- **Error Handling** - Always catch exceptions and return appropriate status
- **Logging** - Use `self.output_handler` for debug/info messages (echo=False for internal logs)
- **Sanitization** - Use `DataSanitizer` for output sent to Uptime Kuma
- **Testing** - Comprehensive unit tests with good coverage
- **Documentation** - Document purpose, configuration, and examples

## Configuration Reference

### Plugin Configuration (Pydantic)

```python
class MyCheckConfig(CheckConfig):
    """Configuration for my check."""
    
    # Required field
    target: str = Field(description="Target to check")
    
    # Optional with default
    timeout: int = Field(default=30, ge=1, le=3600)
    
    # Enum field
    mode: Literal["fast", "thorough"] = Field(default="fast")
```

### YAML Configuration Format

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}

checks:
  - name: my-check
    type: my_check
    target: example.com
    timeout: 60
    mode: thorough
    token: ${MY_CHECK_TOKEN}  # Override global token
```

## Architecture

**CLI Layer** - Auto-generated from Pydantic models. No manual CLI code needed.

**Core Layer** - Shared: config loading, API integration, logging, sanitization.

**Plugin Layer** - Self-contained monitoring logic. Plugins auto-discover on startup.

When you create a plugin:
- Define config via Pydantic (validation + CLI args)
- Implement `execute()` method
- Return `CheckResult` with status and message
- Done! CLI and config loading work automatically

## Troubleshooting

**Plugin not discovered?**
- Ensure file is in `src/kuma_scout/plugins/`
- Restart application (imports are cached)
- Check for import errors: `python -c "from kuma_scout.plugins.my_check import MyCheckPlugin"`

**Tests failing?**
```bash
hatch run test -v  # Verbose output
hatch run test tests/plugins/test_my_check.py  # Run single file
```

**Type errors?**
```bash
uv run mypy src/ tests/ --show-error-codes
```

**Linting issues?**
```bash
hatch run lint --fix  # Auto-fix most issues
```