# Configuration Guide for Kuma Sentinel

## Overview: How Configuration Works

Kuma Sentinel supports multiple configuration sources that work together with a clear priority order. This flexibility allows you to:
- Store sensitive authentication tokens in environment variables
- Use YAML files for detailed, reusable configurations
- Override settings via command-line arguments for one-off executions

**Important:** Only authentication tokens (variables ending in `_TOKEN`) are supported via environment variables. All other configuration must use YAML files or CLI arguments.

### Configuration Priority (Highest to Lowest)

1. **CLI Arguments** - Command-line flags override everything
2. **YAML Config File** - Settings in `/etc/kuma-sentinel/config.yaml` (or custom path via `--config`)
3. **Token Environment Variables** - Authentication tokens prefixed with `KUMA_SENTINEL_*_TOKEN`
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
- Default location: `/etc/kuma-sentinel/config.yaml`
- Override location: `kuma-sentinel COMMAND --config /path/to/config.yaml`

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

These settings apply to all monitoring commands:

**Uptime Kuma Integration:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push  # Where to send push notifications
```

**Heartbeat Service:**
```yaml
heartbeat:
  enabled: true                          # Enable/disable heartbeat pings
  interval: 300                          # Seconds between heartbeats (default: 300 = 5 min)
  uptime_kuma:
    token: your-heartbeat-token          # Shared across all commands
```

**Logging:**
```yaml
logging:
  log_file: /var/log/kuma-sentinel.log  # Log file path
  log_level: INFO                        # DEBUG, INFO, WARNING, ERROR, CRITICAL
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
  uptime_kuma:
    token: your-heartbeat-token
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
  timeout: 10
  uptime_kuma:
    token: your-cmdcheck-token
```

**CLI (Single Command Only):**
```bash
kuma-sentinel cmdcheck \
  --command "systemctl is-active nginx" \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-cmdcheck-token
```

#### Multiple Commands - All Must Pass

**YAML Configuration (Multiple Commands):**
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

**CLI Limitation**: CLI only supports single commands. For multiple commands, use YAML configuration as shown above.

#### Pattern Matching - Detect Conditions in Output

**YAML Configuration:**
```yaml
cmdcheck:
  commands:
    - command: "tail -n 100 /var/log/app.log"
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

#### Authentication Token

**Environment Variable:**
```bash
KUMA_SENTINEL_CMDCHECK_TOKEN=your-cmdcheck-token
```

**Or in YAML:**
```yaml
cmdcheck:
  uptime_kuma:
    token: your-cmdcheck-token
```

### Key Features

- ✅ **Arbitrary Commands** — Run shell commands, scripts, binaries
- ✅ **Pattern Matching** — Detect success/failure via regex patterns on command output (failure > success > exit code precedence)
- ✅ **Multiple Commands** — Run multiple independent checks (via YAML), all must pass for UP
- ✅ **Custom Exit Codes** — Specify expected exit code (default 0), handles non-zero success cases (grep, test, etc.)
- ✅ **Output Truncation** — Last 500 characters captured and sent to Uptime Kuma (prevents log flooding)
- ✅ **Timeout Protection** — Configure per-command timeout (1-300 seconds) to prevent hangs
- ✅ **Per-Command Overrides** — Individual timeouts, exit codes, patterns per command in list
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
cmdcheck:
  commands:
    - command: "/usr/local/bin/check-nginx.sh"
      name: "nginx_check"
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
cmdcheck:
  commands:
    - command: "/usr/local/bin/check-system-health.sh"
      name: "system_health"
      timeout: 10
      expect_exit_code: 0
      success_pattern: "All systems healthy"
      failure_pattern: "failed"
