# Configuration Guide for Kuma Scout

**Upgrading from a previous version?** See [MIGRATION.md](MIGRATION.md) for breaking changes and migration instructions between versions.

## Overview: How Configuration Works

Kuma Scout supports multiple configuration sources that work together with a clear priority order. This flexibility allows you to:
- Store sensitive authentication tokens in environment variables
- Use YAML files for detailed, reusable configurations
- Override settings via command-line arguments for one-off executions

**Important:** Only authentication tokens (variables ending in `_TOKEN`) are supported via environment variables. All other configuration must use YAML files or CLI arguments.

### Configuration Priority (Highest to Lowest)

1. **CLI Arguments** - Command-line flags override everything
2. **YAML Config File** - Settings in `/etc/kuma-scout/config.yaml` (or custom path via `--config`)
3. **Token Environment Variables** - Authentication tokens prefixed with `KUMA_SCOUT_*_TOKEN`
4. **Hardcoded Defaults** - Built-in fallback values

This means if you set a value in multiple places, CLI arguments win, followed by YAML, then token environment variables.

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
- Override location: `kuma-scout COMMAND --config /path/to/config.yaml`

**Method 2: Token Environment Variables (For authentication tokens only)**
- Secure token storage
- CI/CD friendly
- Container-friendly (no files to mount)
- All token variables suffixed with `_TOKEN`

**Method 3: CLI Arguments (Recommended for testing/one-off runs)**
- Quick testing and debugging
- No files needed
- Perfect for cron jobs with inline parameters

**Method 4: Defaults**
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

**Important:** SSH settings are NOT supported via environment variables. Use CLI args or YAML config. Environment variables are reserved for tokens and passwords only.

### Global CLI Options

All commands support these common CLI options for configuration:

```bash
# Core configuration
--config /etc/kuma-scout/config.yaml          # YAML config file path
--uptime-kuma-url http://uptimekuma:3001/api/push  # Uptime Kuma API URL
--heartbeat-token your-heartbeat-token        # Heartbeat token
--token your-command-token                    # Command-specific token

# Retry configuration
--retry-count 3                               # Number of retry attempts (default: 0)
--retry-delay 5                               # Delay in seconds between retries (default: 0)

# SSH remote execution
--ssh user@host                               # SSH connection string
--ssh-key-file /path/to/key                    # SSH private key path
--ssh-password your-password                  # SSH password (discouraged)
--ssh-strict-host-key-checking/--ssh-no-strict-host-key-checking  # Host key checking

# Logging
--log-file /var/log/kuma-scout.log            # Log file path
--log-level INFO                              # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

# Development
--ignore-file-permissions                     # Skip config and key file permission validation
```

**Example with retry options:**
```bash
kuma-scout cmdcheck "curl -s https://api.example.com/health" \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-token \
  --retry-attempts 3 \
  --retry-delay-seconds 5
```

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

#### Multiple Commands - All Must Pass

**YAML Configuration (Multiple Commands):**
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

**Result**: DOWN if ANY command fails, UP only if ALL succeed. Individual commands with per-token configuration send separate push notifications to their respective Uptime Kuma monitors, plus an aggregated push to the global monitor if configured.

**CLI Limitation**: CLI only supports single commands. For multiple commands, use YAML configuration as shown above.

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

**Environment Variable:**
```bash
KUMA_SCOUT_CMDCHECK_TOKEN=your-cmdcheck-token
```

**Or in YAML:**
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
- ✅ **Multiple Commands** — Run multiple independent checks (via YAML), all must pass for UP
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

# Example 5: Multiple independent checks (all must pass)
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

# Example 7: Mixed Local + SSH Commands with Per-Command Tokens
# Monitor services across multiple servers with individual monitors for critical services
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: "infrastructure-aggregate-token"  # For aggregated results

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

  # Routine monitoring (no individual alerts, only aggregated)
  - name: log_directory
    type: cmdcheck
    command: "test -d /var/log"
    timeout: 5

  - name: system_load
    type: cmdcheck
    command: "uptime"
    timeout: 5

