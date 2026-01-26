[![PyPI - Version](https://img.shields.io/pypi/v/kuma-sentinel.svg)](https://pypi.org/project/kuma-sentinel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kuma-sentinel.svg)](https://pypi.org/project/kuma-sentinel)
[![Deploy to ghcr.io](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/ghcr.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/ghcr.yml)
[![Deploy to PyPI](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/pypi.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/pypi.yml)
[![Lint](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/lint.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/lint.yml)
[![Test](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/test.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/test.yml)
[![GitMCP](https://img.shields.io/endpoint?url=https://gitmcp.io/badge/0x6f677548/kuma-sentinel)](https://gitmcp.io/0x6f677548/kuma-sentinel)


# Kuma-Sentinel: Uptime Kuma Monitoring Agent

**The monitoring agent for Uptime Kuma. Monitor internal systems, custom checks, and server health—then push results back to your Uptime Kuma instance.**

While [Uptime Kuma](https://github.com/louislam/uptime-kuma) is excellent for external monitoring (HTTP, Ping, TCP), it lacks a native agent to monitor internal system states, processes, or run custom checking scripts.

**Kuma-Sentinel bridges this gap.** Designed as a CLI utility, it becomes a powerful monitoring agent when deployed via cron, systemd, or Docker. It runs on your servers to execute arbitrary shell commands, check backups, monitor storage, and scan ports—then pushes the health status back to Uptime Kuma.

**Monitor ANY system condition**: If you can check it with a shell command, Kuma-Sentinel can monitor it.

## Quick Example

```bash
# Monitor via YAML config (supports multiple commands)
kuma-sentinel cmdcheck --config /etc/kuma-sentinel/config.yaml

# Or monitor single condition via CLI
kuma-sentinel cmdcheck \
  --command "systemctl is-active nginx" \
  http://uptime-kuma:3001/api/push \
  heartbeat-token \
  cmdcheck-token
```

If all checks pass → Uptime Kuma shows **UP**. If any fail → shows **DOWN** and triggers alerts.

Deploy via `cron`, `systemd timer`, or `Docker` to run periodically on your servers.

For multiple commands, use YAML config with `cmdcheck.commands` list.

## Features

- **Command Execution**: Execute arbitrary shell commands on remote systems and push results to Uptime Kuma (cmdcheck)
- **Pattern Matching**: Use regex patterns for flexible success/failure detection in command output
- **Multi-Command Support**: Run multiple independent checks and aggregate results
- **Port Scanning**: Scans TCP open ports across IP ranges using nmap with configurable ports, timing profiles, and exclusion lists
- **Backup Monitoring**: Monitor Kopia backup snapshot freshness, detect stale or missing snapshots
- **Storage Monitoring**: Monitor ZFS pool health and free space with per-pool thresholds
- **Heartbeat Monitoring**: Sends periodic heartbeat pings during long operations to signal agent health and activity
- **Uptime Kuma Integration**: Reports monitoring results and health status to Uptime Kuma push monitors
- **Flexible Configuration**: Support for YAML config files, environment variables for tokens only, and CLI arguments with clear priority
- **Multi-Source Configuration**:
  1. Command-line arguments (highest priority)
  2. YAML config file
  3. Token environment variables only (authentication tokens only)
  4. Hardcoded defaults (lowest priority)
- **Comprehensive Logging**: File, console, and syslog/journalctl output
- **Security First**: Commands executed without shell interpretation to prevent injection attacks
- **Extensible Architecture**: Built to support additional monitoring checks

## Diagram

```plaintext
┌─────────────────────────────┐
│   Monitoring Machine        │
│   (Kuma Sentinel)           │
│                             │
│  • Command Execution        │
│  • Port Scanning (nmap)     │
│  • Backup Monitoring (Kopia)│
│  • Storage Monitoring (ZFS) │
└────────────┬────────────────┘
             │ Push results
             │ via HTTP
             ▼
┌─────────────────────────────┐
│     Uptime Kuma             │
│   (Central Server)          │
│                             │
│  • Monitor Status           │
│  • Send Alerts              │
│  • Track Metrics            │
└─────────────────────────────┘
```

## Installation

### Via pip (PyPI)

```bash
pip install kuma-sentinel
```

### From source

```bash
git clone https://go.hugobatista.com/gh/kuma-sentinel.git
cd kuma-sentinel
pip install -e .
```

### Development installation

```bash
pip install -e ".[dev]"
```

### Docker

You can run Kuma Sentinel in a Docker container for isolated execution and easy deployment.

#### Using docker-compose (Recommended)

1. Create your configuration file:

```bash
cp example.config.yaml config.yaml
```

2. Edit `config.yaml` with your settings

3. Build and run:

```bash
docker-compose up --build -it
```

#### Using docker run directly

```bash
docker build -t kuma-sentinel:latest .

# Linux/macOS
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-sentinel/config.yaml:ro \
  -v $(pwd)/kuma-sentinel.log:/var/log/kuma-sentinel.log \
  -e KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token \
  -e KUMA_SENTINEL_PORTSCAN_TOKEN=your-portscan-token \
  kuma-sentinel:latest \
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push \
  your-heartbeat-token your-portscan-token

# Windows (PowerShell)
docker run -it --rm `
  -v ${pwd}/config.yaml:/etc/kuma-sentinel/config.yaml:ro `
  -v ${pwd}/kuma-sentinel.log:/var/log/kuma-sentinel.log `
  -e KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token `
  -e KUMA_SENTINEL_PORTSCAN_TOKEN=your-portscan-token `
  kuma-sentinel:latest `
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push `
  your-heartbeat-token your-portscan-token
```

## Usage

### Command Execution (cmdcheck)

Execute arbitrary shell commands on remote systems and push results to Uptime Kuma. The cornerstone feature enabling unlimited monitoring scenarios.

**Single command check (CLI):**
```bash
kuma-sentinel cmdcheck \
  --command "systemctl is-active nginx" \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-cmdcheck-token
```

**Multiple independent checks (YAML config only - all must pass for UP):**
```yaml
# In config file: /etc/kuma-sentinel/config.yaml
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: "web_server"
      timeout: 10
    - command: "test -f /var/run/app.pid"
      name: "app_pid"
      timeout: 5
    - command: "df /"
      name: "disk_space"
      success_pattern: "(\\d{2,}|[1-9]\\d{5,})"  # Match if available space exists
      timeout: 10
  uptime_kuma:
    token: your-cmdcheck-token
```

**With regex pattern matching (CLI):**
```bash
kuma-sentinel cmdcheck \
  --command "tail -n 100 /var/log/app.log" \
  --failure-pattern "ERROR|CRITICAL|PANIC" \
  --success-pattern "healthy" \
  --timeout 10 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-cmdcheck-token
```

**Using configuration file (recommended for multiple commands):**
```bash
kuma-sentinel cmdcheck --config /etc/kuma-sentinel/config.yaml
```

**Note**: CLI supports single commands only. For multiple commands, use YAML configuration with `cmdcheck.commands` list.

See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) for comprehensive cmdcheck examples and security considerations.

### Port Scan

Scans TCP open ports across IP ranges using nmap with configurable ports, timing profiles, and exclusion lists.

**Basic usage:**
```bash
kuma-sentinel portscan 192.168.1.0/24 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token
```

**With custom ports and timing:**
```bash
kuma-sentinel portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  192.168.100.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

**Multiple IP ranges:**
```bash
kuma-sentinel portscan \
  192.168.1.0/24 \
  10.0.0.0/8 \
  172.16.0.0/12 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

**With exclusions:**
```bash
kuma-sentinel portscan \
  --exclude 192.168.1.1,192.168.1.254 \
  192.168.1.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

**Using configuration file (recommended):**
```bash
kuma-sentinel portscan --config /etc/kuma-sentinel/config.yaml
```

**Nmap Timing Profiles:**
The `--timing` parameter controls scan speed and network load:
- `T0`: Paranoid - Very slow, useful for IDS evasion
- `T1`: Sneaky - Slow, IDS evasion
- `T2`: Polite - Slowed to minimize network load
- `T3`: Normal - Default, no delays
- `T4`: Aggressive - Fast, assumes reasonable network
- `T5`: Insane - Very fast, assumes excellent network

### Kopia Snapshot Status

Monitor Kopia backup snapshot freshness with per-path age thresholds:

```bash
# Using configuration file (recommended)
kuma-sentinel kopiasnapshotstatus --config /etc/kuma-sentinel/config.yaml

# Or with CLI arguments
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-kopia-token
```

Multiple snapshots with different age requirements:
```bash
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  --snapshot /archive 168 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-kopia-token
```

### ZFS Pool Status

Monitor ZFS pool health and free space with per-pool thresholds:

```bash
# Using configuration file (recommended)
kuma-sentinel zfspoolstatus --config /etc/kuma-sentinel/config.yaml

# Or with CLI arguments
kuma-sentinel zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-zfs-token
```

Multiple pools with different free space thresholds:
```bash
kuma-sentinel zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  --pool archive 30 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-zfs-token
```

## Use Cases

### Universal Monitoring via Command Execution

Monitor ANY condition on remote systems using standard shell commands. From service health to custom business logic, deploy once and monitor everything.

**Scenario**: You need to monitor diverse conditions across your infrastructure - service health, database connectivity, custom application checks, disk space, log patterns, and more. Instead of building custom monitoring for each scenario, use cmdcheck to execute any shell command.

**Traditional approach**: Build specialized monitoring tools and extensions for each unique condition.

**With Kuma Sentinel cmdcheck**: Write a shell command that returns exit code 0 for "healthy" and non-zero for "unhealthy". Deploy once, monitor anything.

**Example setup on monitoring machine** (using YAML config for multiple checks):
```yaml
# In config file: /etc/kuma-sentinel/config.yaml
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: "web_server"
    - command: "systemctl is-active postgresql"
      name: "database"
    - command: "test -f /var/lock/app.running"
      name: "app_running"
  timeout: 10
  uptime_kuma:
    token: your-cmdcheck-token
```

Then run: `kuma-sentinel cmdcheck --config /etc/kuma-sentinel/config.yaml`

**Additional examples** (single command via CLI):
```bash
# Check service status
kuma-sentinel cmdcheck \
  --command "systemctl is-active nginx"

# Check health endpoint
kuma-sentinel cmdcheck \
  --command "curl -sf http://localhost:8080/health"

# Check log file for errors (using failure pattern)
kuma-sentinel cmdcheck \
  --command "tail -n 100 /var/log/app.log" \
  --failure-pattern "ERROR|CRITICAL"

# Database connectivity check
kuma-sentinel cmdcheck \
  --command "psql -h db.example.com -U monitoring -d health_check -c SELECT 1"

# Custom script execution
kuma-sentinel cmdcheck \
  --command "/usr/local/bin/custom-health-check.sh"
```

**Note**: Commands are executed without shell interpretation for security. Simple commands work great. For complex logic (pipes, operators), wrap your commands in shell scripts. See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md#command-execution-limitations) for details.

**Result**:
- ✅ If all checks pass (exit 0) → Uptime Kuma shows UP
- ⚠️ If any check fails (non-zero exit) → Uptime Kuma shows DOWN and triggers alerts
- 🔍 Pattern matching for advanced scenarios: detect specific error messages, parse output, etc.

**Benefits**:
- Unlimited monitoring scenarios with a single tool
- No specialized monitoring code needed
- Leverage existing scripts and tools (systemctl, curl, grep, custom apps)
- Easy to test locally before deploying
- Version control your monitoring logic

See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md#command-monitoring-cmdcheck) for comprehensive cmdcheck documentation including security considerations, multi-command scenarios, and pattern matching.

### Per-Command Visibility in Uptime Kuma Dashboard

One of the challenges with traditional monitoring is getting enough detail to troubleshoot quickly. Kuma Sentinel sends rich, human-readable status messages that show exactly which commands passed or failed.

**Example - Single Command Result**:
```
✓ Success pattern detected: 'healthy' | Output: active (running)
```
Uptime Kuma dashboard shows the exact status in one line without needing to SSH and inspect logs.

**Note**: Any sensitive data in the actual output (passwords, tokens, connection strings) would be automatically sanitized before display, even though raw output is shown in documentation examples for clarity.

**Example - Multiple Commands Result**:
```
✗ 2/3 passed, 1/3 failed: nginx (exit 1); postgresql ✓; cache ✓
```
Immediately see which service is down and why (exit code, pattern not found, timeout, etc.).

**Example - Diagnostic Output**:
```
✗ 0/5 passed, 5/5 failed: web (exit 1); db (timeout); cache (pattern not found); backup (error); app (exit 127)
```
The top 3 failures are shown inline; check logs for remaining failures. Each failure includes the specific error reason.

**Benefits of rich status messages**:
- ✅ One-glance status visibility without logs
- ✅ Identify problematic services immediately
- ✅ See failure reasons (exit code, pattern mismatch, timeout, etc.)
- ✅ Reduced MTTR (mean time to resolution) through instant diagnosis
- ✅ Works perfectly with Uptime Kuma's dashboard and alert messages

**Logging for Deep Debugging**:
When you need full details, check logs:
```
[2024-01-15 14:32:15] cmdcheck executing 5 commands
[2024-01-15 14:32:15] [nginx: ✓] [postgresql: ✗ timeout] [cache: ✗ exit 1] [backup: ✓] [app: ✗ pattern not found]
[2024-01-15 14:32:15] Result: 2/5 passed, 3/5 failed
```

### Network Security Monitoring

Monitor ports on your network to ensure no unauthorized ports are exposed. Deploy Kuma Sentinel on your watchdog/monitoring machines and schedule it to run periodically via cron or systemd timer to push results to your central Uptime Kuma instance.

**Scenario**: You have multiple machines in your infrastructure that you want to monitor for exposed ports. Your watchdog machine should periodically scan a range of machines to ensure only expected ports are open.

**Traditional approach**: Set up individual TCP port monitors in Uptime Kuma for each machine/port combination, which becomes difficult to manage at scale.

**With Kuma Sentinel**: Install on your watchdog machine and run a portscan check that scans your infrastructure and reports back to your central Uptime Kuma instance.

**Example setup on a watchdog machine**:
```bash
# Deploy in Docker
docker-compose up -d

# Schedule with cron to run every 30 minutes
*/30 * * * * kuma-sentinel portscan \
  --exclude 192.168.1.1,192.168.1.10 \
  --ports 22,3389,80,443 \
  192.168.1.0/24 \
  http://uptime-kuma-instance:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

**Result**: 
- ✅ If all scanned ports are in expected state → Uptime Kuma shows UP
- ⚠️ If unexpected open ports are detected → Uptime Kuma shows DOWN and triggers alerts

### Backup Monitoring

Monitor Kopia backup snapshot freshness across multiple backup paths with different age requirements. Ensure your backups are running on schedule and alert if backups become stale.

**Scenario**: You have multiple critical data paths being backed up with Kopia at different intervals, and you need to ensure backups complete regularly without manual intervention.

**Traditional approach**: Manually check backup timestamps or SSH into the machine to verify backup age.

**With Kuma Sentinel**: Deploy on your backup server and run periodic Kopia snapshot status checks that report to Uptime Kuma.

**Example setup on a backup server**:
```bash
# Deploy in Docker
docker-compose up -d

# Schedule with cron to run every 6 hours
0 */6 * * * kuma-sentinel kopiasnapshotstatus --config /etc/kuma-sentinel/config.yaml
```

**Configuration example** (`/etc/kuma-sentinel/config.yaml`):
```yaml
kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token
  
  snapshots:
    - path: /data
      max_age_hours: 24      # Critical data - must be backed up daily
    - path: /backups
      max_age_hours: 48      # Important - allow 2 days
    - path: /archive
      max_age_hours: 168     # Archive - allow 1 week
  max_age_hours: 24          # Global default
```

**See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) for advanced Kopia snapshot configuration options**

**Result**:
- ✅ If all snapshots are fresh (within their thresholds) → Uptime Kuma shows UP
- ⚠️ If any snapshot is stale → Uptime Kuma shows DOWN and triggers alerts
- 📊 Details include age of each snapshot and its threshold for visibility

### Storage Health Monitoring

Monitor ZFS pool health and free space across multiple pools with different thresholds. Ensure pools remain operational and have adequate free space for continued operation.

**Scenario**: You have multiple ZFS pools with different purposes and acceptable minimum free space levels. A data pool should always have at least 10% free, while an archive pool can tolerate 30% free space.

**Traditional approach**: Manually check pool status via SSH or rely on generic disk space alerts.

**With Kuma Sentinel**: Deploy on your storage server and run periodic ZFS pool status checks that report to Uptime Kuma.

**Example setup on a storage server**:
```bash
# Deploy in Docker
docker-compose up -d

# Schedule with cron to run every hour
0 * * * * kuma-sentinel zfspoolstatus --config /etc/kuma-sentinel/config.yaml
```

**Configuration example** (`/etc/kuma-sentinel/config.yaml`):
```yaml
zfspoolstatus:
  uptime_kuma:
    token: your-zfs-token
  
  pools:
    - name: tank
      free_space_percent_min: 10      # Critical: must stay operational
    - name: backup
      free_space_percent_min: 20      # Important: needs space for incremental backups
    - name: archive
      free_space_percent_min: 30      # Archive: more relaxed threshold
  free_space_percent_default: 10
```

**See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) for advanced ZFS pool configuration options**

**Result**:
- ✅ If all pools are ONLINE with sufficient free space → Uptime Kuma shows UP
- ⚠️ If any pool is unhealthy (DEGRADED, FAULTED, OFFLINE, etc.) → Uptime Kuma shows DOWN and triggers alerts
- ⚠️ If any pool has insufficient free space → Uptime Kuma shows DOWN and triggers alerts
- 📊 Details include health status and free space for each pool

### Help

```bash
kuma-sentinel --help
kuma-sentinel portscan --help
kuma-sentinel kopiasnapshotstatus --help
kuma-sentinel zfspoolstatus --help
```

## Configuration

### YAML File Format (Recommended)

Default location: `/etc/kuma-sentinel/config.yaml`

**For detailed configuration options and examples, see [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)**

Basic structure:

```yaml
logging:
  log_file: /var/log/kuma-sentinel.log
  log_level: INFO

heartbeat:
  enabled: true
  interval: 300                          # Seconds between heartbeats (default: 300 = 5 min)
  uptime_kuma:
    token: your-heartbeat-token

uptime_kuma:
  url: http://uptimekuma:3001/api/push

portscan:
  uptime_kuma:
    token: your-portscan-token
  
  nmap:
    timing: T3
    arguments: []
    keep_xml_output: false
    timeout: 3600
  
  ports: 1-1000
  exclude: [192.168.1.1, 192.168.1.254]
  ip_ranges:
    - 192.168.1.0/24
    - 10.0.0.0/8

kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token
  
  snapshots:
    - path: /data
      max_age_hours: 24
    - path: /backups
      max_age_hours: 48
  max_age_hours: 24

zfspoolstatus:
  uptime_kuma:
    token: your-zfs-token
  
  pools:
    - name: tank
      free_space_percent_min: 10
    - name: backup
      free_space_percent_min: 20
  free_space_percent_default: 10
```

See [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) for advanced configuration with per-pool thresholds and all command examples.

## Security

### Command Execution Security

Kuma Sentinel is designed with **security as a core principle**:

- ✅ **No Shell Injection**: Commands are executed without shell interpretation. Shell metacharacters are treated as literal arguments, preventing injection attacks.
- ✅ **Safe from Chaining**: Semicolons, pipes, operators (`&&`, `||`, etc.) cannot be used to chain commands or inject new ones.
- ✅ **Safe Configuration**: Configuration files (YAML) are the only input mechanism for commands - never accept commands from untrusted sources.

**Example - What's Protected:**

```yaml
# ✅ Shell metacharacters are safely rejected (treated as literal arguments)
commands:
  - command: "systemctl is-active nginx; rm -rf /"  # Semicolon is literal, not a separator
```

With shell=False, the semicolon is passed as a literal argument to systemctl, which rejects it as invalid.

**⚠️ What's NOT Protected:**

If an attacker gains write access to the config file, they can replace the entire command:
```yaml
# ❌ This IS a threat if config file is compromised
commands:
  - command: "rm -rf /"  # Attacker can replace command directly
```

**Real Protection**: Secure your configuration files with proper file permissions (see "Configuration File Permissions" below).

### Running as Non-Root

⚠️ **Always run Kuma Sentinel as a dedicated, low-privilege user**:

```bash
useradd -r -s /bin/false kuma-sentinel
chown kuma-sentinel:kuma-sentinel /etc/kuma-sentinel/config.yaml
chmod 600 /etc/kuma-sentinel/config.yaml
```

If specific commands require elevated privileges, use sudo with **minimal, read-only access**:

```bash
# In sudoers (restrict to specific commands)
kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl is-active
kuma-sentinel ALL=(root) NOPASSWD: /usr/sbin/zpool status
```

### Configuration File Permissions

Always restrict access to configuration files:

```bash
chmod 600 /etc/kuma-sentinel/config.yaml
chown kuma-sentinel:kuma-sentinel /etc/kuma-sentinel/config.yaml
```

Configuration files may contain authentication tokens - they should only be readable by the service user.

### Handling Sensitive Data

Command output is **automatically sanitized by default** to prevent credential leakage:

- ✅ **Automatic Masking**: Passwords, API keys, tokens, emails, and database connection strings are automatically masked
- ✅ **Truncation**: Output is truncated to 500 characters before transmission
- ✅ **Error Sanitization**: Exception messages are sanitized to remove sensitive data

**Patterns Automatically Masked:**
- Passwords: `password=...`, `secret: ...`, `api_key=...`
- Tokens: Bearer tokens, AWS keys, GitHub tokens
- Emails: `user@example.com` → `[REDACTED_EMAIL]`
- Credit cards: `[REDACTED_CARD]`
- Database URLs: Connection strings → `[REDACTED_DB_CONNECTION]`

**Example:**
```
Command output: Connected to mysql://root:password@localhost
After sanitization: Connected to [REDACTED_DB_CONNECTION]
```

**Disable Sanitization (if needed for debugging):**
```yaml
cmdcheck:
  sanitize_output: false  # Default: true - NOT recommended for production
```

**Best Practices:**
- ⚠️ **Avoid outputting secrets** - Rely on exit codes and pattern matching when possible
- ⚠️ **Sanitize scripts** - Remove debug output containing sensitive data
- ⚠️ **Use pattern matching** - Match on status indicators instead of capturing full output

Example - Better approach using pattern matching:

Since `shell=False` prevents piping, use pattern matching in your config instead:

```yaml
# In config file - check API health with pattern matching
cmdcheck:
  commands:
    - command: "curl -s http://api.internal:8080/health"
      name: "api_health"
      success_pattern: '"status":"ok"'    # Match only this pattern
      failure_pattern: '"error"'           # Fail if error detected
      timeout: 10
  uptime_kuma:
    token: your-cmdcheck-token
```

**Why this is better:**
- ✅ Only the matched pattern determines pass/fail, not the full output
- ✅ Sensitive details in the response are masked by default (sanitization)
- ✅ Clear intent: you care about status success, not the full API response
- ✅ Works with `shell=False` (no pipes needed)

**For complex logic that needs pipes**: Wrap your command in a shell script:
```bash
# myscript.sh
#!/bin/bash
curl -s http://api.internal:8080/health | jq -e '.status == "ok"' > /dev/null

# Then in config:
commands:
  - command: "/usr/local/bin/myscript.sh"
    name: "api_health"
```

### Further Reading

For comprehensive security guidance, see [CONFIGURATION_GUIDE.md - Security Considerations](CONFIGURATION_GUIDE.md#security-considerations)


### Authentication Tokens (Environment Variables Only)

Only authentication tokens are supported via environment variables for security reasons. All other configuration must use YAML files or CLI arguments.

**Supported token environment variables:**
- `KUMA_SENTINEL_HEARTBEAT_TOKEN` - Heartbeat push token
- `KUMA_SENTINEL_CMDCHECK_TOKEN` - Command check push token
- `KUMA_SENTINEL_PORTSCAN_TOKEN` - Port scan push token
- `KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN` - Kopia snapshot push token
- `KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN` - ZFS pool status push token

**Configuration Priority** (highest to lowest): CLI arguments > YAML file > Token environment variables > Defaults

### CLI Arguments

```bash
kuma-sentinel portscan \
  --ports 22,80,443 \
  --timing T4 \
  --exclude 192.168.1.1 \
  --log-file /tmp/scan.log \
  192.168.1.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

## Cron Job Example

```bash
# Run scan every 30 minutes
*/30 * * * * kuma-sentinel portscan --config /etc/kuma-sentinel/config.yaml
```

### Systemd Timer Example

Create `/etc/systemd/system/kuma-sentinel.service`:

```ini
[Unit]
Description=Kuma Sentinel Monitoring Agent
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/kuma-sentinel portscan --config /etc/kuma-sentinel/config.yaml
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/kuma-sentinel.timer`:

```ini
[Unit]
Description=Kuma Sentinel Timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable and start:

```bash
systemctl enable kuma-sentinel.timer
systemctl start kuma-sentinel.timer
systemctl status kuma-sentinel.timer
```

## Uptime Kuma Push Tokens

### Creating Monitors

1. In Uptime Kuma, create two new Push monitors:
   - **Heartbeat Monitor**: Reports agent health every X seconds (shared across all commands)
   - **Port-Scan Monitor**: Reports port scan results (UP=all ports closed, DOWN=open ports found)

2. Configure with appropriate heartbeat intervals (suggest 10-15 minutes for heartbeat monitor)

3. Copy the push tokens to your configuration

## Logging

Logs are written to:

1. **File**: Configured in `log_file` (default: `/var/log/kuma-sentinel.log`)
2. **Level**: Configured in `log_level` (default: `INFO`, options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
3. **Console**: Standard output for direct execution
4. **Journalctl**: Syslog integration for systemd systems

Example log output:

```
[2024-01-18 14:30:00] 🔍 PORT SCANNER CONFIGURATION SUMMARY
[2024-01-18 14:30:00] 📝 Nmap Configuration:
[2024-01-18 14:30:00]    Ports: 1-1000
[2024-01-18 14:30:00]    Timing: T3
[2024-01-18 14:30:00] 🔍 Running: nmap -p 1-1000 -T3 -oX /tmp/nmap_output.xml 192.168.1.0/24
[2024-01-18 14:30:15] ✅ Heartbeat sent: Port scan in progress...
[2024-01-18 14:35:00] ✅ Nmap scan completed successfully
[2024-01-18 14:35:00] ✅ Parsed XML: found 3 hosts with open ports
[2024-01-18 14:35:00] ⚠️  Open ports found: 192.168.1.10:22/tcp,80/tcp, 192.168.1.11:443/tcp
[2024-01-18 14:35:01] ✅ Port alert sent (down): Open ports found: 192.168.1.10:22/tcp,80/tcp, 192.168.1.11:443/tcp (5m)
[2024-01-18 14:35:02] ✅ Port scanner complete (5m)
```

## Requirements

- Python 3.10+
- click (installed automatically)

**Per-Command Requirements:**
- **portscan**: nmap (must be installed on system and in PATH)
- **kopiasnapshotstatus**: Kopia backup tool (must be installed and configured on system)
- **zfspoolstatus**: ZFS tools (zpool command, available with ZFS installation)

## Development

For detailed development instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

### Quick Setup

```bash
git clone https://go.hugobatista.com/gh/kuma-sentinel.git
cd kuma-sentinel
pip install -e ".[dev]"
```

### Quick Commands

**Run tests:**
```bash
pytest
pytest --cov=src/kuma_sentinel
pytest -v
```

**Code quality checks:**
```bash
hatch run check  # Run ruff, black, and mypy
ruff check src/ tests/
black src/ tests/
mypy src/ tests/
```

### Building Package

See [DEVELOPMENT.md](DEVELOPMENT.md#building-the-package) for package build instructions.

```bash
python -m pip install build
python -m build
```

## License

MIT License - See [LICENSE](LICENSE) file for details

## Author

Hugo Batista - [GitHub](https://go.hugobatista.com/gh)

## Contributing

Contributions are welcome! See [DEVELOPMENT.md](DEVELOPMENT.md) for development setup and guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run tests and linting: `hatch run check`
6. Submit a pull request

## Issues

Found a bug? Report it on [GitHub Issues](https://go.hugobatista.com/gh/kuma-sentinel/issues)

## Related Projects

- [Uptime Kuma](https://github.com/louislam/uptime-kuma) - Self-hosted monitoring tool
- [Nmap](https://nmap.org/) - Network mapper and security scanner
- [Click](https://click.palletsprojects.com/) - Python CLI framework
