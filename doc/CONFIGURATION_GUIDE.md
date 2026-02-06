# Configuration Guide for Kuma Scout

**Upgrading from a previous version?** See [MIGRATION.md](MIGRATION.md) for breaking changes and migration instructions between versions.

## Overview: How Configuration Works

Kuma Scout supports multiple configuration sources that work together with a clear priority order. This flexibility allows you to:
- Use environment variable expansion throughout your config (via `${VAR}` syntax)
- Use YAML files for detailed, reusable configurations
- Override settings via command-line arguments for one-off executions

**Important:** All configuration values in YAML support variable expansion using `${VARIABLE_NAME}` syntax. CLI tokens also support this syntax when quoted: `--token "${MY_TOKEN}"`.

### Configuration Priority (Highest to Lowest)

1. **CLI Arguments** - Command-line flags override everything
2. **YAML Config File** - Settings in `/etc/kuma-scout/config.yaml` (or custom path via `kuma-scout run /path/to/config.yaml`)
3. **Hardcoded Defaults** - Built-in fallback values

This means if you set a value in multiple places, CLI arguments win, followed by YAML, then defaults.

**Note:** Configuration files do not automatically read environment variables by name. Instead, use `${VAR}` syntax in YAML config to expand environment variables at runtime. This works for all configuration values, not just tokens.

**Example Priority in Action:**
```bash
# Let's say config.yaml has timeout: 30
# And CLI has --timeout 60

# Result: timeout will be 60 (CLI wins, YAML provides fallback)
```

### Configuration Methods

**Method 1: YAML File (Recommended for production)**
- Centralized configuration
- Easy to version control and audit
- Supports complex scenarios (multiple paths, pools, snapshots)
- Default location: `/etc/kuma-scout/config.yaml`
- Usage: `kuma-scout run /path/to/config.yaml`
- Supports variable expansion in tokens: `${VAR_NAME}`
- Filter checks by name, type, or tag:

```bash
# Run all checks (results auto-aggregate by tag)
kuma-scout run config.yaml

# Filter to run only specific tags
kuma-scout run config.yaml --tag critical
kuma-scout run config.yaml --tag backup

# Filter by check name
kuma-scout run config.yaml --name nginx-health

# Filter by check type
kuma-scout run config.yaml --type cmdcheck
kuma-scout run config.yaml --type portscan
```