# Result: 5 individual alerts (web, db, remote-web, remote-db, backup) + 1 aggregated alert
# Routine checks (disk_space, system_load) only appear in aggregated results
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
4. Schedule via cron: `*/30 * * * * /usr/local/bin/kuma-scout run --config /etc/kuma-scout/config.yaml`

**Pattern Explanation:**
- `Download: [0-9][0-9]\.[0-9][0-9] Mbit/s` matches download speeds below 100 Mbit/s (00.00-99.99)
- `Upload: [0-4][0-9]\.[0-9][0-9] Mbit/s` matches upload speeds below 50 Mbit/s (00.00-49.99)
- Combined pattern `(Download:\ [0-4][0-9][0-9]\.[0-9][0-9]\ Mbit/s|Upload:\ [0-3][0-9][0-9]\.[0-9][0-9]\ Mbit/s)` matches download speeds below 500 Mbit/s OR upload speeds below 400 Mbit/s in a single test

**Result:** Uptime Kuma will show DOWN status and alert when your internet speed drops below the configured thresholds for more than ~90 seconds (accounting for retries), helping you identify ISP issues or network problems while avoiding false alerts from transient speed fluctuations.

### Security Considerations

⚠️ **SECURITY FIRST**: Kuma Scout is designed with security as a primary concern.

#### Command Execution Security

Commands are executed **without shell interpretation** (`shell=False`) to prevent command injection vulnerabilities. This means:

- ✅ Shell metacharacters cannot be injected through input
- ✅ Safe against semicolon-separated command chaining
- ✅ Safe against pipe injection attacks
- ✅ Safe against command substitution attacks

#### Configuration Security

Kuma Scout assumes **configuration is admin-controlled** (YAML files, CLI arguments, environment variables are set by administrators only).

If you need complex shell logic:
1. Create a dedicated shell script (stored securely with 755 permissions)
2. Call the script from your configuration
3. Keep the script under version control with your infrastructure code

This separates data (configuration) from logic (scripts) and enables proper code review and auditing.

#### Attack Vectors & Mitigations

| Vector | Risk | Mitigation |
|--------|------|-----------|
| Config File Tampering | Malicious commands in config | File permissions (600), access control |
| PATH Manipulation | Malicious binary substitution | Use absolute paths; dedicated service user |
| Privilege Escalation | Commands running as root | Run as dedicated low-privilege user |
| Resource Exhaustion | Fork bombs, infinite loops | Timeout (default 30s) + cgroup limits |
| Output Leakage | Sensitive data in command output | Output truncated to 500 chars; sanitize scripts |

#### Dangerous Command Pattern Detection

Kuma Scout monitors for and **warns about dangerous commands** that could modify system state when executed with elevated privileges (via sudo). This is a **non-blocking security feature** that helps prevent accidental or malicious system modifications.

**Detection is automatic** - dangerous patterns trigger warning messages in logs but commands still execute. This allows administrators to review and audit commands while maintaining operational continuity.

**Commands that trigger warnings:**

| Category | Tools | Examples |
|----------|-------|----------|
| **Package Managers** | `apt`, `apt-get`, `yum`, `dnf`, `pacman`, `brew`, `pip`, `npm`, `gem`, `cargo` | Installing/removing/upgrading packages |
| **System Services** | `systemctl`, `service` | Starting, stopping, restarting, enabling/disabling services |
| **File System** | `rm`, `mkfs`, `dd`, `fdisk`, `parted` | Deleting files, formatting disks, modifying partitions |
| **User Management** | `useradd`, `userdel`, `usermod`, `passwd`, `chmod`, `chown` | Creating/modifying users, changing permissions |
| **System Control** | `reboot`, `shutdown`, `halt`, `poweroff` | Shutting down or rebooting the system |
| **Process Management** | `kill`, `killall` | Terminating processes |
| **ZFS Storage** | `zpool`, `zfs` | Creating/destroying pools or datasets, snapshots, rollbacks |

**Example Warning Messages:**

```
⚠️  Command 'check_nginx' may modify system state: systemctl start detected. Ensure this is authorized and runs with read-only intent.
⚠️  Command 'update_packages' may install/remove packages: apt install detected. Ensure this is authorized and runs with read-only intent.
⚠️  Command 'cleanup' may delete files: rm detected. Ensure this is authorized and runs with read-only intent.
```

