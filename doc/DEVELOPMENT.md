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

Plugins are simple, self-contained monitoring components. Each plugin defines configuration via Pydantic and execution logic. The plugin system uses a decorator-based architecture that automatically handles timing, error handling, and config casting.

### Step 1: Create Plugin File

Create `src/kuma_scout/plugins/my_check.py`:

```python
"""My custom monitoring plugin."""
from pydantic import Field
from kuma_scout.core.models import CheckResult
from kuma_scout.plugins.base import CheckConfig, Plugin, execute_with_timing


class MyCheckConfig(CheckConfig):
    """Configuration for my custom check."""

    target: str = Field(description="Target to monitor")
    timeout: int = Field(default=30, ge=1, le=3600, description="Timeout in seconds")


class MyCheckPlugin(Plugin):
    """Custom monitoring plugin."""

    name = "my_check"
    description = "Monitor custom target"
    config_class = MyCheckConfig

    @execute_with_timing
    def execute(self, config: MyCheckConfig) -> CheckResult:
        """Execute the check."""
        # Config is automatically cast to MyCheckConfig by the decorator
        # Timing and error handling are handled automatically

        # Your monitoring logic here
        is_up = self._check_target(config.target)

        return CheckResult(
            check_name=config.name,
            status="up" if is_up else "down",
            message="Check passed" if is_up else "Check failed",
        )

    def _check_target(self, target: str) -> bool:
        """Your check logic here."""
        return True
```

### Key Changes in Plugin Architecture

The `@execute_with_timing` decorator provides:

- **Automatic config casting**: No need for manual type casting
- **Built-in timing**: Execution time is measured automatically
- **Standardized error handling**: Exceptions are caught and converted to proper CheckResult objects
- **Structured error context**: All logs and errors are automatically enriched with check name, plugin type, and execution context
- **Consistent behavior**: All plugins have identical error handling and timing

### Execution Context System

All check executions run within an **execution context** that automatically enriches logs and error messages with contextual information. This provides structured logging throughout the entire check execution chain.

**Automatic Log Enrichment:**
```python
# Logs automatically include context when available
self.output_handler.info("Check starting")  # → "[cmdcheck:my-check] Check starting"
self.output_handler.error("Command failed")  # → "[cmdcheck:my-check] Command failed"
```

**Context-Aware Error Details:**
When errors occur, CheckResult details automatically include:
- `timeout_seconds`: The configured timeout value
- `elapsed_seconds`: How long the check ran before failing
- `error`: Sanitized error message
- `error_type`: The exception type that occurred

**Context is automatically managed** - no changes needed in plugin code. The execution context is set at the start of check execution and cleared when complete.

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
    assert result.duration_seconds > 0  # Timing is handled by decorator


def test_execute_error():
    """Test error handling."""
    plugin = MyCheckPlugin()
    config = MyCheckConfig(name="test", target="example.com")

    # Mock an error in the check logic
    original_check = plugin._check_target
    plugin._check_target = lambda x: (_ for _ in ()).throw(RuntimeError("Test error"))

    result = plugin.execute(config)

    assert result.status == "down"
    assert "Check execution failed" in result.message
    assert result.duration_seconds > 0
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
- **Error Handling** - The `@execute_with_timing` decorator handles exceptions automatically
- **Structured Logging** - Use `self.output_handler` for debug/info messages; logs are automatically enriched with execution context (check name, plugin type)
- **Sanitization** - Use `DataSanitizer` for output sent to Uptime Kuma
- **Testing** - Comprehensive unit tests with good coverage, including error cases
- **Documentation** - Document purpose, configuration, and examples
- **Decorator Usage** - Always use `@execute_with_timing` on your `execute()` method

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

**Core Layer** - Shared: config loading, API integration, logging, sanitization, execution context management.

**Plugin Layer** - Self-contained monitoring logic with automatic timing, error handling, and structured logging via `@execute_with_timing` decorator. Plugins auto-discover on startup and run within execution contexts that provide automatic log enrichment.

### Execution Context System

The execution context system provides automatic enrichment of logs and error messages throughout check execution:

- **Context Variables**: Uses Python's `contextvars` for thread-safe, transparent state management
- **Automatic Enrichment**: All logs include `[plugin_type:check_name]` prefix when context is available
- **Error Context**: Failed checks include timeout, elapsed time, and error details in CheckResult
- **No Code Changes**: Context is set automatically at check execution start and cleared on completion

When you create a plugin:
- Define config via Pydantic (validation + CLI args)
- Implement `execute()` method with `@execute_with_timing` decorator
- Return `CheckResult` with status and message (timing, errors, and context handled automatically)
- Done! CLI, config loading, and structured logging work automatically

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