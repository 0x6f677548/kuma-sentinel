# Configuration Guide for Kuma Sentinel

## Command Monitoring (cmdcheck)

Execute arbitrary shell commands on remote systems and monitor ANY condition. The universal monitoring command that enables unlimited use cases.

### Quick Start

#### Single Command - Simple Health Check

**YAML Configuration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
heartbeat:
  uptime_kuma:
    token: your-heartbeat-token
cmdcheck:
  command: "systemctl is-active nginx"
  timeout: 10
  uptime_kuma:
    token: your-cmdcheck-token
```

**CLI:**
```bash
kuma-sentinel cmdcheck \
  --command "systemctl is-active nginx" \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-cmdcheck-token
```

**Environment Variables:**
```bash
export UPTIME_KUMA_URL=http://uptimekuma:3001/api/push
export KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token
export KUMA_SENTINEL_CMDCHECK_TOKEN=your-cmdcheck-token
export KUMA_SENTINEL_CMDCHECK_TIMEOUT=10

kuma-sentinel cmdcheck --command "systemctl is-active nginx"
```

#### Multiple Commands - All Must Pass

**YAML Configuration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
heartbeat:
  uptime_kuma:
    token: your-heartbeat-token
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: web_server
      timeout: 10
    
    - command: "systemctl is-active postgresql"
      name: database
      timeout: 10
    
    - command: "test -f /var/run/app.pid"
      name: app_running
      timeout: 5
  uptime_kuma:
    token: your-cmdcheck-token
```

**Result**: DOWN if ANY command fails, UP only if ALL succeed

#### Pattern Matching - Detect Conditions in Output

**YAML Configuration:**
```yaml
cmdcheck:
  command: "tail -n 100 /var/log/app.log"
  failure_pattern: "ERROR|CRITICAL|PANIC"  # Detected → DOWN
  success_pattern: "^healthy"              # Not detected (with failure) → DOWN
  timeout: 10
  capture_output: true
  uptime_kuma:
    token: your-cmdcheck-token
```

**CLI with Pattern:**
```bash
kuma-sentinel cmdcheck \
  --command "systemctl status myapp" \
  --failure-pattern "failed|error" \
  --success-pattern "active.*running"
```

### Key Features

✅ **Arbitrary Commands** — Run shell commands, scripts, binaries with full shell features (pipes, redirects, logic operators)
✅ **Pattern Matching** — Detect success/failure via regex patterns on command output (failure > success > exit code precedence)
✅ **Multiple Commands** — Run multiple independent checks, all must pass for UP
✅ **Custom Exit Codes** — Specify expected exit code (default 0), handles non-zero success cases (grep, test, etc.)
✅ **Output Truncation** — Last 500 characters captured and sent to Uptime Kuma (prevents log flooding)
✅ **Timeout Protection** — Configure per-command timeout (1-300 seconds) to prevent hangs
✅ **Per-Command Overrides** — Individual timeouts, exit codes, patterns per command in multiple mode
✅ **Type-Safe Configuration** — YAML validation prevents configuration errors

### Configuration Reference

#### Global Settings

```yaml
cmdcheck:
  # Required: Either 'command' (single) or 'commands' (multiple)
  command: "shell command to execute"        # Single command mode
  # OR
  multiple: true                              # Enable multiple command mode
  commands:                                   # List of command objects (when multiple: true)
    - command: "cmd1"
      name: "optional name for reporting"
      timeout: 10                             # Optional: per-command override
      expect_exit_code: 0                     # Optional: per-command override
      success_pattern: "pattern"              # Optional: per-command override
      failure_pattern: "pattern"              # Optional: per-command override
      capture_output: true                    # Optional: per-command override
  
  # Command-specific settings (single command mode)
  timeout: 30                                 # Execution timeout in seconds (1-300, default 30)
  expect_exit_code: 0                         # Expected success exit code (0-255, default 0)
  capture_output: true                        # Capture stdout/stderr (default true, last 500 chars)
  success_pattern: null                       # Regex pattern for success (optional)
  failure_pattern: null                       # Regex pattern for failure (optional, takes precedence)
  
  uptime_kuma:
    token: "your-cmdcheck-token"              # Required: push token for this command
```