**Important - Automatic Tag Aggregation:**
- When running checks, results are AUTOMATICALLY aggregated by tag
- Each check sends an individual result to its token
- Additionally, aggregated results are sent to each tag's token
- `--tag` filtering selects which checks to run, but aggregation happens independently for all executed checks
- See [Tag-Based Result Aggregation](#tag-based-result-aggregation) section below for detailed explanation and examples

**Method 2: CLI Arguments (Recommended for testing/one-off runs)**
- Quick testing and debugging
- No files needed
- Perfect for cron jobs with inline parameters
- Tokens support variable expansion: `--token "${MY_TOKEN}"`

**Method 3: Defaults**
- Built-in fallback values
- Minimal required configuration

### Global Configuration

These settings apply to all monitoring checks:

**Uptime Kuma Integration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push  # Where to send push notifications
  token: ${UPTIME_KUMA_TOKEN}          # Global token (can be overridden per check)
```

**Heartbeat Service:**
```yaml
heartbeat:
  enabled: true                          # Enable/disable heartbeat pings
  interval: 300                          # Seconds between heartbeats (default: 300 = 5 min)
  token: ${HEARTBEAT_TOKEN}              # Uptime Kuma token for heartbeat
```

**Tag-Based Result Aggregation:**
```yaml
tags:
  network:
    token: ${NETWORK_AGGREGATION_TOKEN}  # Token for aggregated network check results
    description: "Aggregated status for all network checks"
  
  backup:
    token: ${BACKUP_AGGREGATION_TOKEN}
    description: "Aggregated status for all backup checks"
```

**How Tag Aggregation Works:**

When checks are executed, results are automatically aggregated by tag. Each check sends TWO reports:

1. **Individual Result**: Sent to the check's own Uptime Kuma token (if configured)
2. **Aggregated Result**: Sent to the tag's aggregation token (in addition to individual report)

**Token Priority for Individual Results:**
1. Check-level `uptime_kuma.token` (if configured on the check itself)
2. Global `uptime_kuma.token` (if configured at the top level)
3. No report sent (if neither is configured)

This means checks can have NO explicit token configured and still send results to the global token, which will also be aggregated by tag.

**Aggregation Logic:**
- **Status**: "down" if ANY check in the tag is "down", otherwise "up"
- **Message**: Combined summary of all checks in the tag with their individual statuses
- **Duration**: Sum of all check durations in the tag (milliseconds)

**Example Flow - Dual Reporting:**
```bash
# Configuration
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: DEFAULT_GLOBAL_TOKEN    # Default token for all checks

tags:
  network:
    token: NETWORK_AGGREGATION_TOKEN

checks:
  - name: internet-check
    type: cmdcheck
    command: "curl -f https://example.com"
    tags: [network]
    # No check-level token, will use global token

  - name: lan-ports
    type: portscan
    targets: "192.168.1.0/24"
    tags: [network]
    uptime_kuma:
      token: PORTSCAN_CUSTOM_TOKEN   # Specific token for this check

# Results sent to:
# 1. internet-check result:
#    - DEFAULT_GLOBAL_TOKEN (individual result)
#    - NETWORK_AGGREGATION_TOKEN (as part of aggregated "network" tag)
#
# 2. lan-ports result:
#    - PORTSCAN_CUSTOM_TOKEN (individual result, overrides global)
#    - NETWORK_AGGREGATION_TOKEN (as part of aggregated "network" tag)
#
# 3. Aggregated "network" tag result:
#    - NETWORK_AGGREGATION_TOKEN (combined status for both checks)
```

**Important Notes:**
- Aggregation happens automatically for all tags present in executed checks
- No `--tag` filtering required - all results are always aggregated
- Tag tokens are optional - if a tag has no token configured, aggregation skips that tag (with debug logging)
- Individual check results are sent immediately after each check completes
- Aggregated results are sent AFTER all checks complete

**Logging:**
```yaml
logging:
  file: /var/log/kuma-scout.log          # Log file path
  level: INFO                            # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**SSH Remote Execution:**
```yaml
# Global SSH settings for all checks
ssh:
  # SSH connection string (recommended approach)
  # Supported formats: ssh://user@host:port, user@host:port, user@host, host:port, host
  host: backup-server.example.com
  
  user: root                             # SSH username
  port: 22                               # SSH port
  key_file: /root/.ssh/id_rsa            # Path to SSH private key
  password: "${SSH_PASSWORD}"            # SSH password (discouraged, use keys)
  strict_host_key_checking: true         # Verify host keys (default: true)
```

### Checks Configuration

Individual checks are defined in the `checks:` list. Each check can override global settings:

```yaml
checks:
  # Example check with global settings
  - name: "nginx-health"
    type: cmdcheck
    command: "systemctl is-active nginx"
    tags: [web, critical]
    
  # Example check with overrides
  - name: "remote-backup"
    type: kopia_snapshot
    snapshot: /data,24
    tags: [backup]
    # Override global SSH settings for this check
    ssh:
      host: backup-server.local
      key_file: /etc/kopia/ssh_key
    # Override global Uptime Kuma settings for this check
    uptime_kuma:
      token: backup-specific-token
```
      max_age_hours: 24
```

**SSH Configuration Priority:**
1. CLI arguments (`--ssh`, `--ssh-key-file`, `--ssh-password`) - highest priority
2. YAML config (command-specific `ssh:` section)
3. YAML config (global `ssh:` section)
4. SSH config file (`~/.ssh/config`)
5. Defaults (local execution) - lowest priority

**Note:** SSH settings in YAML config support variable expansion just like all other config values. For sensitive data like SSH passwords, use `${VAR}` syntax (though keys are recommended over passwords).

**For CLI options and usage examples, see [CLI.md](CLI.md)**

---

## Command Monitoring (cmdcheck)

Execute arbitrary shell commands on remote systems and monitor ANY condition. The universal monitoring command that enables unlimited use cases.

### Quick Start

#### Single Command - Simple Health Check

**YAML Configuration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

heartbeat:
  enabled: true
  uptime_kuma:
    token: your-heartbeat-token

checks:
  - name: nginx-health
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    uptime_kuma:
      token: your-cmdcheck-token
```

**CLI (Single Command Only):**
```bash
kuma-scout cmdcheck "systemctl is-active nginx" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-cmdcheck-token \
  --heartbeat-token your-heartbeat-token
```

#### Multiple Independent Checks

**YAML Configuration (Multiple Checks):**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

heartbeat:
  enabled: true
  uptime_kuma:
    token: your-heartbeat-token

checks:
  - name: web_server
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    
  - name: database
    type: cmdcheck
    command: "systemctl is-active postgresql"
    timeout: 10
    uptime_kuma:
      token: specific-token-for-postgresql
    
  - name: app_running
    type: cmdcheck
    command: "test -f /var/run/app.pid"
    timeout: 5
```

**Result**: Each check executes independently and sends its own UP/DOWN result to Uptime Kuma. Checks with their own `uptime_kuma.token` send to individual monitors. Checks without a token use the global token. There is no aggregation of results across checks.

**CLI Limitation**: CLI only supports single checks. For multiple checks, use YAML configuration as shown above.

#### Pattern Matching - Detect Conditions in Output

**YAML Configuration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: log_errors
    type: cmdcheck
    command: "tail -n 100 /var/log/app.log"
    failure_pattern: "ERROR|CRITICAL|PANIC"  # Detected → DOWN
    success_pattern: "^healthy"              # Not detected (with failure) → DOWN
    timeout: 10
    uptime_kuma:
      token: your-cmdcheck-token
```

**CLI with Pattern:**
```bash
kuma-scout cmdcheck "systemctl status myapp" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-cmdcheck-token \
  --heartbeat-token your-heartbeat-token \
  --failure-pattern "failed|error" \
  --success-pattern "active.*running"
```

#### Authentication Token

**Using variable expansion:**
```bash
# Set your token in environment
export MY_CMDCHECK_TOKEN=your-token

# Use in YAML with variable expansion
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${MY_CMDCHECK_TOKEN}
```

**Or on CLI:**
```bash
export MY_TOKEN=your-cmdcheck-token
kuma-scout cmdcheck "command" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_TOKEN}" \
  --name "my-check"
```

**Or directly in YAML:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: cmdcheck-service
    type: cmdcheck
    command: "your-command-here"
    uptime_kuma:
      token: your-cmdcheck-token
```

#### Retry Logic - Handle Transient Failures

**YAML Configuration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: api_check
    type: cmdcheck
    command: "curl -s https://api.example.com/health"
    retry:
      attempts: 5                          # Per-command override
      delay_seconds: 10                    # Per-command delay override
```

**CLI Configuration:**
```bash
kuma-scout cmdcheck "curl -s https://api.example.com/health" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-token \
  --retry-attempts 3 \
  --retry-delay-seconds 5
```

**Result**: Failed commands are retried up to the specified count with delays between attempts. Only failed commands are retried; successful commands proceed normally. SSH connections are re-established for each retry attempt.

### Key Features

- ✅ **Arbitrary Commands** — Run shell commands, scripts, binaries
- ✅ **Pattern Matching** — Detect success/failure via regex patterns on command output (failure > success > exit code precedence)
- ✅ **Multiple Checks** — Run multiple independent checks (via YAML), each sending results independently
- ✅ **Custom Exit Codes** — Specify expected exit code (default 0), handles non-zero success cases (grep, test, etc.)
- ✅ **Output Truncation** — Last 500 characters captured and sent to Uptime Kuma (prevents log flooding)
- ✅ **Timeout Protection** — Configure per-command timeout (1-300 seconds) to prevent hangs
- ✅ **Retry Logic** — Configurable retries with delays for failed commands
- ✅ **Per-Command Overrides** — Individual timeouts, exit codes, patterns, retries per command in list
- ✅ **Type-Safe Configuration** — YAML validation prevents configuration errors
- ✅ **Security** — Commands executed without shell interpretation to prevent injection attacks

### Command Execution Limitations

Commands are executed **without shell interpretation** (`shell=False`) to prevent command injection attacks and improve security. This means **shell metacharacters are NOT evaluated**.

#### ❌ NOT Supported (Shell Features)

These patterns will **NOT work**:

```bash
# Pipes
"systemctl status nginx | grep active"

# Command substitution
"echo $(whoami)" or "echo `whoami`"

# Logical operators
"test -f /etc/file && echo yes"
"cmd1 || cmd2"

# Redirections
"ls > /tmp/output.log"
"cat < /etc/passwd"

# Bash-specific operators
"for i in {1..5}; do echo $i; done"

# Variable expansion
"echo $HOME"
"echo ${USER}_profile"

# Background processes
"long-running-cmd &"
```

**Why?** These features require shell interpretation. To prevent command injection vulnerabilities, commands run directly without a shell.

#### ✅ Supported

Simple commands with arguments work perfectly:

```bash
"systemctl is-active nginx"              # ✅ Works
"curl -s https://api.example.com/health" # ✅ Works
"grep ERROR /var/log/app.log"            # ✅ Works
"test -f /var/run/app.pid"               # ✅ Works
"/usr/local/bin/check-health.sh"         # ✅ Works
```

Quoted arguments are handled correctly:

```bash
"grep 'error pattern' /var/log/syslog"   # ✅ Works
'echo "hello world"'                      # ✅ Works
```

#### Handling Complex Commands

If you need commands that require shell features, wrap them in a shell script:

**Before (doesn't work):**
```yaml
cmdcheck:
  commands:
    - command: "systemctl status nginx | grep active"
```

**After (works):**

1. Create `/usr/local/bin/check-nginx.sh`:
```bash
#!/bin/bash
systemctl status nginx | grep active
```

2. Make it executable:
```bash
chmod 755 /usr/local/bin/check-nginx.sh
```

3. Update config:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: nginx_check
    type: cmdcheck
    command: "/usr/local/bin/check-nginx.sh"
    uptime_kuma:
      token: your-token
```

**Complex Example with Multiple Conditions:**

Script `/usr/local/bin/check-system-health.sh`:
```bash
#!/bin/bash

# Complex logic with pipes, conditions, etc.
if systemctl is-active nginx >/dev/null 2>&1; then
    NGINX_OK=1
else
    NGINX_OK=0
fi

if test -f /var/run/app.pid; then
    APP_OK=1
else
    APP_OK=0
fi

if [ $NGINX_OK -eq 1 ] && [ $APP_OK -eq 1 ]; then
    echo "All systems healthy"
    exit 0
else
    echo "System check failed: nginx=$NGINX_OK app=$APP_OK"
    exit 1
fi
```

Config:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: system_health
    type: cmdcheck
    command: "/usr/local/bin/check-system-health.sh"
    timeout: 10
    expect_exit_code: 0
    success_pattern: "All systems healthy"
    failure_pattern: "failed"
    uptime_kuma:
      token: your-token
```

### Configuration Reference

#### Always-List Structure

Commands are **always stored as a list**, even for a single command. This provides consistency and enables per-command configuration:

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: my-command
    type: cmdcheck
    command: "shell command to execute"    # Required: the actual shell command
    timeout: 30                            # Optional: per-command timeout (inherits from defaults if omitted)
    expect_exit_code: 0                    # Optional: per-command exit code (inherits from defaults if omitted)
    success_pattern: null                  # Optional: per-command success pattern
    failure_pattern: null                  # Optional: per-command failure pattern
    retry:
      attempts: 0                             # Optional: per-command retry attempts (inherits from defaults if omitted)
      delay_seconds: 0                        # Optional: per-command retry delay (inherits from defaults if omitted)
    uptime_kuma:
      token: "per-command-token"           # Optional: per-command token (overrides global token)
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
# Example 1: Single command (simplest form)
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: myapp-check
    type: cmdcheck
    command: "systemctl is-active myapp"
    expect_exit_code: 0
    timeout: 5
    uptime_kuma:
      token: your-token

# Example 2: Named single command
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_pid_file
    type: cmdcheck
    command: "test -f /var/run/app.pid"
    timeout: 5
    uptime_kuma:
      token: your-token

# Example 3: Log error detection (failure pattern)
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_logs
    type: cmdcheck
    command: "tail -n 500 /var/log/app.log"
    failure_pattern: "ERROR|CRITICAL|PANIC"
    timeout: 10
    uptime_kuma:
      token: your-token

# Example 4: Health endpoint with status line (success pattern)
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_health
    type: cmdcheck
    command: "curl -s http://localhost:8080/health"
    success_pattern: '"status":\s*"healthy"'
    timeout: 5
    uptime_kuma:
      token: your-token

# Example 5: Multiple independent checks
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: nginx
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: postgresql
    type: cmdcheck
    command: "systemctl is-active postgresql"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: app_health
    type: cmdcheck
    command: "curl -sf http://app.local/health"
    timeout: 5
    success_pattern: "OK"
    uptime_kuma:
      token: your-token

# Example 6: Per-command tokens (separate Uptime Kuma monitors)
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: web_server
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: database
    type: cmdcheck
    command: "systemctl is-active postgresql"
    timeout: 10
    uptime_kuma:
      token: "postgres-monitor-token"
  
  - name: app_process
    type: cmdcheck
    command: "test -f /var/run/app.pid"
    timeout: 5
    uptime_kuma:
      token: "app-monitor-token"
```

#### 9. Mixed Local + SSH Commands with Per-Command Tokens
```yaml
# Monitor services across multiple servers with individual monitors for critical services
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: "global-token"  # Used by checks that don't specify their own token

# Global SSH config (used by local commands)
ssh:
  host: infrastructure-server.local

checks:
  # Local critical services (individual monitors)
  - name: local_web
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    uptime_kuma:
      token: "web-monitor-token"

  - name: local_db
    type: cmdcheck
    command: "systemctl is-active postgresql"
    timeout: 15
    uptime_kuma:
      token: "database-monitor-token"

  # Remote critical services (per-command SSH + individual monitors)
  - name: remote_web
    type: cmdcheck
    command: "systemctl is-active apache2"
    timeout: 10
    ssh:
      host: web-server.prod.example.com
    uptime_kuma:
      token: "remote-web-monitor-token"

  - name: remote_db
    type: cmdcheck
    command: "systemctl is-active mysql"
    timeout: 15
    ssh:
      host: db-server.prod.example.com
      key_file: /etc/kuma-scout/prod_db_key
    uptime_kuma:
      token: "remote-db-monitor-token"

  # Backup verification (different SSH config + individual monitor)
  - name: backup_check
    type: cmdcheck
    command: "test -f /backups/latest.tar.gz"
    timeout: 30
    ssh:
      host: backup@nas.prod.example.com
      port: 2222
      key_file: /etc/kuma-scout/backup_key
    uptime_kuma:
      token: "backup-monitor-token"

  # Routine monitoring (uses global token)
  - name: log_directory
    type: cmdcheck
    command: "test -d /var/log"
    timeout: 5

  - name: system_load
    type: cmdcheck
    command: "uptime"
    timeout: 5

# Result: 5 individual alerts (web, db, remote-web, remote-db, backup) + 2 alerts to global monitor
# Checks with their own tokens send to individual monitors
# Checks without tokens (log_directory, system_load) send to the global monitor
```

### Use Cases

#### 1. Service Health Monitoring

Check if critical services are running:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: web_server
    type: cmdcheck
    command: "systemctl is-active nginx"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: database
    type: cmdcheck
    command: "systemctl is-active postgresql"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: cache
    type: cmdcheck
    command: "systemctl is-active redis-server"
    timeout: 10
    uptime_kuma:
      token: your-token
```

#### 2. Custom Health Endpoints

Monitor application health endpoints:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_health
    type: cmdcheck
    command: "curl -s http://localhost:8080/api/health"
    success_pattern: '"status":\s*"healthy"'
    timeout: 5
    uptime_kuma:
      token: your-token
```

#### 3. File Existence Checks

Alert if critical files are missing (multiple independent checks):
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_pid_file
    type: cmdcheck
    command: "test -f /var/run/app.pid"
    timeout: 5
    uptime_kuma:
      token: your-token
  
  - name: lock_file
    type: cmdcheck
    command: "test -f /var/spool/lock"
    timeout: 5
    uptime_kuma:
      token: your-token
  
  - name: config_file
    type: cmdcheck
    command: "test -f /etc/app/config.yaml"
    timeout: 5
    uptime_kuma:
      token: your-token
```

**Result**: DOWN if ANY file is missing, UP only if ALL files exist

#### 4. Disk Space Monitoring

Create a monitoring script:
```bash
# Script: /usr/local/bin/check-disk-space.sh
#!/bin/bash
AVAILABLE=$(df / | tail -1 | awk '{print $4}')
test "$AVAILABLE" -gt 5000000
```

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: disk_space
    type: cmdcheck
    command: "/usr/local/bin/check-disk-space.sh"
    timeout: 10
    uptime_kuma:
      token: your-token
```

#### 5. Log Pattern Detection

Alert on error patterns in logs:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_logs
    type: cmdcheck
    command: "journalctl -u myapp -n 1000 --no-pager"
    failure_pattern: "ERROR|CRITICAL|FATAL"
    success_pattern: "Running normally"
    timeout: 10
    uptime_kuma:
      token: your-token
```

#### 6. Database Connectivity

Verify database health:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: db_health
    type: cmdcheck
    command: "psql -h db.example.com -U monitoring -d health_check -c SELECT 1"
    expect_exit_code: 0
    timeout: 10
    uptime_kuma:
      token: your-token
```

#### 7. Custom Script Execution

Run custom monitoring scripts:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: custom_check
    type: cmdcheck
    command: "/usr/local/bin/custom-health-check.sh"
    success_pattern: "^HEALTHY"
    timeout: 30
    uptime_kuma:
      token: your-token
```

#### 8. ISP Speed Test Monitoring (Real-World Example)

Monitor your internet connection speed and alert when it drops below acceptable thresholds. This is a perfect example of using Kuma-Scout to monitor external service quality.

**CLI Examples:**
```bash
# Monitor download speed - alert if below 100 Mbit/s
kuma-scout cmdcheck "speedtest-cli --simple --no-upload" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-speedtest-token \
  --heartbeat-token your-heartbeat-token \
  --failure-pattern "Download: [0-9][0-9]\.[0-9][0-9] Mbit/s"

# Monitor upload speed - alert if below 50 Mbit/s  
kuma-scout cmdcheck "speedtest-cli --simple --no-download" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-upload-speedtest-token \
  --heartbeat-token your-heartbeat-token \
  --failure-pattern "Upload: [0-4][0-9]\.[0-9][0-9] Mbit/s"
```

**YAML Configuration (Recommended for production):**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

heartbeat:
  enabled: true
  uptime_kuma:
    token: your-heartbeat-token

checks:
  - name: download_speed_test
    type: cmdcheck
    command: 'speedtest-cli --simple --no-upload'
    failure_pattern: 'Download: [0-9][0-9]\.[0-9][0-9] Mbit/s'
    timeout: 300
    uptime_kuma:
      token: KumaScoutSpeedtestDownloadToken
  
  - name: upload_speed_test
    type: cmdcheck
    command: 'speedtest-cli --simple --no-download'
    failure_pattern: 'Upload: [0-4][0-9]\.[0-9][0-9] Mbit/s'
    timeout: 300
    uptime_kuma:
      token: KumaScoutSpeedtestUploadToken
```

**Alternative YAML Configuration (Combined Speed Test with Retries):**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

heartbeat:
  enabled: true
  uptime_kuma:
    token: your-heartbeat-token

checks:
  - name: internet_speed_test
    type: cmdcheck
    command: 'speedtest-cli --simple --secure'
    failure_pattern: '(Download:\ [0-4][0-9][0-9]\.[0-9][0-9]\ Mbit/s|Upload:\ [0-3][0-9][0-9]\.[0-9][0-9]\ Mbit/s)'
    timeout: 300
    retry:
      attempts: 3
      delay_seconds: 30
    uptime_kuma:
      token: KumaScoutSpeedtestCombinedToken
```

**Setup Requirements:**
1. Install `speedtest-cli`: `pip install speedtest-cli` or `apt install speedtest-cli`
2. Run initial test to ensure it works: `speedtest-cli --simple`
3. Adjust failure patterns based on your acceptable minimum speeds
4. Schedule via cron: `*/30 * * * * /usr/local/bin/kuma-scout run /etc/kuma-scout/config.yaml`

**Pattern Explanation:**
- `Download: [0-9][0-9]\.[0-9][0-9] Mbit/s` matches download speeds below 100 Mbit/s (00.00-99.99)
- `Upload: [0-4][0-9]\.[0-9][0-9] Mbit/s` matches upload speeds below 50 Mbit/s (00.00-49.99)
- Combined pattern `(Download:\ [0-4][0-9][0-9]\.[0-9][0-9]\ Mbit/s|Upload:\ [0-3][0-9][0-9]\.[0-9][0-9]\ Mbit/s)` matches download speeds below 500 Mbit/s OR upload speeds below 400 Mbit/s in a single test

**Result:** Uptime Kuma will show DOWN status and alert when your internet speed drops below the configured thresholds for more than ~90 seconds (accounting for retries), helping you identify ISP issues or network problems while avoiding false alerts from transient speed fluctuations.

### Security Considerations

**For comprehensive security guidance, see [SECURITY.md](SECURITY.md)**

This configuration guide focuses on the configuration aspects of security. For detailed information on:
- Attack vectors and mitigations
- Dangerous command pattern detection
- Safe vs dangerous monitoring patterns
- Sudoers configuration examples
- SSH key and config file permission validation
- Best practices for command design and network security

See the [Security Guide](SECURITY.md).

---

## Kopia Snapshot Monitoring (kopiasnapshotstatus)

Monitor backup snapshot age and alert when backups are stale.

### Quick Start

#### Configuration File (YAML)
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: data_backup
    type: kopiasnapshotstatus
    path: /data
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: backup_snapshot
    type: kopiasnapshotstatus
    path: /backups
    max_age_hours: 48
    uptime_kuma:
      token: your-kopia-token
  
  - name: remote_backup
    type: kopiasnapshotstatus
    path: root@fileserver:/mnt/shares
    # Uses default max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
```

### Command Line
```bash
# Single snapshot
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  /data
```

### Authentication Token

Use environment variable expansion in YAML config or CLI:

```bash
# In YAML config
uptime_kuma:
  token: ${MY_KOPIA_TOKEN}

# Or on CLI
export MY_KOPIA_TOKEN=your-kopia-token
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_KOPIA_TOKEN}" \
  /data
```

## Key Features

- ✅ **Per-path thresholds** — Each snapshot can have different age requirements
- ✅ **Global fallback** — Paths without explicit threshold use global default
- ✅ **SSH support** — Handles remote paths like `user@host:/path`
- ✅ **Path validation** — Prevents path traversal and command injection attacks
- ✅ **CLI override** — CLI `--snapshot` flags replace YAML config entirely
- ✅ **Type-safe** — Structured YAML format prevents configuration errors
- ✅ **Multi-source config** — Load from YAML files, environment variables, or CLI arguments

## Configuration Reference

### Structure
```
uptime_kuma:
  url: <string>      # Uptime Kuma push API URL

checks:
  - name: <string>   # Required: unique check name
    type: kopiasnapshotstatus
    path: <string>   # Required: snapshot path (local or remote)
    max_age_hours: <int>  # Optional: max age hours (default: 24)
    uptime_kuma:
      token: <string> # Optional: override global token
```

### Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):
1. **CLI arguments** - Command-line options (highest priority)
2. **YAML file** - Configuration from config file
3. **Defaults** - Built-in defaults (max_age_hours: 24)

### YAML Configuration

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: data_backup
    type: kopiasnapshotstatus
    path: /data
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: backup_snapshot
    type: kopiasnapshotstatus
    path: /backups
    max_age_hours: 48
    uptime_kuma:
      token: your-kopia-token
```

### Authentication Token

Use environment variable expansion in YAML config or CLI:

```bash
# In YAML config
uptime_kuma:
  token: ${MY_KOPIA_TOKEN}

# Or on CLI
export MY_KOPIA_TOKEN=your-kopia-token
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_KOPIA_TOKEN}" \
  /data
```

### CLI Arguments

```bash
# Single snapshot with default max age (24 hours)
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  /data

# Single snapshot with custom max age
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  --max-age-hours 48 \
  /data

# Single snapshot with heartbeat
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  --heartbeat-token your-heartbeat-token \
  /data

# Multiple snapshots (not supported in CLI - use config file)

# Single snapshot with custom age threshold
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  /data

# With heartbeat
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  --heartbeat-token your-heartbeat-token \
  /data
  --token your-kopia-token \
  --max-age-hours 24
```

**Note:** Snapshot format supports two options:
- With hours: `--snapshot path,hours` (e.g., `/data,24`)
- Without hours: `--snapshot path` (uses `--max-age-hours` value or hardcoded default 24)

### Path Validation & Security

Snapshot paths are validated to prevent path traversal and command injection attacks.

**Allowed path formats:**
- ✅ Local paths: `/mnt/data`, `./backup`, `~/snapshots`
- ✅ SSH paths: `user@host:/path`, `root@server.com:/mnt/backups`
- ✅ Valid characters: alphanumerics, hyphens, underscores, dots, forward slashes, tildes

**Blocked patterns:**
- ❌ Path traversal: `../../../etc/passwd`
- ❌ Command injection: `; rm -rf /`, `| cat`, `&& echo`, `` `whoami` ``, `$(whoami)`
- ❌ Dangerous characters: `!`, `*`, `?`, `$`, `` ` ``, `;`, `|`, `&`, `(`, `)`, `<`, `>`

If an invalid path is detected, the snapshot check fails with a security error:
```
❌ Invalid snapshot path configuration: Invalid snapshot path format: /data; rm -rf /
```

This validation is performed both at configuration load time and during execution.

## Examples

### Local paths with different thresholds:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: data_backup
    type: kopiasnapshotstatus
    path: /data
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: backups
    type: kopiasnapshotstatus
    path: /var/backups
    max_age_hours: 48
    uptime_kuma:
      token: your-kopia-token
  
  - name: archive
    type: kopiasnapshotstatus
    path: /archive
    max_age_hours: 168  # Weekly
    uptime_kuma:
      token: your-kopia-token
```

**Mixed local and remote paths:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: local_backup
    type: kopiasnapshotstatus
    path: /local/backup
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: remote_snapshots
    type: kopiasnapshotstatus
    path: backup.example.com:/remote/snapshots
    max_age_hours: 48
    uptime_kuma:
      token: your-kopia-token
  
  - name: nas_backup
    type: kopiasnapshotstatus
    path: root@nas:/volume1/backup
    max_age_hours: 72
    uptime_kuma:
      token: your-kopia-token
```

**Using global default:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: data_backup
    type: kopiasnapshotstatus
    path: /data
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: backups
    type: kopiasnapshotstatus
    path: /backups
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
  
  - name: archive
    type: kopiasnapshotstatus
    path: /archive
    max_age_hours: 24
    uptime_kuma:
      token: your-kopia-token
```

## CLI Usage

### Single snapshot
```bash
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  /data
```

### Multiple snapshots
```bash
# Multiple snapshots not supported in CLI - use config file
```

### Quick CLI Check

```bash
kuma-scout kopiasnapshotstatus /data \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token
```

### With full Uptime Kuma integration

```bash
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  --heartbeat-token your-heartbeat-token \
  /data
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
hatch run test tests/test_config_loading.py::test_yaml_preserved_when_typer_empty_list_provided -v
hatch run test tests/checkers/test_kopia_snapshot_checker.py::TestKopiaSnapshotChecker -v
```

## Troubleshooting

**Q: Can I omit hours for some snapshot paths?**
A: Yes! Use `--snapshot path` (without hours) to use the global `--max-age-hours` value. Example: `--snapshot /data` with `--max-age-hours 24`

**Q: How do I mix paths with and without explicit hours?**
A: Just provide them as separate arguments. Example: `--snapshot /data --snapshot /backups,48 --max-age-hours 24` (/data uses 24h, /backups uses 48h)

**Q: Do CLI flags merge with YAML config?**
A: No. CLI `--snapshot` flags **replace** the YAML config entirely.

**Q: How does it handle SSH paths with multiple colons?**
A: The parser splits on the **rightmost** space between PATH and MAX_AGE_HOURS, so `user@host:/path@24` works correctly. For paths without hours, use `user@host:/path` with `--max-age-hours`.

**Q: Can I set max_age_hours to 0?**
A: Yes, but snapshots must be fresher than 0 hours (essentially never allowed). Use with caution.

---

# Port Scan Configuration Guide

## Quick Start

### Configuration File (YAML)
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: network_scan
    type: portscan
    targets: ["192.168.1.0/24"]
    ports: "1-1000"
    exclude: ["192.168.1.1", "192.168.1.254"]
    timing: "T3"
    uptime_kuma:
      token: your-portscan-token
```

### Command Line
```bash
# Basic port scan
export MY_PORTSCAN_TOKEN=your-token
kuma-scout portscan \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_PORTSCAN_TOKEN}" \
  192.168.1.0/24