**Recommended Sudoers Configuration**

Only grant sudo access to **read-only** commands that your monitoring actually needs:

```sudoers
# /etc/sudoers.d/kuma-scout
# Allow monitoring user to check service status (read-only)
kuma-scout ALL=(root) NOPASSWD: /usr/bin/systemctl status *
kuma-scout ALL=(root) NOPASSWD: /usr/bin/systemctl is-active *

# Allow checking ZFS pool status (read-only)
kuma-scout ALL=(root) NOPASSWD: /usr/sbin/zpool list
kuma-scout ALL=(root) NOPASSWD: /usr/sbin/zpool status

# Do NOT grant write permissions to ANY tools
# ❌ AVOID: kuma-scout ALL=(root) NOPASSWD: /usr/bin/systemctl *  (too broad)
# ❌ AVOID: kuma-scout ALL=(root) NOPASSWD: /usr/bin/apt *        (package manager)
# ❌ AVOID: kuma-scout ALL=(root) NOPASSWD: /bin/rm *             (destructive)
```

**Safe Monitoring Patterns:**

✅ **Good - Read-only checks:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: nginx_status
    type: cmdcheck
    command: "systemctl is-active nginx"        # Status check
    uptime_kuma:
      token: your-token
  
  - name: app_pid_check
    type: cmdcheck
    command: "test -f /var/run/app.pid"         # File existence
    uptime_kuma:
      token: your-token
  
  - name: disk_usage
    type: cmdcheck
    command: "/usr/local/bin/check-disk-usage.sh" # Disk usage
    uptime_kuma:
      token: your-token
  
  - name: zfs_pool_status
    type: cmdcheck
    command: "zpool status tank"                # ZFS pool status
    uptime_kuma:
      token: your-token
  
  - name: app_health
    type: cmdcheck
    command: "curl -s http://app:8080/health"   # Health endpoint
    uptime_kuma:
      token: your-token
```

❌ **Dangerous - System modification:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: nginx_restart
    type: cmdcheck
    command: "systemctl restart nginx"          # Modifies service
    uptime_kuma:
      token: your-token
  
  - name: package_update
    type: cmdcheck
    command: "apt update && apt upgrade"        # Installs packages
    uptime_kuma:
      token: your-token
  
  - name: cleanup_cache
    type: cmdcheck
    command: "rm -rf /tmp/cache"                # Deletes files
    uptime_kuma:
      token: your-token
  
  - name: destroy_zfs_pool
    type: cmdcheck
    command: "zpool destroy tank"               # Destroys storage
    uptime_kuma:
      token: your-token
  
  - name: system_reboot
    type: cmdcheck
    command: "reboot"                           # Reboots system
    uptime_kuma:
      token: your-token
```

**Best Practices:**

1. **Use Read-Only Commands** - Prefer checking status/health instead of modifying systems
2. **Grant Minimal Sudo** - Only grant access to specific commands you actually need
3. **Use Full Paths** - Always specify absolute paths (e.g., `/usr/bin/systemctl`) in sudoers
4. **Enable Audit Logging** - Configure sudo to log all executed commands:
   ```sudoers
   Defaults logfile=/var/log/sudo.log
   ```
5. **Monitor Warning Messages** - Check logs regularly for dangerous command warnings
6. **Test in Non-Production** - Always test your monitoring setup in a non-production environment first

#### Configuration File Permission Validation

Kuma Scout **enforces** that your configuration file has **restricted permissions (0o600)** to prevent unauthorized access to sensitive tokens and credentials.

**What it checks:**
- Config file should only be readable/writable by its owner
- Typical location: `/etc/kuma-scout/config.yaml` (owner: kuma-scout)
- Restrictive permissions prevent other users from reading your Uptime Kuma tokens

**If validation fails**, execution **BLOCKS** with an error:
```
❌ Security check failed: Config file /etc/kuma-scout/config.yaml has overly permissive mode 0o644.
Recommended: 0o600. Run: chmod 600 /etc/kuma-scout/config.yaml
To bypass this check, use --ignore-file-permissions flag or set logging.ignore_file_permissions: true in config.
```