#### Pattern Matching Logic

```
1. failure_pattern: If matches in output → Status: DOWN (highest priority)
2. success_pattern: If matches in output → Status: UP
                   If not matches → Status: DOWN (if provided, must match)
3. Exit code:       exit_code == expect_exit_code → Status: UP (fallback)
```

**Examples:**
```yaml
# Example 1: Service status check (exit code only)
cmdcheck:
  command: "systemctl is-active myapp"
  expect_exit_code: 0
  timeout: 5

# Example 2: Log error detection (failure pattern)
cmdcheck:
  command: "tail -n 500 /var/log/app.log"
  failure_pattern: "ERROR|CRITICAL|PANIC"
  timeout: 10

# Example 3: Health endpoint with status line (success pattern)
cmdcheck:
  command: "curl -s http://localhost:8080/health"
  success_pattern: '"status":\s*"healthy"'
  timeout: 5

# Example 4: Disk space check (custom exit code)
cmdcheck:
  command: "test $(df /var | tail -1 | awk '{print $4}') -gt 1000000"
  expect_exit_code: 0
  timeout: 5

# Example 5: Multiple independent checks
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: nginx
      timeout: 10
    - command: "systemctl is-active postgresql"
      name: postgresql
      timeout: 10
    - command: "curl -sf http://app.local/health"
      name: app_health
      timeout: 5
      success_pattern: "OK"
```

### Use Cases

#### 1. Service Health Monitoring

Check if critical services are running:
```yaml
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: web_server
      timeout: 10
    - command: "systemctl is-active postgresql"
      name: database
      timeout: 10
    - command: "systemctl is-active redis-server"
      name: cache
      timeout: 10
```

#### 2. Custom Health Endpoints

Monitor application health endpoints:
```yaml
cmdcheck:
  command: "curl -s http://localhost:8080/api/health | grep -q 'healthy'"
  success_pattern: "healthy"
  timeout: 5
```

#### 3. File Existence Checks

Alert if critical files are missing:
```yaml
cmdcheck:
  command: "test -f /var/run/app.pid && test -f /var/spool/lock"
  timeout: 5
```

#### 4. Disk Space Monitoring

Ensure sufficient disk space:
```yaml
cmdcheck:
  command: "test $(df / | tail -1 | awk '{print $4}') -gt 5000000"
  timeout: 10
```

#### 5. Log Pattern Detection

Alert on error patterns in logs:
```yaml
cmdcheck:
  command: "journalctl -u myapp -n 1000 --no-pager"
  failure_pattern: "ERROR|CRITICAL|FATAL"
  success_pattern: "Running normally"
  timeout: 10
```

#### 6. Database Connectivity

Verify database health:
```yaml
cmdcheck:
  command: "psql -h db.example.com -U monitoring -d health_check -c 'SELECT 1' -q"
  expect_exit_code: 0
  timeout: 10
```

#### 7. Custom Script Execution

Run custom monitoring scripts:
```yaml
cmdcheck:
  command: "/usr/local/bin/custom-health-check.sh"
  success_pattern: "^HEALTHY"
  timeout: 30
```

### Security Considerations

⚠️ **CRITICAL SECURITY MODEL**: Kuma Sentinel assumes **configuration is admin-controlled**. Commands are defined in config files or CLI arguments, NOT from untrusted user input.


#### Attack Vectors & Mitigations

| Vector | Risk | Mitigation |
|--------|------|-----------|
| Shell Metacharacters (`;`, `&&`, `\|`) | Command chaining if input is uncontrolled | Config-only commands; admin responsibility |
| PATH Manipulation | Malicious `ls` via hijacked PATH | Dedicated service user; use absolute paths in commands |
| Privilege Escalation | Commands running as root | Run as dedicated low-privilege user |
| Resource Exhaustion | Fork bombs, infinite loops | Timeout (default 30s) + cgroup limits in container |
| Output Leakage | Sensitive data in command output | Output truncated to 500 chars; document data sensitivity |

#### Deployment Best Practices