# With custom ports and timing
kuma-scout portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_PORTSCAN_TOKEN}" \
  192.168.1.0/24
```

### Authentication Token

Use variable expansion in YAML config or CLI:

```bash
# In YAML
uptime_kuma:
  token: ${MY_PORTSCAN_TOKEN}

# Or on CLI
export MY_PORTSCAN_TOKEN=your-portscan-token
kuma-scout portscan \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_PORTSCAN_TOKEN}" \
  192.168.1.0/24
```

## Configuration Reference

### YAML Structure
```yaml
uptime_kuma:
  url: <string>                 # Uptime Kuma push API URL

checks:
  - name: <string>              # Required: unique check name
    type: portscan
    targets: [<range-list>]     # Required: IP ranges to scan (e.g., ["192.168.1.0/24"])
    ports: <port-spec>          # Optional: Port range (default: "1-1000")
    exclude: [<ip-list>]        # Optional: IPs to exclude from scan
    timing: <T0-T5>             # Optional: Timing profile (default: "T3")
    timeout: <int>              # Optional: Timeout in seconds (default: 3600)
    arguments: <string>         # Optional: Additional nmap arguments
    keep_xml: <bool>            # Optional: Keep XML output file (default: false)
    uptime_kuma:
      token: <string>           # Optional: override global token