**To bypass this check** (development or testing only):
```bash
# Using CLI flag
kuma-scout cmdcheck --ignore-file-permissions --config ./config.yaml

# Using YAML configuration
logging:
  ignore_file_permissions: true
```

⚠️ **Security Note**: Only bypass this check during development or testing. Always ensure production configurations have proper permissions (0o600). A config file with world-readable permissions exposes your Uptime Kuma authentication tokens.

#### SSH Security

When using SSH remote execution (`--ssh` option), Kuma Scout enforces security best practices:

**Host Key Verification:**
- Strict host key checking is **enabled by default** (`StrictHostKeyChecking=yes`)
- This prevents MITM attacks by verifying the remote host's identity
- Host keys must be in `~/.ssh/known_hosts` before connecting

**To bypass host key checking** (development/testing only):
```bash
kuma-scout cmdcheck \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-uptime-kuma-token \
  --ssh root@dev-server \
  --ssh-no-strict-host-key-checking \
  "uptime"
```

⚠️ **Warning**: Disabling host key checking makes you vulnerable to MITM attacks. Never use in production.

**SSH Key File Permissions:**
- SSH private key files must have **restricted permissions (0o600)**
- Kuma Scout validates key file permissions before use
- This prevents unauthorized users from reading your private keys

**If validation fails**, execution **BLOCKS** with an error:
```
❌ Security check failed: SSH key file /root/.ssh/id_rsa has overly permissive mode 0o644.
Recommended: 0o600. Run: chmod 600 /root/.ssh/id_rsa
To bypass this check, use --ignore-file-permissions flag.
```

**To bypass SSH key permission validation** (development/testing only):
```bash
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-uptime-kuma-token \
  --ssh root@backup-server \
  --ssh-key-file /shared/key \
  --ignore-file-permissions \
  /data
```

Note: The `--ignore-file-permissions` flag applies to both config files and SSH key files.

**SSH Authentication Methods:**

1. **SSH Key (Recommended)** - Most secure, no passwords in config:
   ```yaml
   ssh:
     connection: "root@backup-server"        # SSH connection string
     key_file: /root/.ssh/id_rsa             # Path to SSH private key
   ```

2. **SSH Password (Discouraged)** - Use only when keys are not possible:
   ```yaml
   ssh:
     connection: "admin@legacy-server"       # SSH connection string
     password: "${SSH_PASSWORD}"             # SSH password (use env var)
   ```
   ⚠️ Passwords are less secure than keys and may appear in process lists.

**SSH Best Practices:**
- ✅ Use SSH keys instead of passwords
- ✅ Keep private keys in `~/.ssh/` with 600 permissions
- ✅ Use a dedicated SSH key pair for monitoring (not your personal key)
- ✅ Add monitoring host keys to `~/.ssh/known_hosts` in advance
- ✅ Use `~/.ssh/config` for host-specific settings (aliases, jump hosts)
- ✅ Restrict SSH user permissions on remote hosts (read-only access)
- ❌ Never disable host key checking in production
- ❌ Never commit SSH private keys to version control
- ❌ Never use root SSH keys for monitoring (create dedicated user)

**Example SSH Config (`~/.ssh/config`):**
```
Host backup-server
    HostName 192.168.1.10
    User kuma-scout
    IdentityFile ~/.ssh/kuma-scout_key
    StrictHostKeyChecking yes

Host nas-server
    HostName 192.168.1.20
    User monitoring
    IdentityFile ~/.ssh/nas_monitoring_key
    Port 2222
```

Then use host aliases in kuma-scout:
```bash
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-uptime-kuma-token \
  --ssh backup-server \
  /data
```

#### SSH Password Authentication Security

⚠️ **SSH password authentication carries security risks**:

**Password Exposure Risk:**
- Passwords are passed via command line to `sshpass`
- Passwords may be visible in process lists (`ps`, `top`, `htop`)
- Other users on the system can potentially see the password

**Example of what's visible:**
```bash
# Process list may show:
sshpass -p mypassword ssh user@host systemctl status nginx
```