1. **Run under dedicated user:**
   ```bash
   useradd -r -s /bin/false kuma-sentinel
   chown kuma-sentinel:kuma-sentinel /etc/kuma-sentinel/config.yaml
   chmod 600 /etc/kuma-sentinel/config.yaml
   ```

2. **Use systemd service with restricted capabilities:**
   ```ini
   [Service]
   User=kuma-sentinel
   Group=kuma-sentinel
   NoNewPrivileges=yes
   ProtectSystem=strict
   ProtectHome=yes
   ReadWritePaths=/var/log/kuma-sentinel
   ```

3. **Enable sudo for specific commands if needed:**
   ```bash
   # /etc/sudoers.d/kuma-sentinel
   kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl, /usr/bin/zpool
   ```

4. **Container deployment (recommended):**
   ```dockerfile
   FROM python:3.11-slim
   RUN useradd -r -s /bin/false kuma-sentinel
   COPY --chown=kuma-sentinel:kuma-sentinel config.yaml /etc/kuma-sentinel/
   USER kuma-sentinel
   ```

5. **Centralized logging:**
   ```bash
   # Send all command output and errors to centralized logging
   kuma-sentinel cmdcheck --config /etc/kuma-sentinel/config.yaml 2>&1 | \
     logger -t kuma-sentinel -s
   ```

#### What NOT to Do

❌ Don't run commands that output passwords, API keys, or PII (output visible to Uptime Kuma)
❌ Don't allow user-provided commands via web interfaces
❌ Don't run kuma-sentinel as root unless absolutely necessary
❌ Don't expose Uptime Kuma push tokens in logs or metrics
❌ Don't use shell=True with unchecked user input

#### Output Sensitivity

Command output is:
- Truncated to 500 characters (last 500 chars retained)
- Sent to Uptime Kuma in plaintext
- Possibly stored in logs and dashboards
- Visible to anyone with Uptime Kuma access

**Example safe outputs:**
✅ `active (running)` — Service status
✅ `OK` — Health check result
✅ `HEALTHY` — Custom application status
✅ `1` — Database connectivity test

**Example dangerous outputs:**
❌ `password: abc123` — Credentials
❌ `api_key: sk-1234567890` — API keys
❌ `user@example.com` — PII
❌ Database connection strings with passwords

### Common Examples

#### Monitor Multiple Services

```yaml
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: nginx
    - command: "systemctl is-active postgresql"
      name: postgresql
    - command: "systemctl is-active redis-server"
      name: redis
    - command: "systemctl is-active app"
      name: app
  timeout: 10
  uptime_kuma:
    token: your-token
```

#### Monitor Backup Completion

```yaml
cmdcheck:
  command: "find /var/backups -name 'backup-*.tar' -mtime -1 | wc -l | grep -q '^[1-9]$'"
  success_pattern: "^[1-9]"
  failure_pattern: "^0"
  timeout: 30
```

#### Check Application via Custom Script

```yaml
cmdcheck:
  command: "/opt/monitoring/check_app_health.sh"
  success_pattern: "HEALTHY"
  failure_pattern: "ERROR|UNHEALTHY|TIMEOUT"
  timeout: 60
```

#### Database Replica Lag Check

```yaml
cmdcheck:
  command: "psql -h replica.db -U monitoring -c \"SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))\" | grep -E '^\\s+[0-9]{1,3}(\\.[0-9]+)?\\s*$'"
  timeout: 15
```

### Result Message Format

Uptime Kuma displays rich status messages with per-command visibility, allowing you to see exactly which commands passed or failed without inspecting logs.

#### Single Command Results

**Success:**
```
✓ Success pattern detected: 'healthy' | Output: active (running)
```

**Failure - Pattern Mismatch:**
```
✗ Pattern not found: expected 'OK' in output
```

**Failure - Exit Code:**
```
✗ Command failed (exit 1, expected 0)
```

**Failure - Timeout:**
```
✗ Command timeout after 30 seconds
```

#### Multiple Command Results

**All Pass:**
```
✓ 3/3 commands succeeded: nginx ✓, postgresql ✓, redis ✓
```

**Some Fail:**
```
✗ 1/3 passed, 2/3 failed: nginx (exit 1); postgresql (pattern not found); redis ✓
```