```



```bash
# Single IP range
kuma-scout portscan \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
  192.168.1.0/24

# Multiple IP ranges
kuma-scout portscan \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
  192.168.1.0/24 \
  10.0.0.0/8

# With custom ports
kuma-scout portscan \
  --ports 22,80,443 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
  192.168.1.0/24

# With exclusions
kuma-scout portscan \
  --exclude 192.168.1.1 \
  --exclude 192.168.1.254 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
  192.168.1.0/24

# With nmap timing
kuma-scout portscan \
  --timing T4 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
  192.168.1.0/24
  --timing T4 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token

# All options combined
kuma-scout portscan \
  --ports 1-10000 \
  --timing T4 \
  --exclude 192.168.1.1 \
  --exclude 192.168.1.254 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-portscan-token \
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
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: network-scan-basic
    type: portscan
    ports: 1-1000
    ip_ranges:
      - 192.168.1.0/24
    token: ${UPTIME_KUMA_TOKEN}
```

### Multi-range scan with exclusions
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: network-scan-multi
    type: portscan
    ports: 22,80,443,3306,3389
    exclude:
      - 192.168.1.1
      - 192.168.1.254
    ip_ranges:
      - 192.168.1.0/24
      - 10.0.0.0/8
    nmap_timing: T4
    token: ${UPTIME_KUMA_TOKEN}
```