```

### Configuration Reference

#### Always-List Structure

Commands are **always stored as a list**, even for a single command. This provides consistency and enables per-command configuration:

```yaml
cmdcheck:
  # Commands list (required) - always a list
  commands:
    - command: "shell command to execute"    # Required: the actual shell command
      name: "optional_name"                  # Optional: name for reporting (auto-generated if omitted)
      timeout: 30                            # Optional: per-command timeout (inherits from defaults if omitted)
      expect_exit_code: 0                    # Optional: per-command exit code (inherits from defaults if omitted)
      success_pattern: null                  # Optional: per-command success pattern
      failure_pattern: null                  # Optional: per-command failure pattern
      capture_output: true                   # Optional: per-command output capture (inherits from defaults if omitted)
  
  # Default values (applied to all commands unless overridden)
  timeout: 30                                # Default timeout in seconds (1-300, default 30)
  expect_exit_code: 0                        # Default expected exit code (0-255, default 0)
  capture_output: true                       # Default output capture (default true, last 500 chars)
  success_pattern: null                      # Default success pattern (optional)
  failure_pattern: null                      # Default failure pattern (optional, takes precedence)
  sanitize_output: true                      # Sanitize sensitive data from output (default true, prevents credential leakage)
  
  uptime_kuma:
    token: "your-cmdcheck-token"             # Required: push token for this command
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
cmdcheck:
  commands:
    - command: "systemctl is-active myapp"
  expect_exit_code: 0
  timeout: 5

# Example 2: Named single command
cmdcheck:
  commands:
    - command: "test -f /var/run/app.pid"
      name: "app_pid_file"
  timeout: 5

# Example 3: Log error detection (failure pattern)
cmdcheck:
  commands:
    - command: "tail -n 500 /var/log/app.log"
  failure_pattern: "ERROR|CRITICAL|PANIC"
  timeout: 10

# Example 4: Health endpoint with status line (success pattern)
cmdcheck:
  commands:
    - command: "curl -s http://localhost:8080/health"
  success_pattern: '"status":\s*"healthy"'
  timeout: 5

# Example 5: Multiple independent checks (all must pass)
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
  commands:
    - command: "curl -s http://localhost:8080/api/health"
      name: "app_health"
      success_pattern: '"status":\s*"healthy"'
      timeout: 5
```

#### 3. File Existence Checks

Alert if critical files are missing (multiple independent checks):
```yaml
cmdcheck:
  commands:
    - command: "test -f /var/run/app.pid"
      name: "app_pid_file"
      timeout: 5
    - command: "test -f /var/spool/lock"
      name: "lock_file"
      timeout: 5
    - command: "test -f /etc/app/config.yaml"
      name: "config_file"
      timeout: 5
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
cmdcheck:
  commands:
    - command: "/usr/local/bin/check-disk-space.sh"
      timeout: 10
```

#### 5. Log Pattern Detection

Alert on error patterns in logs:
```yaml
cmdcheck:
  commands:
    - command: "journalctl -u myapp -n 1000 --no-pager"
      name: "app_logs"
      failure_pattern: "ERROR|CRITICAL|FATAL"
      success_pattern: "Running normally"
      timeout: 10
```

#### 6. Database Connectivity

Verify database health:
```yaml
cmdcheck:
  commands:
    - command: "psql -h db.example.com -U monitoring -d health_check -c SELECT 1"
      name: "db_health"
      expect_exit_code: 0
      timeout: 10
```

#### 7. Custom Script Execution

Run custom monitoring scripts:
```yaml
cmdcheck:
  commands:
    - command: "/usr/local/bin/custom-health-check.sh"
      name: "custom_check"
      success_pattern: "^HEALTHY"
      timeout: 30