**All Fail:**
```
✗ 0/3 passed, 3/3 failed: nginx (exit 1); postgresql (timeout); redis (error)
```

#### Reading Results in Uptime Kuma Dashboard

The message field shows:
- **Status symbol** — ✓ (UP) or ✗ (DOWN) at a glance
- **Pass/fail ratio** — For multiple commands, see how many passed
- **Failure reasons** — Top 3 failures with specific error reasons
- **Command names** — When using named commands in multiple mode

**Example workflow:**
1. Uptime Kuma shows ✗ DOWN status in dashboard
2. Click on the heartbeat to see the message
3. Read "✗ 2/5 passed, 3/5 failed: database (exit 1); cache (timeout); backup (pattern not found)"
4. Immediately know which 3 services have issues and why
5. No need to SSH and inspect logs to diagnose the problem

#### Logging for Detailed Debugging

Full per-command breakdown is logged locally for detailed debugging:
```
[2024-01-15 14:32:15] cmdcheck executing 3 commands
[2024-01-15 14:32:15] [nginx: ✓] [database: ✗ exit 1] [cache: ✗ timeout] 
[2024-01-15 14:32:15] Result: 1/3 passed, 2/3 failed
```

Check logs with:
```bash
# All kuma-sentinel logs
docker logs kuma-sentinel

# Or journalctl if running as systemd service
journalctl -u kuma-sentinel -n 100
```

---

## Kopia Snapshot Monitoring (kopiasnapshotstatus)

Monitor backup snapshot age and alert when backups are stale.

### Quick Start

#### Configuration File (YAML)
```yaml
kopiasnapshotstatus:
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

### Environment Variables
```bash
# Format: path1:age1,path2:age2
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS="/data:24,/backups:48"
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS=24
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
```

## Key Features

✅ **Per-path thresholds** — Each snapshot can have different age requirements
✅ **Global fallback** — Paths without explicit threshold use global default
✅ **SSH support** — Handles remote paths like `user@host:/path`
✅ **CLI override** — CLI `--snapshot` flags replace YAML config entirely
✅ **Type-safe** — Structured YAML format prevents configuration errors
✅ **Multi-source config** — Load from YAML files, environment variables, or CLI arguments

## Configuration Reference

### Structure
```
kopiasnapshotstatus:
  snapshots:          # List of snapshot configurations
    - path: <string>  # Required: snapshot path (local or remote)
      max_age_hours: <int>  # Optional: max age hours (falls back to global default)
  max_age_hours: <int> # Global default (default: 24)
```

### Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):
1. **CLI arguments** - Command-line `--snapshot` and `--max-age-hours` flags (highest priority)
2. **YAML file** - Configuration from config file
3. **Environment variables** - `KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_*` variables
4. **Defaults** - Built-in defaults (max_age_hours: 24)

**Note:** CLI arguments completely override YAML/environment config. Each layer fully replaces the previous one—they don't merge.

### YAML Configuration

```yaml
kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token
  snapshots:
    - path: /data
      max_age_hours: 24
    - path: /backups
      max_age_hours: 48
  max_age_hours: 24
```

### Environment Variables

Format: `VARIABLE_NAME=value`

```bash
# Snapshots: comma-separated path:age pairs (age is hours)
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS="/data:24,/backups:48,/archive:168"

# Global default for snapshots without explicit threshold
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS=24

# API token for Uptime Kuma
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token

# Shared settings (same for all commands)
KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token
KUMA_SENTINEL_HEARTBEAT_INTERVAL=300
KUMA_SENTINEL_UPTIME_KUMA_URL=http://uptimekuma:3001/api/push
```

**Environment variable format for snapshots:**
- Format: `path1:age1,path2:age2`
- Paths with colons (SSH paths): Split from the right, so `user@host:/data:24` → path=`user@host:/data`, age=`24`
- Paths without age: Use global default (e.g., `/data` uses `KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS`)

**Examples:**
```bash
# Simple local paths
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS="/data:24,/backups:48"

# Remote SSH paths
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS="root@fileserver:/mnt/shares:48,user@backup:/archive:168"

