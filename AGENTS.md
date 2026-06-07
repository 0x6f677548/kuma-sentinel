# Kuma-Scout — Agent Instructions

Python 3.10+ CLI monitoring agent for Uptime Kuma. Plugin-based, with auto-generated Typer CLI from Pydantic models.

## Dev commands

```bash
uv sync --all-extras          # setup
hatch run test                # pytest + coverage (htmlcov/)
hatch run lint --fix          # ruff auto-fix
hatch run format              # ruff format
hatch run typecheck           # mypy
hatch run check               # lint-check + format-check + test + typecheck
hatch run lint-check          # ruff check (no fix)
hatch run format-check        # ruff format --check
```

CI runs `ruff check .`, `ruff format --check`, `mypy` (lint.yml) and `pytest` (test.yml) independently. Both use `uv sync --frozen --no-dev` with only relevant dep groups.

## Project map

| Path | Purpose |
|---|---|
| `src/kuma_scout/cli/` | Typer CLI app, auto-generator, config merger |
| `src/kuma_scout/core/` | Config loading, models, logging, heartbeat, uptime_kuma push, SSH runner, sanitizer |
| `src/kuma_scout/plugins/` | Single-file plugins: `base.py` (abstract + `@execute_with_timing` decorator), cmdcheck, portscan, kopia_snapshot, zfs_pool |
| `tests/` | Mirrors src/ structure |
| `doc/` | Configuration guide, migration guide, development guide |

Entrypoint: `kuma_scout.cli.app:cli` → registered as `kuma-scout` console script.

## Plugin system

- Plugins auto-discovered at runtime via `discover_plugins()` in `plugins/__init__.py` (cached with `@lru_cache`)
- Each plugin file defines a config class (extends `CheckConfig`) and a plugin class (extends `Plugin`)
- `name`, `description`, `config_class` class attributes required
- `execute()` method decorated with `@execute_with_timing` (auto config casting, timing, error handling)
- `execute_with_heartbeat()` wraps execution with heartbeat start/stop and retry logic
- All results use `CheckResult` dataclass (status: "up"|"down")

## Conventions

- No relative imports ever. All imports at module level; avoid import cycles instead of inline imports.
- No `# type: ignore` patches — fix the underlying issue.
- Use `DataSanitizer` for any output sent to Uptime Kuma via `send_push()`.
- Config priority: CLI args > YAML config > defaults. `${VAR}` expansion supported everywhere.
- Global + per-check URL/token merging logic lives in `ConfigMerger` (`cli/config_merger.py`).
- Execution context (`core/execution_context.py`) auto-enriches logs with `[plugin_type:check_name]` prefix.
- Never use `test.config.yaml` in tests. Use `tmp_path` pytest fixture or `example.config.yaml`.

## Testing

- `pytest` with coverage: `--cov=src/kuma_scout --cov-report=html --cov-report=term-missing`
- Single file: `hatch run test tests/plugins/test_cmdcheck.py`
- Keep coverage ≥ 80% (aim for 90%+).
- Ruff rules: E, W, F, I, C, B, UP (B008 ignored — allows `typer.Option` defaults).
- Line length: 88, quote style: double.

## Documentation policy

- Update `example.config.yaml` and `doc/CONFIGURATION_GUIDE.md` for config changes.
- Update `doc/DEVELOPMENT.md` for plugin architecture or dev workflow changes.
- Update `doc/MIGRATION.md` for breaking changes vs last release.
- Update `README.md` for macro changes only.

## Build & release

```bash
uv build                    # builds sdist + wheel
uv sync --frozen            # CI-style sync
```

Docker: multi-stage build with `uv` export, non-root `appuser` (UID/GID args), nmap installed.

Release flow: `create-draft-release.yml` creates branch `release/vX.Y.Z` and a draft GitHub release. On publish, `pypi.yml` and `ghcr.yml` deploy to PyPI and GHCR (linux/amd64 + linux/arm64).

## Known gaps (don't assume fixed)

- `send_push()` lacks retry on network failure
- Retry logic in `base.py` uses fixed delay, not exponential backoff
- Heartbeat has no jitter or checkpoint-signal method
- CLI generator class (`cli/generator.py`, ~1350 lines) is a large monolith
- No explicit plugin registry pattern (uses dynamic `issubclass` discovery)