```

### Security Considerations

⚠️ **SECURITY FIRST**: Kuma Sentinel is designed with security as a primary concern.

#### Command Execution Security

Commands are executed **without shell interpretation** (`shell=False`) to prevent command injection vulnerabilities. This means:

- ✅ Shell metacharacters cannot be injected through input
- ✅ Safe against semicolon-separated command chaining
- ✅ Safe against pipe injection attacks
- ✅ Safe against command substitution attacks

#### Configuration Security

Kuma Sentinel assumes **configuration is admin-controlled** (YAML files, CLI arguments, environment variables are set by administrators only).

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

Kuma Sentinel monitors for and **warns about dangerous commands** that could modify system state when executed with elevated privileges (via sudo). This is a **non-blocking security feature** that helps prevent accidental or malicious system modifications.

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
# /etc/sudoers.d/kuma-sentinel
# Allow monitoring user to check service status (read-only)
kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl status *
kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl is-active *

# Allow checking ZFS pool status (read-only)
kuma-sentinel ALL=(root) NOPASSWD: /usr/sbin/zpool list
kuma-sentinel ALL=(root) NOPASSWD: /usr/sbin/zpool status

# Do NOT grant write permissions to ANY tools
# ❌ AVOID: kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl *  (too broad)
# ❌ AVOID: kuma-sentinel ALL=(root) NOPASSWD: /usr/bin/apt *        (package manager)
# ❌ AVOID: kuma-sentinel ALL=(root) NOPASSWD: /bin/rm *             (destructive)
```

**Safe Monitoring Patterns:**

✅ **Good - Read-only checks:**
```yaml
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"        # Status check
    - command: "test -f /var/run/app.pid"         # File existence
    - command: "df / | tail -1 | awk '{print $5}'" # Disk usage
    - command: "zpool status tank"                # ZFS pool status
    - command: "curl -s http://app:8080/health"   # Health endpoint
```

❌ **Dangerous - System modification:**
```yaml
cmdcheck:
  commands:
    - command: "systemctl restart nginx"          # Modifies service
    - command: "apt update && apt upgrade"        # Installs packages
    - command: "rm -rf /tmp/cache"                # Deletes files
    - command: "zpool destroy tank"               # Destroys storage
    - command: "reboot"                           # Reboots system
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

Kuma Sentinel **enforces** that your configuration file has **restricted permissions (0o600)** to prevent unauthorized access to sensitive tokens and credentials.

**What it checks:**
- Config file should only be readable/writable by its owner
- Typical location: `/etc/kuma-sentinel/config.yaml` (owner: kuma-sentinel)
- Restrictive permissions prevent other users from reading your Uptime Kuma tokens

**If validation fails**, execution **BLOCKS** with an error:
```
❌ Security check failed: Config file /etc/kuma-sentinel/config.yaml has overly permissive mode 0o644.
Recommended: 0o600. Run: chmod 600 /etc/kuma-sentinel/config.yaml
To bypass this check, use --ignore-file-permissions flag or set logging.ignore_file_permissions: true in config.
```

**To bypass this check** (development or testing only):
```bash
# Using CLI flag
kuma-sentinel cmdcheck --ignore-file-permissions --config ./config.yaml

# Using YAML configuration
logging:
  ignore_file_permissions: true
```

⚠️ **Security Note**: Only bypass this check during development or testing. Always ensure production configurations have proper permissions (0o600). A config file with world-readable permissions exposes your Uptime Kuma authentication tokens.

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

- ❌ Don't run commands that output passwords, API keys, or PII (output visible to Uptime Kuma)
- ❌ Don't allow user-provided commands via web interfaces
- ❌ Don't run kuma-sentinel as root unless absolutely necessary
- ❌ Don't expose Uptime Kuma push tokens in logs or metrics
- ❌ Don't use shell=True with unchecked user input
#### Automatic Output Sanitization

⚠️ **SECURITY FEATURE**: Kuma Sentinel automatically sanitizes command output to prevent accidental exposure of sensitive data.

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
cmdcheck:
  commands:
    - command: "systemctl status myapp"
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

Create a monitoring script to check for recent backups:
```bash
# Script: /usr/local/bin/check-backup-completion.sh
#!/bin/bash
# Check if backups from last 24 hours exist
find /var/backups -name 'backup-*.tar' -mtime -1 | grep -q .
```

```yaml
cmdcheck:
  commands:
    - command: "/usr/local/bin/check-backup-completion.sh"
      name: "backup_check"
      success_pattern: ""  # Any output = success (files found)
      timeout: 30