### Fast scan with custom arguments
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: network-scan-fast
    type: portscan
    ports: 1-65535
    ip_ranges:
      - 192.168.100.0/24
    nmap_timing: T5
    nmap_arguments:
      - --script vuln
      - --min-rate 1000
    token: ${UPTIME_KUMA_TOKEN}
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
A: Yes, set `keep_xml_output: true` in the YAML config file.

---

# ZFS Pool Status Configuration Guide

## Quick Start

### Configuration File (YAML)
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: tank_pool
    type: zfspoolstatus
    pool: tank
    min_free_percent: 10
    uptime_kuma:
      token: your-zfs-token
  
  - name: backup_pool
    type: zfspoolstatus
    pool: backup
    min_free_percent: 20
    uptime_kuma:
      token: your-zfs-token
  
  - name: archive_pool
    type: zfspoolstatus
    pool: archive
    # Uses default min_free_percent: 10
    uptime_kuma:
      token: your-zfs-token
```

### Command Line
```bash
# Monitor single pool with default threshold (10%)
export MY_ZFS_TOKEN=your-zfs-token
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_ZFS_TOKEN}" \
  tank

# Monitor single pool with custom threshold
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_ZFS_TOKEN}" \
  --min-free-percent 20 \
  tank
```

### Authentication Token

Use variable expansion in YAML config or CLI:

```bash
# In YAML
uptime_kuma:
  token: ${MY_ZFS_TOKEN}