# Mixed with defaults (no age specified uses global default)
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_SNAPSHOTS="/data:24,/backups"
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS=24
```

### CLI Arguments

```bash
# Single snapshot
kuma-sentinel kopiasnapshotstatus --snapshot /data 24

# Multiple snapshots
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  --snapshot "user@host:/path" 72

# With config file and additional settings
kuma-sentinel kopiasnapshotstatus \
  --config /etc/kuma-sentinel/config.yaml \
  --max-age-hours 24
```

## Examples

### Local paths with different thresholds:
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

## Troubleshooting

**Q: Can I omit max_age_hours for some paths?**
A: Yes! They'll use the global `max_age_hours` value.

**Q: Do CLI flags merge with YAML config?**
A: No. CLI `--snapshot` flags **replace** the YAML config entirely.

**Q: How does it handle SSH paths with multiple colons?**
A: The parser splits on the **rightmost** space between PATH and MAX_AGE_HOURS, so `user@host:/path@24` works correctly.

**Q: Can I set max_age_hours to 0?**
A: Yes, but snapshots must be fresher than 0 hours (essentially never allowed). Use with caution.
---

# Port Scan Configuration Guide

## Quick Start

### Configuration File (YAML)
```yaml
portscan:
  ports: 1-1000
  exclude: [192.168.1.1, 192.168.1.254]
  ip_ranges:
    - 192.168.1.0/24
  nmap:
    timing: T3
```

### Command Line
```bash
# Basic port scan
kuma-sentinel portscan 192.168.1.0/24

# With custom ports and timing
kuma-sentinel portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  192.168.1.0/24
```

### Environment Variables
```bash
# Port ranges to scan (comma-separated)
KUMA_SENTINEL_PORTSCAN_PORTS=1-1000

# IP ranges to exclude (comma-separated)
KUMA_SENTINEL_PORTSCAN_EXCLUDE="192.168.1.1,192.168.1.254"

# IP ranges to scan (comma-separated)
KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.1.0/24,10.0.0.0/8"

# Nmap timing profile
KUMA_SENTINEL_PORTSCAN_NMAP_TIMING=T3

# Nmap timeout
KUMA_SENTINEL_PORTSCAN_NMAP_TIMEOUT=3600

# Additional nmap arguments
KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS=--script vuln

# Keep nmap XML output
KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT=false

# API token
KUMA_SENTINEL_PORTSCAN_TOKEN=your-portscan-token
```

## Configuration Reference

### YAML Structure
```yaml
portscan:
  uptime_kuma:
    token: <string>              # Uptime Kuma API token
  
  nmap:
    timing: <T0-T5>             # Timing profile (default: T3)
    timeout: <int>              # Timeout in seconds (default: 3600)
    arguments: [<args>]         # Additional nmap arguments
    keep_xml_output: <bool>     # Keep XML output file (default: false)
  
  ports: <port-spec>            # Port range: "1-1000", "22,80,443" (default: 1-1000)
  exclude: [<ip-list>]          # IPs to exclude from scan
  ip_ranges: [<range-list>]     # IP ranges to scan (e.g., 192.168.1.0/24)
```

### Environment Variables

**Parsing rules:**
- Comma-separated lists: `192.168.1.0/24,10.0.0.0/8` or `192.168.1.1,192.168.1.254`
- Whitespace is trimmed automatically
- Examples:
  ```bash
  KUMA_SENTINEL_PORTSCAN_EXCLUDE="192.168.1.1, 192.168.1.254"  # Spaces handled
  KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.1.0/24,10.0.0.0/8"
  ```

### CLI Arguments

```bash
# Single IP range
kuma-sentinel portscan 192.168.1.0/24

# Multiple IP ranges
kuma-sentinel portscan 192.168.1.0/24 10.0.0.0/8

# With custom ports
kuma-sentinel portscan --ports 22,80,443 192.168.1.0/24

# With exclusions
kuma-sentinel portscan \
  --exclude 192.168.1.1 \
  --exclude 192.168.1.254 \
  192.168.1.0/24

# With nmap timing
kuma-sentinel portscan --timing T4 192.168.1.0/24

