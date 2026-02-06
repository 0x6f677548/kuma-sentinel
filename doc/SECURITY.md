# Security Guide

Kuma-Scout is designed with security as a core principle. This guide explains the security features and best practices.

## Core Security Features

### Command Execution Security

Kuma Scout executes commands **without shell interpretation**, preventing shell injection attacks:

- ✅ **No Shell Injection**: Commands are executed directly without shell parsing
- ✅ **Safe Metacharacters**: Semicolons, pipes, operators (`&&`, `||`, etc.) cannot chain commands
- ✅ **Safe Configuration**: Commands come from YAML config files only, never from untrusted sources

**Example - Protected:**

```yaml
checks:
  - name: secure_check
    type: cmdcheck
    command: "systemctl is-active nginx; rm -rf /"
```

The semicolon is passed as a literal argument to `systemctl`, which rejects it as invalid. The `rm -rf /` is never executed.

**Configuration File is the Attack Surface:**

If an attacker gains **write access to the config file**, they can replace commands:

```yaml
# ❌ Threat if config is writable
checks:
  - name: compromised_check
    type: cmdcheck
    command: "rm -rf /"
```

**Real Protection**: Secure your configuration files with proper permissions (see "Configuration File Permissions" below).

## Running as Non-Root

⚠️ **Always run Kuma Scout as a dedicated, low-privilege user:**

### System User Setup

```bash
# Create dedicated user
useradd -r -s /bin/false kuma-scout

# Set permissions on config file
chmod 600 /etc/kuma-scout/config.yaml
chown kuma-scout:kuma-scout /etc/kuma-scout/config.yaml

# Create log directory
mkdir -p /var/log/kuma-scout
chown kuma-scout:kuma-scout /var/log/kuma-scout
chmod 755 /var/log/kuma-scout
```

### systemd Service Example

```ini
[Unit]
Description=Kuma Scout Monitoring Agent
After=network-online.target

[Service]
Type=oneshot
User=kuma-scout
Group=kuma-scout
ExecStart=/usr/bin/kuma-scout run /etc/kuma-scout/config.yaml
StandardOutput=journal
StandardError=journal
```

### Elevated Privileges with sudo

If specific checks require root privileges, use **minimal sudo rules**:

```bash
# In /etc/sudoers (edit with visudo)
# Allow only specific, read-only commands
kuma-scout ALL=(root) NOPASSWD: /usr/bin/systemctl is-active
kuma-scout ALL=(root) NOPASSWD: /usr/sbin/zpool status
kuma-scout ALL=(root) NOPASSWD: /bin/ls -la /var/backups
```

**Detailed Sudoers Configuration Examples:**

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

Then in config:

```yaml
checks:
  - name: zfs_check
    type: cmdcheck
    command: "sudo /usr/sbin/zpool status tank"
    # sudo required because user has no direct zpool access
```

**Key Principles:**
- Use `sudo` only for specific commands
- Never use `sudo kuma-scout` - run the service as unprivileged user
- Restrict sudo to read-only commands when possible
- Use `NOPASSWD` to avoid password prompts in non-interactive monitoring

## Attack Vectors & Mitigations

Understanding potential security threats helps you deploy Kuma Scout securely:

| Vector | Risk | Mitigation |
|--------|------|-----------|
| Config File Tampering | Malicious commands in config | File permissions (600), access control |
| PATH Manipulation | Malicious binary substitution | Use absolute paths; dedicated service user |
| Privilege Escalation | Commands running as root | Run as dedicated low-privilege user |
| Resource Exhaustion | Fork bombs, infinite loops | Timeout (default 30s) + cgroup limits |
| Output Leakage | Sensitive data in command output | Output truncated to 500 chars; sanitize scripts |

## Dangerous Command Pattern Detection

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
- Restrict sudo to read-only commands when possible
- Use `NOPASSWD` to avoid password prompts

## Configuration File Permissions

Configuration files contain authentication tokens - **restrict access strictly**:

```bash
# Set secure permissions (readable by owner only)
chmod 600 /etc/kuma-scout/config.yaml

# Verify permissions (should show: -rw-------)
ls -la /etc/kuma-scout/config.yaml

# Verify ownership
chown kuma-scout:kuma-scout /etc/kuma-scout/config.yaml
```

### Example: Insecure Permissions

```bash
# ❌ DO NOT DO THIS
chmod 644 /etc/kuma-scout/config.yaml  # World-readable!
chmod 777 /etc/kuma-scout/               # World-writable!
```

These permissions expose your authentication tokens to any user on the system.

## SSH Security

### Strict Host Key Checking (Default: Enabled)

Host key verification is **enabled by default** to prevent man-in-the-middle attacks:

```yaml
ssh:
  strict_host_key_checking: true  # Default
```

**Known Hosts Management:**

```bash
# Manually add hosts to ~/.ssh/known_hosts first
ssh-keyscan -t ed25519 remote-server.example.com >> ~/.ssh/known_hosts

# Or use ssh-copy-id which handles host keys
ssh-copy-id -i ~/.ssh/kuma_scout_key.pub user@remote-server
```

### SSH Key Authentication (Recommended)

Use SSH keys instead of passwords:

```bash
# Generate ED25519 key (more secure than RSA)
ssh-keygen -t ed25519 -f ~/.ssh/kuma_scout_key -C "kuma-scout key" -N ""

# Set secure permissions
chmod 600 ~/.ssh/kuma_scout_key
chmod 644 ~/.ssh/kuma_scout_key.pub

# Copy public key to target
ssh-copy-id -i ~/.ssh/kuma_scout_key.pub user@remote-server

# Test access
ssh -i ~/.ssh/kuma_scout_key user@remote-server "uptime"
```

### SSH Key in Configuration

```yaml
ssh:
  host: user@remote-server
  key_file: ~/.ssh/kuma_scout_key  # Path to private key
  # strict_host_key_checking: true  # Default
```

### Restrict SSH Key Permissions

```bash
# Key must have mode 600
chmod 600 ~/.ssh/kuma_scout_key

# Public key can be 644
chmod 644 ~/.ssh/kuma_scout_key.pub

# .ssh directory must be 700
chmod 700 ~/.ssh

# Verify
ls -la ~/.ssh/kuma_scout_key*
# -rw------- 1 user user ... kuma_scout_key
# -rw-r--r-- 1 user user ... kuma_scout_key.pub
```

### SSH on Non-Standard Ports

```bash
# SSH with custom port
ssh -p 2222 user@remote-server

# In Kuma Scout config
ssh:
  host: user@remote-server:2222
```

### Disable Strict Host Key Checking (Not Recommended)

Only disable if running in isolated, trusted environments:

```yaml
ssh:
  strict_host_key_checking: false  # ⚠️ NOT recommended for production
```

Or via CLI:

```bash
kuma-scout cmdcheck "uptime" \
  --ssh user@remote-server \
  --ssh-no-strict-host-key-checking  # ⚠️ NOT recommended
```

## Token Security

### Variable Expansion

All configuration values support environment variable expansion using `${VARIABLE_NAME}` syntax. This includes tokens, URLs, paths, and sensitive data like SSH passwords:

```bash
# ✅ Variable expansion works for all config values
export MY_SECURE_TOKEN=my-token-value
export SSH_PASSWORD=my-ssh-pass

# In YAML config
uptime_kuma:
  token: ${MY_SECURE_TOKEN}

ssh:
  password: ${SSH_PASSWORD}  # Also supports expansion

# Or on CLI
kuma-scout cmdcheck "uptime" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token "${MY_SECURE_TOKEN}" \
  --name "my-check"
```

### Store Tokens Securely

