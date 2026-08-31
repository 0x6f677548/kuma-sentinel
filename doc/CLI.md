# CLI Quick Reference

For detailed command options, use `--help`:

```bash
kuma-scout --help           # All commands
kuma-scout run --help       # Specific command help
```

## Basic Usage

### Configuration-Based Execution

Most common usage - run all checks from a YAML config:

```bash
kuma-scout run /etc/kuma-scout/config.yaml
```

Filter by tag, name, or type:

```bash
kuma-scout run config.yaml --tag critical
kuma-scout run config.yaml --name nginx-check
kuma-scout run config.yaml --type portscan
```

**Result Reporting Behavior:**

When running checks:

1. **Individual Results**: Each check sends its result to:
   - Check-specific token (if configured with `uptime_kuma.token`)
   - Global token (if check has no specific token but global token is configured)

2. **Automatic Tag Aggregation**: Results are automatically aggregated by tag if:
   - Checks have `tags` defined
   - Tag tokens are configured in the `tags:` section
   - Aggregated results are sent IN ADDITION to individual results

**Example:** Running 3 checks with tags `[network, critical]` using config with global token and tag tokens:
```
✓ check-1 result → global token
✓ check-2 result → global token
✓ check-3 result → global token
✓ network tag aggregated result → network tag token
✓ critical tag aggregated result → critical tag token

Total: 5 API calls to Uptime Kuma (3 individual + 2 aggregated)
```

**Note on `--tag` filtering:** The `--tag` flag filters which checks to execute (e.g., `--tag critical` only runs checks tagged "critical"). Aggregation happens independently - all executed checks are aggregated by their tags.

### Command-Line Check (Ad-Hoc)

Execute a single check without config file (requires `--uptime-kuma-url` and `--token`):

```bash
# Simple command check
kuma-scout cmdcheck "systemctl is-active nginx" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN

# With optional name and SSH
kuma-scout cmdcheck "systemctl is-active nginx" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
  --name "nginx-health" \
  --ssh admin@server

# With pattern matching
kuma-scout cmdcheck "curl http://api:8080/health" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
  --success-pattern '"status":"ok"'
```

### Port Scanning

```bash
# Scan network (requires --uptime-kuma-url and --token)
kuma-scout portscan 192.168.1.0/24 \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN

# Specific ports with optional name
kuma-scout portscan 192.168.1.0/24 \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
  --ports 22,80,443 \
  --name "web-servers"
```

### Backup & Storage Monitoring

```bash
# Check Kopia backup age (requires --uptime-kuma-url and --token)
kuma-scout kopiasnapshotstatus "/data" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
  --name "data-backup"

# Check ZFS pool (requires --uptime-kuma-url and --token)
kuma-scout zfspoolstatus "tank" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
  --name "tank-pool"
```

## Key Options

**For individual check commands** (cmdcheck, portscan, kopiasnapshotstatus, zfspoolstatus):
- `--uptime-kuma-url` and `--token` are **required**
- `--name` is **optional** (auto-generated if omitted)

**For config-based execution** (`kuma-scout run <config.yaml>`):
- All settings come from the YAML file

| Option | Required | Purpose | Example |
|--------|----------|---------|---------|
| `--token TOKEN` | ✓ (for individual checks) | Uptime Kuma push token (overrides per-check config) | `--token abc123` |
| `--uptime-kuma-url URL` | ✓ (for individual checks) | Uptime Kuma API endpoint (overrides per-check config) | `--uptime-kuma-url http://uptimekuma:3001/api/push` |
| `--name NAME` | ✗ | Check name (auto-generated if omitted) | `--name "nginx-health"` |
| `--ssh CONNECTION` | ✗ | Remote SSH execution (overrides per-check config) | `--ssh user@server` or `--ssh user@server:2222` |
| `--timeout SECONDS` | ✗ | Operation timeout (overrides per-check and global timeouts) | `--timeout 600` |
| `--log-level LEVEL` | ✗ | Debug output | `--log-level DEBUG` |
| `--log-file PATH` | ✗ | Log file path | `--log-file /var/log/kuma-scout.log` |
| `--quiet` | ✗ | Suppress console output | `--quiet` |
| `--verbose` | ✗ | Enable verbose logging with console output | `--verbose` |

## Configuration Priority

Settings are resolved in order:

1. **CLI arguments** (highest)
2. **YAML config file**
3. **Defaults** (lowest)

```bash
# CLI overrides config
export MY_TOKEN=my-token-value
kuma-scout run config.yaml --token "${MY_TOKEN}"  # CLI token wins
```

## Output Control

### Quiet Mode (`--quiet`)

Suppress all console output while maintaining file and syslog logging:

```bash
# Run silently, only logs go to file/syslog
kuma-scout run config.yaml --quiet --log-file /var/log/kuma-scout.log
```

Useful for:
- Cron jobs and automated systems
- Running checks in background without terminal output
- Clean Docker/container execution

### Verbose Mode (`--verbose`)

Enable debug-level logging with console output:

```bash
# Show detailed execution flow
kuma-scout run config.yaml --verbose

# Verbose with custom log file
kuma-scout run config.yaml --verbose --log-file /var/log/debug.log
```

Useful for:
- Troubleshooting check failures
- Understanding execution flow
- Debugging configuration issues

**Note:** Quiet and verbose modes are mutually exclusive. Using both will result in an error.

## Variable Expansion

Tokens in both YAML config and CLI support environment variable expansion using `${VAR}` syntax:

**In YAML config:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}  # Any env var name

heartbeat:
  token: ${MY_HEARTBEAT_TOKEN}  # Any env var name
```

**On CLI:**
```bash
export MY_TOKEN=secure-token-here
kuma-scout cmdcheck "uptime" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token "${MY_TOKEN}" \
  --name "my-check"
```

Use any environment variable name - expansion happens at runtime for tokens only.

## Scheduling

### crontab

```bash
*/5 * * * * kuma-scout run /etc/kuma-scout/config.yaml
```

### systemd Timer

Set `OnUnitActiveSec=5min` in `/etc/systemd/system/kuma-scout.timer`

## More Information

- **All config options**: See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)
- **Security & SSH setup**: See [SECURITY.md](SECURITY.md)
- **Docker deployment**: See [DOCKER.md](DOCKER.md)