# All options combined
kuma-sentinel portscan \
  --ports 1-10000 \
  --timing T4 \
  --exclude 192.168.1.1 \
  --exclude 192.168.1.254 \
  192.168.1.0/24 \
  10.0.0.0/8
```

## Nmap Timing Profiles

| Profile | Name | Speed | Use Case |
|---------|------|-------|----------|
| T0 | Paranoid | Very slow | IDS evasion |
| T1 | Sneaky | Slow | IDS evasion, stealth |
| T2 | Polite | Moderate | Network-friendly |
| T3 | Normal | Default | Standard scans (default) |
| T4 | Aggressive | Fast | Fast networks |
| T5 | Insane | Very fast | Excellent networks, time-critical |

## Examples

### Basic network scan
```yaml
portscan:
  ports: 1-1000
  ip_ranges:
    - 192.168.1.0/24
```

```bash
KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.1.0/24"
```

### Multi-range scan with exclusions
```yaml
portscan:
  ports: 22,80,443,3306,3389
  exclude:
    - 192.168.1.1
    - 192.168.1.254
  ip_ranges:
    - 192.168.1.0/24
    - 10.0.0.0/8
  nmap:
    timing: T4
```

```bash
KUMA_SENTINEL_PORTSCAN_PORTS="22,80,443,3306,3389"
KUMA_SENTINEL_PORTSCAN_EXCLUDE="192.168.1.1,192.168.1.254"
KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.1.0/24,10.0.0.0/8"
KUMA_SENTINEL_PORTSCAN_NMAP_TIMING=T4
```

### Fast scan with custom arguments
```yaml
portscan:
  ports: 1-65535
  ip_ranges:
    - 192.168.100.0/24
  nmap:
    timing: T5
    arguments:
      - --script vuln
      - --min-rate 1000
```

```bash
KUMA_SENTINEL_PORTSCAN_PORTS="1-65535"
KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.100.0/24"
KUMA_SENTINEL_PORTSCAN_NMAP_TIMING=T5
KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS="--script vuln,--min-rate 1000"
```

## Common Port Ranges

- **Well-known ports**: 1-1023
- **Registered ports**: 1024-49151
- **Common services**: 22,25,53,80,110,143,443,465,587,993,995,3306,3389,5432,5900,8080,8443
- **SSH/RDP/Web**: 22,80,443,3389
- **Database ports**: 3306 (MySQL), 5432 (PostgreSQL), 1433 (MSSQL), 27017 (MongoDB)

## Troubleshooting

**Q: How do I specify a range of ports?**
A: Use nmap notation: `1-1000` (range), `22,80,443` (individual), or `1-1000,8080-8090` (mixed)

**Q: Can I exclude specific subnets instead of individual IPs?**
A: Yes, CIDR notation works: `192.168.1.0/25` or `192.168.1.128/25`

**Q: What's the difference between timing profiles?**
A: Higher numbers (T4, T5) scan faster but are more aggressive. Lower numbers (T0, T1) are slower and stealthier. Use T3-T4 for most scenarios.

**Q: How do I handle IP ranges with multiple colons in CSV format?**
A: The parser handles CSV correctly: `192.168.1.0/24, 10.0.0.0/8` (whitespace trimmed automatically)

**Q: Can I keep the nmap XML output for further analysis?**
A: Yes, set `keep_xml_output: true` in config or use `KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT=true`

---

# ZFS Pool Status Configuration Guide

## Quick Start

### Configuration File (YAML)
```yaml
zfspoolstatus:
  pools:
    - name: tank
      free_space_percent_min: 10
    - name: backup
      free_space_percent_min: 20
    - name: archive
      # Omits free_space_percent_min → uses global default
  free_space_percent_default: 10
  uptime_kuma:
    token: your-zfs-token