```bash
# ❌ Never hardcode tokens in scripts or config files
token: "secret-token-here"  # Don't do this

# ✅ Use environment variable expansion with .env file
echo "MY_TOKEN=secure-token" > /etc/kuma-scout/.env
chmod 600 /etc/kuma-scout/.env
source /etc/kuma-scout/.env

# In config, reference the environment variable
uptime_kuma:
  token: ${MY_TOKEN}

# ✅ Use secret management systems
# Docker Secrets, Kubernetes Secrets, HashiCorp Vault, etc.

# ✅ Use systemd environment files
# /etc/systemd/system/kuma-scout.service.d/env.conf
# [Service]
# EnvironmentFile=/etc/kuma-scout/kuma-scout.env
```

### Configuration Priority

Configuration is loaded in this priority order:

1. **CLI arguments** (highest priority)
2. **YAML configuration file**
3. **Token environment variables** (tokens only)
4. **Hardcoded defaults** (lowest priority)

This means CLI arguments can override everything, useful for secure token passing.

## Output Sanitization

Command output is **automatically sanitized** to prevent credential leakage:

- ✅ **Automatic Masking**: Passwords, API keys, tokens, emails, connection strings
- ✅ **Truncation**: Output limited to 500 characters before transmission
- ✅ **Error Sanitization**: Exception messages scrubbed of sensitive data

### Patterns Automatically Masked

- `password=***`, `secret=***`, `api_key=***`
- Bearer tokens: `Authorization: Bearer ***`
- AWS/Azure/GCP credentials
- Email addresses → `[REDACTED_EMAIL]`
- Credit cards → `[REDACTED_CARD]`
- Database URLs → `[REDACTED_DB_CONNECTION]`

**Example:**

```
Original: Connected to mysql://root:MyPassword123@localhost:3306/app
Sanitized: Connected to [REDACTED_DB_CONNECTION]
```

### Verify Sanitization

Logs contain sanitized output:

```bash
# View logs
tail -f /var/log/kuma-scout.log

# Sensitive data should be masked
[2024-01-15 14:32:15] Connected to [REDACTED_DB_CONNECTION]
```

### Disable Sanitization (Not Recommended)

Only for debugging - never use in production:

```yaml
sanitize_output: false  # ❌ NOT recommended
```

**Why this is dangerous**: Sanitization disabled means credentials, passwords, and tokens in command output will be sent to Uptime Kuma unmasked.

## Best Practices

### Command Design

1. **Use Exit Codes**: Prefer exit code (0 = success, non-zero = failure) over output parsing

```yaml
# Good: simple exit code check
checks:
  - name: service_check
    type: cmdcheck
    command: "systemctl is-active nginx"
    # Exit 0 = active, non-zero = inactive
```

2. **Use Pattern Matching**: Match specific status indicators, not full output

```yaml
# Good: match only the important part
checks:
  - name: health_check
    type: cmdcheck
    command: "curl -s http://api:8080/health"
    success_pattern: '"status":"ok"'
    failure_pattern: '"error"'
```

3. **Avoid Outputting Secrets**: Never echo passwords or tokens

```bash
# ❌ Bad: outputs password
echo "mysql -u root -p$DB_PASSWORD ..."

# ✅ Good: no output
mysql -u root -p$DB_PASSWORD -e "SELECT 1" > /dev/null
```

4. **Wrap Complex Logic in Scripts**: Can't use pipes with `shell=False`, so wrap in shell script

```bash
# myscript.sh
#!/bin/bash
curl -s http://api:8080/health | jq -e '.status == "ok"'

# Then in config:
checks:
  - name: health_check
    type: cmdcheck
    command: "/usr/local/bin/myscript.sh"
```

### Safe vs Dangerous Monitoring Patterns

**Safe - Read-only checks (Recommended):**

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

**Dangerous - System modification (Avoid):**

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

**Key Takeaway**: Use monitoring checks to **detect problems**, not to **fix them**. Prefer read-only checks that report status. If automatic remediation is needed, use separate automation tools designed for that purpose.
    success_pattern: '"status":"ok"'
    failure_pattern: '"error"'