**Security Warning:**
When using password authentication, Kuma Scout logs a security warning:
```
⚠️  SECURITY WARNING: Using SSH password authentication. Password may be exposed in process list (ps/top). Consider using SSH key authentication instead.
```

**Recommendations:**
- ✅ **Use SSH key authentication** - More secure and doesn't expose credentials
- ✅ **Restrict SSH key access** - Use key-specific restrictions if possible
- ✅ **Monitor for password usage** - Check logs for security warnings
- ⚠️ **Avoid password auth in production** - Reserve for legacy systems only

**SSH Key Setup (Recommended):**
```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "kuma-scout@yourhost"

# Copy public key to remote host
ssh-copy-id user@remote-host

# Use in Kuma Scout config
ssh:
  host: user@remote-host
  key_file: ~/.ssh/id_ed25519
```

#### Deployment Best Practices

1. **Run under dedicated user:**
   ```bash
   useradd -r -s /bin/false kuma-scout
   chown kuma-scout:kuma-scout /etc/kuma-scout/config.yaml
   chmod 600 /etc/kuma-scout/config.yaml
   ```

2. **Use systemd service with restricted capabilities:**
   ```ini
   [Service]
   User=kuma-scout
   Group=kuma-scout
   NoNewPrivileges=yes
   ProtectSystem=strict
   ProtectHome=yes
   ReadWritePaths=/var/log/kuma-scout
   ```

3. **Enable sudo for specific commands if needed:**
   ```bash
   # /etc/sudoers.d/kuma-scout
   kuma-scout ALL=(root) NOPASSWD: /usr/bin/systemctl, /usr/bin/zpool
   ```

4. **Container deployment (recommended):**
   ```dockerfile
   FROM python:3.11-slim
   RUN useradd -r -s /bin/false kuma-scout
   COPY --chown=kuma-scout:kuma-scout run config.yaml
   USER kuma-scout
   ```


#### What NOT to Do

- ❌ Don't run commands that output passwords, API keys, or PII (output visible to Uptime Kuma)
- ❌ Don't allow user-provided commands via web interfaces
- ❌ Don't run kuma-scout as root unless absolutely necessary
- ❌ Don't expose Uptime Kuma push tokens in logs or metrics
- ❌ Don't use shell=True with unchecked user input
#### Automatic Output Sanitization

⚠️ **SECURITY FEATURE**: Kuma Scout automatically sanitizes command output to prevent accidental exposure of sensitive data.

**By default, the following patterns are masked with `[REDACTED]`:**
- Passwords and secrets: `password=value`, `secret: value`, `api_key=...`
- Authentication tokens: Bearer tokens, AWS keys, GitHub tokens
- Email addresses (masked as `[REDACTED_EMAIL]`)
- Credit card numbers (masked as `[REDACTED_CARD]`)
- Database connection strings (masked as `[REDACTED_DB_CONNECTION]`)
- Exception messages that contain sensitive data

**Example - Automatic Sanitization:**

If your command outputs:
```
Connected to mysql://admin:password123@db.local:3306/prod
User: admin@example.com
Status: OK
```

Uptime Kuma will see:
```
Connected to [REDACTED_DB_CONNECTION]
User: [REDACTED_EMAIL]
Status: OK
```

**Disable Sanitization (if needed for debugging):**

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: myapp_status
    type: cmdcheck
    command: "systemctl status myapp"
    sanitize_output: false  # Default: true
    uptime_kuma:
      token: your-token
```

**⚠️ WARNING**: Only disable sanitization if you're confident the command output won't contain sensitive data.

### Output Sensitivity

Command output is:
- Truncated to 500 characters (last 500 chars retained)
- Sent to Uptime Kuma in plaintext
- Possibly stored in logs and dashboards
- Visible to anyone with Uptime Kuma access

**Example safe outputs:**
- ✅ `active (running)` — Service status
- ✅ `OK` — Health check result
- ✅ `HEALTHY` — Custom application status
- ✅ `1` — Database connectivity test

**Example dangerous outputs:**
- ❌ `password: abc123` — Credentials
- ❌ `api_key: sk-1234567890` — API keys
- ❌ `user@example.com` — PII
- ❌ Database connection strings with passwords

### Common Examples

#### Monitor Multiple Services

```yaml
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
  
  - name: redis
    type: cmdcheck
    command: "systemctl is-active redis-server"
    timeout: 10
    uptime_kuma:
      token: your-token
  
  - name: app
    type: cmdcheck
    command: "systemctl is-active app"
    timeout: 10
    uptime_kuma:
      token: your-token