```

### Command Line
```bash
# Monitor multiple pools with thresholds
kuma-sentinel zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-zfs-token
```

### Environment Variables
```bash
# Format: pool1:min_free%,pool2:min_free%
KUMA_SENTINEL_ZFSPOOLSTATUS_POOLS="tank:10,backup:20,archive:15"
KUMA_SENTINEL_ZFSPOOLSTATUS_FREE_SPACE_PERCENT=10
KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN=your-zfs-token
```

## Key Features

✅ **Per-pool thresholds** — Each pool can have different minimum free space requirements
✅ **Global fallback** — Pools without explicit threshold use global default (10% by default)
✅ **Health monitoring** — Detects unhealthy pools (DEGRADED, FAULTED, OFFLINE)
✅ **Individual failures** — One failing pool doesn't prevent checking others
✅ **CLI override** — CLI `--pool` flags replace YAML config entirely
✅ **Type-safe** — Structured YAML format prevents configuration errors

## Configuration Reference

### Structure
```
zfspoolstatus:
  pools:                          # List of pool configurations
    - name: <string>              # Required: pool name (e.g., "tank")
      free_space_percent_min: <int>  # Optional: min free space % (falls back to global default)
  free_space_percent_default: <int>  # Global default (default: 10)
  uptime_kuma:
    token: <string>               # Uptime Kuma API token
```

### Environment Variables

**Parsing rules:**
- Comma-separated lists: `pool1:10,pool2:20,pool3:15`
- Whitespace is trimmed automatically
- Pools without threshold use global default
- Examples:
  ```bash
  KUMA_SENTINEL_ZFSPOOLSTATUS_POOLS="tank:10,backup:20"
  KUMA_SENTINEL_ZFSPOOLSTATUS_POOLS="tank:10, backup:20"  # Spaces handled
  KUMA_SENTINEL_ZFSPOOLSTATUS_FREE_SPACE_PERCENT=10
  ```

### CLI Arguments

```bash
# Single pool
kuma-sentinel zfspoolstatus --pool tank 10

# Multiple pools
kuma-sentinel zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  --pool archive 15

# With config file
kuma-sentinel zfspoolstatus \
  --config /etc/kuma-sentinel/config.yaml

# Override global default
kuma-sentinel zfspoolstatus \
  --pool tank 10 \
  --free-space-percent 15
```

## Pool Health Status

Only `ONLINE` status is considered healthy. Any other status triggers an alert:

| Status | Description | Alert |
|--------|-------------|-------|
| ONLINE | Pool is healthy and operational | ✅ OK if free space >= threshold |
| DEGRADED | Pool operational but reduced redundancy (missing disk) | ⚠️ DOWN |
| FAULTED | Pool has encountered fatal errors | ⚠️ DOWN |
| OFFLINE | Pool is offline (user request) | ⚠️ DOWN |
| REMOVED | Pool was removed | ⚠️ DOWN |

**Note:** All non-ONLINE states immediately trigger DOWN status, regardless of free space.

## Examples

### Single pool with default threshold
```yaml
zfspoolstatus:
  pools:
    - name: tank
  free_space_percent_default: 10
```

### Multiple pools with different thresholds
```yaml
zfspoolstatus:
  pools:
    - name: tank
      free_space_percent_min: 10      # Critical: needs 10% free
    - name: backup
      free_space_percent_min: 20      # Important: needs 20% free
    - name: archive
      free_space_percent_min: 30      # Archive: more relaxed
  free_space_percent_default: 10
```

```bash
KUMA_SENTINEL_ZFSPOOLSTATUS_POOLS="tank:10,backup:20,archive:30"
```

### Mix pools with and without explicit thresholds
```yaml
zfspoolstatus:
  pools:
    - name: tank
      free_space_percent_min: 10
    - name: backup                   # Uses global default (15%)
    - name: archive                  # Uses global default (15%)
  free_space_percent_default: 15