```

3. **Avoid Outputting Secrets**: Never echo passwords or tokens

```bash
# ❌ Bad: outputs password
echo "mysql -u root -p$DB_PASSWORD ..."

# ✅ Good: no output
mysql -u root -p$DB_PASSWORD -e "SELECT 1" > /dev/null
```

4. **Wrap Complex Logic in Scripts**: Can't use pipes with `shell=False`, so wrap in shell script

```bash
# myscript.sh
#!/bin/bash
curl -s http://api:8080/health | jq -e '.status == "ok"'

# Then in config:
checks:
  - name: health_check
    type: cmdcheck
    command: "/usr/local/bin/myscript.sh"
```

### Network Security

1. **Use HTTPS**: Always use HTTPS for Uptime Kuma URL

```yaml
# ❌ Insecure
uptime_kuma:
  url: http://uptime-kuma:3001/api/push

# ✅ Secure
uptime_kuma:
  url: https://uptime-kuma.example.com/api/push
```

2. **VPN for Remote SSH**: Use VPN for secure SSH access over untrusted networks

```yaml
ssh:
  host: user@remote-server.vpn-only
  key_file: ~/.ssh/vpn_key
```

3. **Firewall Rules**: Restrict Kuma-Scout's outbound connections

```bash
# iptables example: allow only to Uptime Kuma server
iptables -A OUTPUT -d 10.0.0.5 -p tcp --dport 3001 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 3001 -j DROP
```

### File Permissions Checklist

```bash
# Config file: readable by service user only
-rw------- kuma-scout kuma-scout /etc/kuma-scout/config.yaml

# SSH key: readable by service user only
-rw------- kuma-scout kuma-scout ~/.ssh/kuma_scout_key

# Log directory: writable by service user
drwxr-xr-x kuma-scout kuma-scout /var/log/kuma-scout

# Verify all:
sudo -u kuma-scout test -r /etc/kuma-scout/config.yaml && echo "Config readable"
sudo -u kuma-scout test -w /var/log/kuma-scout && echo "Log dir writable"
```

### Monitoring and Auditing

1. **Enable Logging**: Always enable file and/or syslog logging

```yaml
logging:
  level: INFO  # DEBUG for troubleshooting
  file: /var/log/kuma-scout.log
```

2. **Monitor Logs**: Check logs regularly for errors or anomalies

```bash
# Recent errors
grep ERROR /var/log/kuma-scout.log

# Failed checks
grep "DOWN\|Failed\|error" /var/log/kuma-scout.log

# SSH access attempts
grep "ssh\|SSH\|remote" /var/log/kuma-scout.log
```

3. **Rotate Logs**: Use logrotate to prevent disk space issues

```bash
# /etc/logrotate.d/kuma-scout
/var/log/kuma-scout.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0600 kuma-scout kuma-scout
}
```

## Security Checklist

Before deploying to production:

- [ ] Running as non-root user `kuma-scout`
- [ ] Config file permissions are `600` (readable by owner only)
- [ ] Config file owner is `kuma-scout:kuma-scout`
- [ ] SSH keys have permissions `600`
- [ ] SSH known_hosts is properly configured
- [ ] Uptime Kuma URL uses HTTPS
- [ ] No tokens in command output (checked logs)
- [ ] Logging is enabled to file and/or syslog
- [ ] Output sanitization is enabled (default)
- [ ] Only necessary sudo permissions granted
- [ ] Tokens stored in environment or secret management, not hardcoded
- [ ] Regular log monitoring and auditing in place

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly to the maintainers rather than opening a public issue. This allows time for a fix before disclosure. 

Contact: [code at hugobatista.com]

## Further Reading

- [Configuration Guide](CONFIGURATION_GUIDE.md) - Configuration options and examples
- [CLI Usage](CLI.md) - Command-line interface documentation
- [Docker Deployment](DOCKER.md) - Containerized deployment security