# Or on CLI
export MY_ZFS_TOKEN=your-zfs-token
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token "${MY_ZFS_TOKEN}" \
  tank
```

## Key Features

- ✅ **Per-pool thresholds** — Each pool can have different minimum free space requirements
- ✅ **Global fallback** — Pools without explicit threshold use global default (10% by default)
- ✅ **Health monitoring** — Detects unhealthy pools (DEGRADED, FAULTED, OFFLINE)
- ✅ **Individual failures** — One failing pool doesn't prevent checking others
- ✅ **CLI override** — CLI `--pool` flags replace YAML config entirely
- ✅ **Type-safe** — Structured YAML format prevents configuration errors

## Configuration Reference

### Structure
```
uptime_kuma:
  url: <string>                   # Uptime Kuma push API URL

checks:
  - name: <string>                # Required: unique check name
    type: zfspoolstatus
    pool: <string>                # Required: pool name (e.g., "tank")
    min_free_percent: <int>       # Optional: min free space % (default: 10)
    uptime_kuma:
      token: <string>             # Optional: override global token
```



```bash
# Single pool with default threshold (10%)
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token \
  tank

# Single pool with custom threshold
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token \
  --min-free-percent 20 \
  tank

# Multiple pools (not supported in CLI - use config file)
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token

# Multiple pools with custom global default
kuma-scout zfspoolstatus \
  --pool tank \
  --pool backup,20 \
  --pool archive,30 \
  --min-free-percent 15 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token