```

#### Monitor Backup Completion

Create a monitoring script to check for recent backups:
```bash
# Script: /usr/local/bin/check-backup-completion.sh
#!/bin/bash
# Check if backups from last 24 hours exist
find /var/backups -name 'backup-*.tar' -mtime -1 | grep -q .
```

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: backup_check
    type: cmdcheck
    command: "/usr/local/bin/check-backup-completion.sh"
    success_pattern: ""  # Any output = success (files found)
    timeout: 30
    uptime_kuma:
      token: your-token
```

**Alternative:** Use multiple test commands:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: recent_backups
    type: cmdcheck
    command: "find /var/backups -name 'backup-*.tar' -mtime -1"
    timeout: 30
    failure_pattern: "^$"  # Empty output = failure (no backups found)
    uptime_kuma:
      token: your-token
```

#### Check Application via Custom Script

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: app_health
    type: cmdcheck
    command: "/opt/monitoring/check_app_health.sh"
    success_pattern: "HEALTHY"
    failure_pattern: "ERROR|UNHEALTHY|TIMEOUT"
    timeout: 60
    uptime_kuma:
      token: your-token
```

#### Database Replica Lag Check

Create a monitoring script for replication lag:
```bash
# Script: /usr/local/bin/check-replica-lag.sh
#!/bin/bash
# Check PostgreSQL replication lag
LAG=$(psql -h replica.db -U monitoring -d postgres \
  -c "SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))" \
  -t 2>/dev/null | tr -d ' ')

# Check if lag is less than 60 seconds
[ -n "$LAG" ] && [ "${LAG%.*}" -lt 60 ]
```

```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: replica_lag
    type: cmdcheck
    command: "/usr/local/bin/check-replica-lag.sh"
    expect_exit_code: 0
    timeout: 15
    uptime_kuma:
      token: your-token
```

**Alternative:** Use direct command with pattern matching:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: replica_lag
    type: cmdcheck
    command: "psql -h replica.db -U monitoring -d postgres -c SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))"
    failure_pattern: "^\\s*[6-9][0-9]+|^\\s*[1-9][0-9]{2,}"  # Matches >= 60 seconds
    timeout: 15
    uptime_kuma:
      token: your-token
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
# All kuma-scout logs
docker logs kuma-scout

# Or journalctl if running as systemd service
journalctl -u kuma-scout -n 100
```

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
```bash
KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
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

Only the token environment variable is supported:

```bash
KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
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

# With config file and additional settings
kuma-scout kopiasnapshotstatus \
  --config /etc/kuma-scout/config.yaml \
  --max-age-hours 24

# With Uptime Kuma options
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  /data
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
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

### Override config file
```bash
kuma-scout kopiasnapshotstatus \
  --config /etc/kuma-scout/config.yaml \
  /data
```

### With full Uptime Kuma integration
```bash
kuma-scout kopiasnapshotstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-kopia-token \
  --heartbeat-token your-heartbeat-token \
  /data
```
  --heartbeat-token your-heartbeat-token \
  --token your-kopia-token
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
kuma-scout portscan \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-portscan-token \
  192.168.1.0/24

# With custom ports and timing
kuma-scout portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-portscan-token \
  192.168.1.0/24
```

### Authentication Token
```bash
KUMA_SCOUT_PORTSCAN_TOKEN=your-portscan-token
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
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-zfs-token \
  tank
```
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token \
  tank

# Monitor single pool with custom threshold
kuma-scout zfspoolstatus \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token your-heartbeat-token \
  --token your-zfs-token \
  --min-free-percent 20 \
  tank
```

### Authentication Token
```bash
KUMA_SCOUT_ZFSPOOLSTATUS_TOKEN=your-zfs-token
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
  --config /etc/kuma-scout/config.yaml \
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