```

```bash
KUMA_SENTINEL_ZFSPOOLSTATUS_POOLS="tank:10,backup,archive"
KUMA_SENTINEL_ZFSPOOLSTATUS_FREE_SPACE_PERCENT=15
```

## Alert Messages

### All pools healthy
```
✅ All pools healthy: tank: 25.0% free; backup: 50.0% free
```

### Pool with low free space
```
⚠️ Low free space: tank: 8.0% < 10%; backup: 12.0% < 20%
```

### Unhealthy pool status
```
⚠️ Unhealthy pools: tank (status: FAULTED), backup (status: DEGRADED)
```

### Per-pool details in result
```json
{
  "pool_details": {
    "tank": {
      "status": "ONLINE",
      "free_percent": 25.0,
      "threshold": 10
    },
    "backup": {
      "status": "DEGRADED",
      "free_percent": 40.0,
      "threshold": 20
    }
  }
}
```

## Troubleshooting

**Q: Why is the command failing with "zpool not found"?**
A: ZFS tools must be installed on the system. Install with: `apt install zfsutils-linux` (Debian/Ubuntu) or `yum install zfs` (RHEL/CentOS)

**Q: How do I check pool status manually?**
A: Use: `zpool list -H -o name,size,alloc,free,cap,health POOL_NAME`

**Q: Can I omit free_space_percent_min for some pools?**
A: Yes! They'll use the global `free_space_percent_default` value.

**Q: Do CLI flags merge with YAML config?**
A: No. CLI `--pool` flags **replace** the YAML config entirely.

**Q: What if a pool doesn't exist?**
A: The command reports it as a failed pool and returns DOWN status.

**Q: Can I set free_space_percent to 0?**
A: Yes, but pools must have >0% free space. A value of 0 means the pool must never be completely full.

---

## Shared Configuration

All commands support these shared settings:

### Logging
```yaml
logging:
  log_file: /var/log/kuma-sentinel.log
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

```bash
KUMA_SENTINEL_LOG_FILE=/var/log/kuma-sentinel.log
KUMA_SENTINEL_LOG_LEVEL=INFO
```

### Heartbeat (Uptime Kuma monitoring)
```yaml
heartbeat:
  enabled: true
  interval: 300              # seconds
  uptime_kuma:
    token: your-heartbeat-token
```

```bash
KUMA_SENTINEL_HEARTBEAT_ENABLED=true
KUMA_SENTINEL_HEARTBEAT_INTERVAL=300
KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token
```

### Uptime Kuma URL
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
```

```bash
KUMA_SENTINEL_UPTIME_KUMA_URL=http://uptimekuma:3001/api/push
```

## Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):

1. **CLI arguments** - Command-line flags (highest priority)
2. **YAML file** - Configuration from `--config` file
3. **Environment variables** - `KUMA_SENTINEL_*` environment variables
4. **Defaults** - Built-in default values (lowest priority)

**Loading order in code:**
```
Defaults (in __init__)
  ↓
Environment variables (load_from_env)
  ↓
YAML file (load_from_yaml)
  ↓
CLI arguments (load_from_args) ← Final value wins
```

**Note:** Each layer completely replaces the previous one—values don't merge.

### Example Priority

Given these configurations:

```yaml
# config.yaml (YAML file - second highest)
portscan:
  ports: 1-1000
```

```bash
# Environment variable (third highest)
export KUMA_SENTINEL_PORTSCAN_PORTS="22,80,443"

# CLI argument (highest priority - takes final effect)
kuma-sentinel portscan --ports 1-65535
```

**Result:** Scans ports `1-65535` (CLI argument wins over all others)

If you remove the CLI argument:
```bash
unset KUMA_SENTINEL_PORTSCAN_PORTS
kuma-sentinel portscan
# Result: Scans ports 1-1000 (YAML file wins)
```

If you also remove the YAML entry:
```yaml
# config.yaml: (no ports entry)
portscan:
  ip_ranges: [192.168.1.0/24]
```

Then environment variable wins:
```bash
export KUMA_SENTINEL_PORTSCAN_PORTS="22,80,443"
kuma-sentinel portscan
# Result: Scans ports 22,80,443 (environment variable wins)
```

---

## Testing Your Configuration

### Validate YAML syntax
```bash
# Python can validate YAML
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

### Dry run with verbose logging
```bash
kuma-sentinel portscan --log-level DEBUG --config config.yaml
```

### Test environment variables
```bash
export KUMA_SENTINEL_PORTSCAN_IP_RANGES="192.168.1.0/24"
kuma-sentinel portscan
```

### Run configuration tests
```bash
pytest tests/test_config.py -v
pytest tests/checkers/test_port_checker.py -v
pytest tests/checkers/test_kopia_snapshot_checker.py -v
```