```

**Alternative:** Use multiple test commands:
```yaml
cmdcheck:
  commands:
    - command: "find /var/backups -name 'backup-*.tar' -mtime -1"
      name: "recent_backups"
      timeout: 30
      failure_pattern: "^$"  # Empty output = failure (no backups found)
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
cmdcheck:
  commands:
    - command: "/usr/local/bin/check-replica-lag.sh"
      name: "replica_lag"
      expect_exit_code: 0
      timeout: 15
```

**Alternative:** Use direct command with pattern matching:
```yaml
cmdcheck:
  commands:
    - command: "psql -h replica.db -U monitoring -d postgres -c SELECT EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))"
      name: "replica_lag"
      failure_pattern: "^\\s*[6-9][0-9]+|^\\s*[1-9][0-9]{2,}"  # Matches >= 60 seconds
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

### Authentication Token
```bash
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
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
3. **Defaults** - Built-in defaults (max_age_hours: 24)

**Note:** CLI arguments completely override YAML config. Each layer fully replaces the previous one—they don't merge.

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

### Authentication Token

Only the token environment variable is supported:

```bash
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
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

### Authentication Token
```bash
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

### Authentication Token
```bash
KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN=your-zfs-token
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
zfspoolstatus:
  pools:                          # List of pool configurations
    - name: <string>              # Required: pool name (e.g., "tank")
      free_space_percent_min: <int>  # Optional: min free space % (falls back to global default)
  free_space_percent_default: <int>  # Global default (default: 10)
  uptime_kuma:
    token: <string>               # Uptime Kuma API token
```



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

### Authentication Tokens (Environment Variables Only)

Only authentication tokens are supported via environment variables. All other configuration must use YAML files or CLI arguments.

**Supported token environment variables:**
- `KUMA_SENTINEL_HEARTBEAT_TOKEN` - Shared heartbeat notifications token
- `KUMA_SENTINEL_CMDCHECK_TOKEN` - Command execution monitoring token
- `KUMA_SENTINEL_PORTSCAN_TOKEN` - Port scan results token
- `KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN` - Backup snapshot monitoring token
- `KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN` - ZFS pool monitoring token

**Example:**
```bash
export KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token
export KUMA_SENTINEL_CMDCHECK_TOKEN=your-cmdcheck-token
export KUMA_SENTINEL_PORTSCAN_TOKEN=your-portscan-token
export KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
export KUMA_SENTINEL_ZFSPOOLSTATUS_TOKEN=your-zfs-token
```

**Or in YAML:**
```yaml
heartbeat:
  uptime_kuma:
    token: your-heartbeat-token

cmdcheck:
  uptime_kuma:
    token: your-cmdcheck-token

portscan:
  uptime_kuma:
    token: your-portscan-token

kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token

zfspoolstatus:
  uptime_kuma:
    token: your-zfs-token
```

### Logging (YAML Only)
```yaml
logging:
  log_file: /var/log/kuma-sentinel.log
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
3. **Token Environment Variables** - Only `KUMA_SENTINEL_*_TOKEN` variables
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
portscan:
  ports: 1-1000
```

```bash
# CLI argument (highest priority - takes final effect)
kuma-sentinel portscan --ports 1-65535
```

**Result:** Scans ports `1-65535` (CLI argument wins)

If you remove the CLI argument:
```bash
kuma-sentinel portscan
# Result: Scans ports 1-1000 (YAML file wins)
```

**Note:** Non-token settings can only be configured via YAML files or CLI arguments. Environment variables are reserved for authentication tokens only.

---

## Input Validation

Kuma Sentinel performs comprehensive validation on all configuration inputs to prevent invalid configurations and security issues. This section describes the validation rules for key configuration fields.

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

All configuration is validated when you start Kuma Sentinel. If validation fails, the application will:

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
kuma-sentinel portscan --log-level DEBUG --config config.yaml
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

### Run configuration tests
```bash
pytest tests/test_config.py -v
pytest tests/checkers/test_port_checker.py -v
pytest tests/checkers/test_kopia_snapshot_checker.py -v
```