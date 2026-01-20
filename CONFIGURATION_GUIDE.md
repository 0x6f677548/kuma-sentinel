# Per-Path max_age_hours Configuration Guide

## Quick Start

### Configuration File (YAML)
```yaml
kopiasnapshotstatus:
  targets:
    snapshots:
      - path: /data
        max_age_hours: 24
      - path: /backups
        max_age_hours: 48
      - path: root@fileserver:/mnt/shares
        # Omits max_age_hours → uses global default
    max_age_hours: 24
```

### Command Line
```bash
# Override with CLI
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48
```

## Key Features

✅ **Per-path thresholds** — Each snapshot can have different age requirements
✅ **Global fallback** — Paths without explicit threshold use global default
✅ **SSH support** — Handles remote paths like `user@host:/path`
✅ **CLI override** — CLI `--snapshot` flags replace YAML config entirely
✅ **Type-safe** — Structured YAML format prevents configuration errors

## Configuration Reference

### Structure
```
kopiasnapshotstatus:
  targets:
    snapshots:          # List of snapshot configurations
      - path: <string>  # Required: snapshot path (local or remote)
        max_age_hours: <int>  # Optional: max age hours (falls back to global default)
    max_age_hours: <int> # Global default (default: 24)
```

### Examples

**Local paths with different thresholds:**
```yaml
snapshots:
  - path: /data
    max_age_hours: 24
  - path: /var/backups
    max_age_hours: 48
  - path: /archive
    max_age_hours: 168  # Weekly
```

**Mixed local and remote paths:**
```yaml
snapshots:
  - path: /local/backup
    max_age_hours: 24
  - path: backup.example.com:/remote/snapshots
    max_age_hours: 48
  - path: root@nas:/volume1/backup
    max_age_hours: 72
```

**Using global default:**
```yaml
snapshots:
  - path: /data
  - path: /backups
  - path: /archive
max_age_hours: 24  # All use 24h
```

## CLI Usage

### Single snapshot
```bash
kuma-sentinel kopiasnapshotstatus --snapshot /data 24
```

### Multiple snapshots
```bash
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  --snapshot "user@host:/path" 72
```

### Override config file
```bash
kuma-sentinel kopiasnapshotstatus \
  --config /etc/kuma-sentinel/config.yaml \
  --snapshot /critical 12 \
  --snapshot /archive 240
```

## Alert Messages

### Fresh snapshots
```
✅ All snapshots fresh: /data: 5.0h; /backups: 12.0h
```

### Stale snapshot
```
⚠️ Snapshots too old: /data: 30.0h > 24h; /backups: 50.0h > 48h
```

### Per-path details in result
```json
{
  "old_snapshots": [
    {
      "path": "/backups",
      "age_hours": 50.0,
      "max_age_hours": 48,
      "metadata": {...}
    }
  ]
}
```

## Testing

Run tests to verify configuration:
```bash
pytest tests/test_config.py::test_kopia_config_load_from_yaml -v
pytest tests/checkers/test_kopia_snapshot_checker.py::TestKopiaSnapshotChecker -v
```

## Migration from Old Format

### Before (deprecated)
```yaml
kopiasnapshotstatus:
  targets:
    snapshot_paths:
      - /data
      - /backups
    max_age_hours: 24
```

### After (new format)
```yaml
kopiasnapshotstatus:
  targets:
    snapshots:
      - path: /data
        max_age_hours: 24
      - path: /backups
        max_age_hours: 24
    max_age_hours: 24
```

## Troubleshooting

**Q: Can I omit max_age_hours for some paths?**
A: Yes! They'll use the global `max_age_hours` value.

**Q: Do CLI flags merge with YAML config?**
A: No. CLI `--snapshot` flags **replace** the YAML config entirely.

**Q: How does it handle SSH paths with multiple colons?**
A: The parser splits on the **rightmost** space between PATH and MAX_AGE_HOURS, so `user@host:/path@24` works correctly.

**Q: Can I set max_age_hours to 0?**
A: Yes, but snapshots must be fresher than 0 hours (essentially never allowed). Use with caution.