# With config file
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-zfs-token \
  tank

# Override global default with CLI
kuma-scout zfspoolstatus \
  --min-free-percent 15 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token \
  tank
```

**Note:** Pool format supports two options:
- With percent: `--pool name,percent` (e.g., `tank,10`)
- Without percent: `--pool name` (uses `--min-free-percent` value or default 10)

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
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: zfs-tank
    type: zfspoolstatus
    pools:
      - name: tank
    free_space_percent_default: 10
    token: ${UPTIME_KUMA_TOKEN}
```

### Multiple pools with different thresholds
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: zfs-pools-multi
    type: zfspoolstatus
    pools:
      - name: tank
        free_space_percent_min: 10      # Critical: needs 10% free
      - name: backup
        free_space_percent_min: 20      # Important: needs 20% free
      - name: archive
        free_space_percent_min: 30      # Archive: more relaxed
    free_space_percent_default: 10
    token: ${UPTIME_KUMA_TOKEN}
```

### Mix pools with and without explicit thresholds
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: zfs-pools-mixed
    type: zfspoolstatus
    pools:
      - name: tank
        free_space_percent_min: 10
      - name: backup                   # Uses global default (15%)
      - name: archive                  # Uses global default (15%)
    free_space_percent_default: 15
    token: ${UPTIME_KUMA_TOKEN}
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

**Q: Can I omit the percent threshold for some pools?**
A: Yes! Use `--pool name` (without percent) to use the global `--min-free-percent` value. Example: `--pool tank` with `--min-free-percent 10`

**Q: How do I mix pools with and without explicit thresholds?**
A: Just provide them as separate arguments. Example: `--pool tank --pool backup,20 --min-free-percent 10` (tank uses 10%, backup uses 20%)

**Q: Do CLI flags merge with YAML config?**
A: No. CLI `--pool` flags **replace** the YAML config entirely.

**Q: What if a pool doesn't exist?**
A: The command reports it as a failed pool and returns DOWN status.

**Q: Can I set free_space_percent to 0?**
A: Yes, but pools must have >0% free space. A value of 0 means the pool must never be completely full.

---

## Shared Configuration

All commands support these shared settings:

### Authentication Tokens (Variable Expansion Support)

All configuration values support environment variable expansion using `${VARIABLE_NAME}` syntax. This includes tokens, URLs, file paths, SSH passwords, and any other configuration setting.

**Example - In YAML config (all values can use expansion):**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${MY_UPTIME_KUMA_TOKEN}  # Any variable name you choose

heartbeat:
  enabled: true
  token: ${MY_HEARTBEAT_TOKEN}    # Any variable name you choose

ssh:
  key_file: ${SSH_KEY_PATH}       # Paths support expansion too
  password: ${SSH_PASSWORD}       # So do sensitive values
```

