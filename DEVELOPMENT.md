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
- All development dependencies (pytest, pytest-cov, black, ruff)

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
│   ├── __about__.py           # Version info
│   ├── __init__.py            # Package exports
│   ├── cli/
│   │   ├── __init__.py
│   │   └── app.py             # Click CLI application
│   └── core/
│       ├── __init__.py
│       ├── config.py          # Configuration management
│       ├── logger.py          # Logging setup
│       ├── scanner.py         # Nmap execution and parsing
│       └── uptime_kuma.py     # Uptime Kuma API integration
├── tests/
│   ├── __init__.py
│   ├── test_cli.py            # CLI tests
│   ├── test_config.py         # Configuration tests
│   └── test_scanner.py        # Scanner/parsing tests
├── pyproject.toml             # Project configuration (Hatch, pytest, ruff, black)
├── README.md                  # Main documentation
├── LICENSE                    # MIT License
├── MANIFEST.in                # Distribution manifest
├── example.config.ini         # Example configuration file
└── .gitignore                 # Git ignore rules
```

## Key Configuration Files

### pyproject.toml

Main project configuration with:
- **[project]**: Package metadata, dependencies
- **[tool.black]**: Black formatter settings
- **[tool.ruff]**: Ruff linter configuration
- **[tool.pytest.ini_options]**: pytest configuration

### Entry Point

The CLI entry point is defined in `pyproject.toml`:

```
[project.scripts]
kuma-sentinel = "kuma_sentinel.cli.app:cli"
```

This creates the `kuma-sentinel` command that calls the `cli()` function in `app.py`.

## Making Changes

### Adding a New Feature

1. **Implement the feature** in the appropriate module under `src/kuma_sentinel/`
2. **Write tests** for the feature in `tests/`
3. **Run tests** to ensure nothing breaks: `pytest`
4. **Format code**: `black src/ tests/`
5. **Check linting**: `ruff check --fix src/ tests/`

### Updating Version

Edit [pyproject.toml](pyproject.toml) and update the version field in the `[project]` section:

```toml
version = "0.2.0"  # Update this
```

You can also update [src/kuma_sentinel/__about__.py](src/kuma_sentinel/__about__.py) for reference in the package.

## Publishing to PyPI

### 1. Build the Distribution

```bash
uv build
```

### 2. Upload to Test PyPI (Optional, recommended first)

```bash
uv pip install twine
twine upload --repository testpypi dist/*
```

### 3. Upload to PyPI

```bash
twine upload dist/*
```

### 4. Install from PyPI

```bash
pip install kuma-sentinel
```

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

## IDE Configuration

### VS Code Settings

Add to `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  }
}
```

### PyCharm/IntelliJ

1. Go to Settings → Editor → Code Style → Python
2. Set line length to 88
3. Enable Black formatter integration

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

# Build package
uv build

# Build wheel only
uv build --wheel
```

## Dependencies

### Core
- `click>=8.0.0` - CLI framework

### Development (optional)
- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `black>=23.0.0` - Code formatter
- `ruff>=0.1.0` - Linter

### System
- `nmap` - Network mapper (must be installed separately)