### Authentication Tokens (Environment Variables Only)

Only authentication tokens are supported via environment variables. All other configuration must use YAML files or CLI arguments.

**Supported token environment variables:**
- `KUMA_SCOUT_HEARTBEAT_TOKEN` - Shared heartbeat notifications token
- `KUMA_SCOUT_CMDCHECK_TOKEN` - Command execution monitoring token
- `KUMA_SCOUT_PORTSCAN_TOKEN` - Port scan results token
- `KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN` - Backup snapshot monitoring token
- `KUMA_SCOUT_ZFSPOOLSTATUS_TOKEN` - ZFS pool monitoring token

**Example:**
```bash
export KUMA_SCOUT_HEARTBEAT_TOKEN=your-heartbeat-token
export KUMA_SCOUT_CMDCHECK_TOKEN=your-cmdcheck-token
export KUMA_SCOUT_PORTSCAN_TOKEN=your-portscan-token
export KUMA_SCOUT_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
export KUMA_SCOUT_ZFSPOOLSTATUS_TOKEN=your-zfs-token
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

### Logging (YAML Only)
```yaml
logging:
  log_file: /var/log/kuma-scout.log
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Note:** Logging configuration can only be set via YAML files or CLI arguments, not environment variables.

### Heartbeat (Uptime Kuma monitoring)
```yaml
heartbeat:
  enabled: true
  interval: 300              # seconds
  uptime_kuma:
    token: your-heartbeat-token
```

**Note:** Enable/disable and interval settings can only be configured via YAML files or CLI arguments.

### Uptime Kuma URL
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
```

**Note:** The base URL must be configured via YAML file or CLI arguments.

## Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):

1. **CLI arguments** - Command-line flags (highest priority)
2. **YAML file** - Configuration from `--config` file
3. **Token Environment Variables** - Only `KUMA_SCOUT_*_TOKEN` variables
4. **Defaults** - Built-in default values (lowest priority)

**Loading order in code:**
```
Defaults (in __init__)
  ↓
Token environment variables (load_from_env)
  ↓
YAML file (load_from_yaml)
  ↓
CLI arguments (load_from_args) ← Final value wins
```

**Note:** Each layer completely replaces the previous one—values don't merge. Only authentication tokens are supported via environment variables.

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

**Note:** Non-token settings can only be configured via YAML files or CLI arguments. Environment variables are reserved for authentication tokens only.

---

## Input Validation

Kuma Scout performs comprehensive validation on all configuration inputs to prevent invalid configurations and security issues. This section describes the validation rules for key configuration fields.

### Uptime Kuma URL Validation

The `uptime_kuma.url` field is validated to ensure it points to a valid, secure Uptime Kuma instance.

**Validation Rules:**
- **Scheme:** Must be `http` or `https` (no `ftp://`, `file://`, etc.)
- **Hostname:** Must be present (e.g., `localhost`, `uptimekuma`, `192.168.1.1`)
- **Format:** No spaces allowed
- **Trailing Slashes:** Not allowed (e.g., `http://uptimekuma:3001/` is invalid, use `http://uptimekuma:3001` instead)

**Valid Examples:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  url: https://monitoring.example.com:8080/api/push
  url: http://192.168.1.1:3001/api/push
  url: https://uptimekuma.example.com
```

**Invalid Examples and Errors:**
```yaml
uptime_kuma:
  url: ftp://uptimekuma:3001/api/push
  # Error: URL scheme must be 'http' or 'https'

uptime_kuma:
  url: http://
  # Error: URL must include a hostname

uptime_kuma:
  url: http://uptimekuma:3001/api/push/
  # Error: URL must not have a trailing slash

uptime_kuma:
  url: http://uptime kuma:3001
  # Error: URL contains invalid characters (spaces)