**Example - On CLI:**
```bash
export MY_TOKEN=my-secure-token
export MY_HEARTBEAT=heartbeat-token

kuma-scout run config.yaml \
  --token "${MY_TOKEN}" \
  --heartbeat-token "${MY_HEARTBEAT}"
```

**Or in YAML:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}

heartbeat:
  enabled: true
  interval: 300

checks:
  - name: heartbeat-check
    type: cmdcheck
    command: "echo heartbeat"
    token: ${HEARTBEAT_TOKEN}

  - name: nginx-check
    type: cmdcheck
    command: "systemctl is-active nginx"
    token: ${CMDCHECK_TOKEN}

  - name: network-scan
    type: portscan
    ports: 80,443,22
    ip_ranges:
      - 192.168.1.0/24
    token: ${PORTSCAN_TOKEN}

  - name: backup-check
    type: kopiasnapshotstatus
    paths:
      - /data/backups
    token: ${KOPIASNAPSHOTSTATUS_TOKEN}

  - name: pool-check
    type: zfspoolstatus
    pools:
      - name: tank
    token: ${ZFSPOOLSTATUS_TOKEN}
```

### Environment Variable Expansion in YAML

Kuma Scout supports environment variable expansion directly in YAML configuration files using `${VAR_NAME}` syntax. This allows you to reference environment variables for tokens without hardcoding sensitive information.

**Supported Syntax:**
- `${VAR_NAME}` - Expands to the value of environment variable `VAR_NAME`
- `$VAR_NAME` - Alternative syntax (without braces)

**Examples:**
```yaml
# Global tokens
uptime_kuma:
  url: http://uptimekuma:3001/api/push

heartbeat:
  uptime_kuma:
    token: "${HEARTBEAT_TOKEN}"  # Expands to env var HEARTBEAT_TOKEN

checks:
  - name: web_server
    type: cmdcheck
    command: "systemctl is-active nginx"
    uptime_kuma:
      token: "${WEB_TOKEN}"    # Per-command token expansion
  
  - name: database
    type: cmdcheck
    command: "systemctl is-active postgresql"
    uptime_kuma:
      token: "${DB_TOKEN}"     # Different token for database
```

**Environment Setup:**
```bash
export HEARTBEAT_TOKEN=abc123def456
export WEB_TOKEN=web_monitor_token
export DB_TOKEN=db_monitor_token
```

**Error Handling:**
- If a referenced environment variable is not set, configuration loading will fail with a clear error message
- This prevents silent failures where tokens would be undefined

**Security Benefits:**
- Avoid storing sensitive tokens in configuration files
- Tokens can be managed via environment variables, secret managers, or CI/CD systems
- Configuration files can be committed to version control without exposing secrets

**Note:** Environment variable expansion is only supported for token fields. Other configuration values must still use YAML literals or CLI arguments.

### Logging
```yaml
logging:
  log_file: /var/log/kuma-scout.log
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**CLI Options:**
```bash
# Set log level via CLI
kuma-scout run config.yaml --log-level DEBUG

# Set log file via CLI
kuma-scout run config.yaml --log-file /var/log/custom.log
```

**Note:** Logging configuration supports variable expansion (e.g., `${LOG_LEVEL}`) in YAML files.

### Heartbeat (Uptime Kuma monitoring)
```yaml
heartbeat:
  enabled: true
  interval: 300              # seconds
  uptime_kuma:
    token: your-heartbeat-token
```

**CLI Options:**
```bash
# Enable heartbeat with custom token via CLI
kuma-scout run config.yaml --heartbeat-token your-heartbeat-token
```

**Note:** Enable/disable and interval settings can only be configured via YAML files, but the heartbeat token can be overridden via CLI `--heartbeat-token`.

### Uptime Kuma URL
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: your-uptime-kuma-token
```

**CLI Options:**
```bash
# Override URL and token via CLI
kuma-scout run config.yaml \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-uptime-kuma-token
```

**Note:** Both the URL and token can be configured via YAML file or overridden via CLI arguments `--uptime-kuma-url` and `--token`.

## Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):

1. **CLI arguments** - Command-line flags (highest priority)
2. **YAML file** - Configuration from config file passed to `run` command
3. **Defaults** - Built-in default values (lowest priority)

**Variable Expansion:** All configuration values support `${VAR}` syntax for environment variable expansion. Use any variable name you choose.

**Loading order in code:**
```
Defaults (in __init__)
  ↓
YAML file (load_from_yaml, with ${VAR} expansion for all values)
  ↓
CLI arguments (load_from_args, with ${VAR} expansion for all values) ← Final value wins
```

**Note:** Each layer completely replaces the previous one—values don't merge.

### Example Priority

Given these configurations:

```yaml
# config.yaml (YAML file - second highest)
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: network-scan
    type: portscan
    ports: 1-1000
    ip_ranges:
      - 192.168.1.0/24
    token: ${UPTIME_KUMA_TOKEN}
```

```bash
# CLI argument (highest priority - takes final effect)
kuma-scout portscan --ports 1-65535
```

**Result:** Scans ports `1-65535` (CLI argument wins)

If you remove the CLI argument:
```bash
kuma-scout portscan
# Result: Scans ports 1-1000 (YAML file wins)
```

---