```

### Port Range Validation (portscan command)

The `portscan.portscan_nmap_ports` field accepts multiple formats for specifying ports to scan.

**Supported Formats:**

1. **Single Port:**
   ```yaml
   portscan:
     portscan_nmap_ports: "80"
     portscan_nmap_ports: "443"
     portscan_nmap_ports: "8080"
   ```

2. **Port Range:**
   ```yaml
   portscan:
     portscan_nmap_ports: "1-1000"        # Ports 1 through 1000
     portscan_nmap_ports: "20-25"         # Common SMTP range
     portscan_nmap_ports: "8000-9000"     # Web services range
   ```

3. **Multiple Ports (Comma-separated):**
   ```yaml
   portscan:
     portscan_nmap_ports: "22,80,443"     # SSH, HTTP, HTTPS
     portscan_nmap_ports: "3306,5432"     # MySQL, PostgreSQL
   ```

4. **Mixed Format:**
   ```yaml
   portscan:
     portscan_nmap_ports: "22,80,443-445,8000-8100"
     # SSH (22), HTTP (80), HTTPS/SMB (443-445), Custom web (8000-8100)
   ```

5. **Common Presets:**
   ```yaml
   portscan:
     portscan_nmap_ports: "1-65535"       # All ports (slow!)
     portscan_nmap_ports: "1-1000"        # Common ports
     portscan_nmap_ports: "20-25,53,80,110,143,443,465,993,995"  # Common services
   ```

**Validation Rules:**
- **Port Range:** Each port must be between 1 and 65535
- **Range Format:** Must be in format `start-end` where `start < end`
- **No Spaces:** Port specifications cannot contain spaces
- **Numeric Values:** All port numbers must be numeric (no letters or special characters)
- **Range Direction:** Cannot have reversed ranges (e.g., `1000-100` is invalid)

**Valid Examples:**
```yaml
portscan:
  portscan_nmap_ports: "22"               # Single port
  portscan_nmap_ports: "1-1000"           # Range
  portscan_nmap_ports: "80,443"           # Multiple ports
  portscan_nmap_ports: "22,80,443-445"    # Mixed
```

**Invalid Examples and Errors:**
```yaml
portscan:
  portscan_nmap_ports: "0"
  # Error: Port must be between 1 and 65535

portscan:
  portscan_nmap_ports: "65536"
  # Error: Port must be between 1 and 65535

portscan:
  portscan_nmap_ports: "1000-100"
  # Error: Port range start must be less than end (range inverted)

portscan:
  portscan_nmap_ports: "80 443"
  # Error: Port specification contains spaces

portscan:
  portscan_nmap_ports: "80-"
  # Error: Invalid port specification (incomplete range)

portscan:
  portscan_nmap_ports: "ssh,http,https"
  # Error: Port specification must contain numeric values only
```

### Configuration Validation on Startup

All configuration is validated when you start Kuma Scout. If validation fails, the application will:

1. **Log a detailed error message** showing exactly what failed
2. **Refuse to start** the monitoring service
3. **Exit with an error code** (exit code 1)

**Example error output:**
```
ERROR: Configuration validation failed
  - Invalid Uptime Kuma URL: URL scheme must be 'http' or 'https'
  - Invalid port specification in portscan: Port must be between 1 and 65535
```

### Handling Validation Errors

**If you get a validation error:**

1. **Read the error message** - It will tell you exactly what's wrong
2. **Check the CONFIGURATION_GUIDE.md** - See valid examples for that field
3. **Validate URL format** - Ensure scheme is http/https, hostname is present, no trailing slashes
4. **Validate port ranges** - Ensure all ports are 1-65535 and ranges are in format start-end
5. **Test with dry-run** - Use `--log-level DEBUG` to see configuration details

**Example debug workflow:**
```bash
# Check if URL is valid
# - Must start with http:// or https://
# - Must have a hostname
# - No trailing slashes

# Check if ports are valid
# - Single: 1-65535
# - Range: start-end (start < end)
# - Multiple: comma-separated, no spaces
# - Examples: "22", "80-443", "22,80,443-445"

# Use verbose logging to see what's being validated
kuma-scout portscan --log-level DEBUG --config config.yaml
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
kuma-scout portscan --log-level DEBUG --config config.yaml
```

### Run configuration tests
```bash
hatch run test tests/test_config_loading.py -v
hatch run test tests/checkers/test_port_checker.py -v
hatch run test tests/checkers/test_kopia_snapshot_checker.py -v
```