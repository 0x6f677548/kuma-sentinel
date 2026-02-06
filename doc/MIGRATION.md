# Migration Guide

This guide helps you upgrade between major versions of Kuma-Scout. Each section documents breaking changes and how to migrate your configurations.

## v0.1.x → v0.2.0 (Major Architecture Change)

### Breaking Changes

#### 1. Complete Architecture Overhaul: Commands → Plugins

**What changed:** Kuma-Scout has been completely rewritten with a plugin-based architecture that reduces boilerplate by ~70% and simplifies configuration.

**Impact:** All existing configurations, scripts, and usage patterns must be updated.

**Before (v0.1.x) - Command-based:**
```bash
# Individual commands with complex nested config
kuma-scout cmdcheck --config config.yaml
kuma-scout portscan --ip-range 192.168.1.0/24 --uptime-kuma-url http://uptime:3001/api/push --token token

# Nested YAML structure
cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      name: "web-server"
      token: "web-token"
portscan:
  ip_range: "192.168.1.0/24"
  token: "port-token"
```

**After (v0.2.0) - Plugin-based:**
```bash
# Unified run command or individual check commands
kuma-scout run --config config.yaml
kuma-scout cmdcheck "systemctl is-active nginx" --uptime-kuma-url http://uptime:3001/api/push --token token --name "web-server"

# Flat YAML structure with checks list
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: "web-server"
    type: cmdcheck
    command: "systemctl is-active nginx"
    uptime_kuma:
      token: "web-token"
    tags: [web, critical]
  - name: "lan-ports"
    type: portscan
    ip_range: "192.168.1.0/24"
    tags: [network]
```

#### 2. Configuration Structure Changes

**YAML Structure Migration:**

Old nested structure:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

cmdcheck:
  commands:
    - command: "systemctl is-active nginx"
      token: "token1"
      
portscan:
  ip_range: "192.168.1.0/24"
  token: "token2"
```

New flat structure:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push

checks:
  - name: "nginx-check"
    type: cmdcheck
    command: "systemctl is-active nginx"
    uptime_kuma:
      token: "token1"
    tags: [web]
    
  - name: "port-scan"
    type: portscan
    ip_range: "192.168.1.0/24"
    tags: [network]
```

#### 3. CLI Command Changes

**Command Migration:**

| Old Command | New Command |
|-------------|-------------|
| `kuma-scout cmdcheck --config config.yaml` | `kuma-scout run --config config.yaml` |
| `kuma-scout cmdcheck --command "cmd"` | `kuma-scout cmdcheck "cmd"` |
| `kuma-scout portscan --ip-range 192.168.1.0/24` | `kuma-scout portscan 192.168.1.0/24` |
| `kuma-scout kopiasnapshotstatus --snapshot /data,24` | `kuma-scout kopiasnapshotstatus "/data"` |
| `kuma-scout zfspoolstatus --pool tank,10` | `kuma-scout zfspoolstatus "tank"` |

#### 4. Migration Steps

1. **Update Configuration Files:**
   - Change nested command configs to flat `checks:` list
   - Add `type:` field to specify plugin type
   - Move command-specific settings under each check
   - Add `name:` and `tags:` fields for better organization

2. **Update Scripts and Cron Jobs:**
   - Replace individual command calls with `kuma-scout run --config config.yaml`
   - Or update to use `kuma-scout check <plugin> --name "check-name" ...`

3. **Update Environment Variables:**
   - Token variables remain the same: `KUMA_SCOUT_*_TOKEN`
   - But now apply globally or per-check

4. **Test Thoroughly:**
   - The new architecture maintains the same monitoring capabilities
   - All plugins support SSH remote execution
   - Tag-based filtering allows running subsets of checks

#### 5. Benefits of the New Architecture

- **70% Less Code**: ~60-80 lines per plugin vs ~525 lines per command
- **Auto-Discovery**: Drop a plugin file and it's automatically available
- **Tag-Based Filtering**: Run checks by tags: `--tag critical`, `--tag web`
- **Consistent Patterns**: All plugins follow the same structure
- **Flat Config**: Simple YAML that's easy to read and maintain

## v0.1.0 → v0.2.0 (Pre-architecture changes)

### Breaking Changes

#### 1. Common Arguments Changed from Positional to Options

**What changed:** The common arguments (`uptime_kuma_url`, `heartbeat_token`, `token`) are now **options** (using `--flag` format) instead of **positional arguments**.

**Impact:** Any shell scripts, cron jobs, or systemd units using the old positional argument syntax will break.

**Before (v0.1.0) - Positional arguments:**
```bash
# uptime_kuma_url, heartbeat_token, and token were positional arguments
kuma-scout kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  kopia-token

kuma-scout zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  zfs-token
```

**After (v0.2.0) - Options:**
```bash
# uptime_kuma_url, heartbeat_token, and token are now options
kuma-scout kopiasnapshotstatus \
  --snapshot /data,24 \
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token

kuma-scout zfspoolstatus \
  --pool tank,10 \
  --pool backup,20 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token zfs-token
```

**Migration Steps:**
1. Move positional URL argument to `--uptime-kuma-url` option
2. Move positional heartbeat token to `--heartbeat-token` option
3. Move positional command token to `--token` option
4. Update all shell scripts, cron jobs, and systemd timers with the new syntax
5. If using Docker containers, update command definitions

---

#### 2. Snapshot/Pool Argument Format Changed

**What changed:** The `--snapshot` and `--pool` options now accept a **single comma-separated value** (`path,hours` or `name,percent`) instead of **two separate positional values**.

**Impact:** Any shell scripts, cron jobs, or systemd units using the old two-value syntax will break.

**Before (v0.1.0) - Two separate values:**
```bash
# --snapshot takes two values: path and hours
kuma-scout kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  kopia-token

# --pool takes two values: name and percent
kuma-scout zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  zfs-token
```

**After (v0.2.0) - Single comma-separated value (hours/percent now optional):**
```bash
# --snapshot takes single value: path,hours or just path
kuma-scout kopiasnapshotstatus \
  --snapshot /data,24 \
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token

# --pool takes single value: name,percent or just name
kuma-scout zfspoolstatus \
  --pool tank,10 \
  --pool backup,20 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token zfs-token
```

**Migration Steps:**
1. Change `--snapshot <path> <hours>` to `--snapshot <path>,<hours>`
2. Change `--pool <name> <percent>` to `--pool <name>,<percent>`
3. Optionally remove the hours/percent if you want to use defaults: `--snapshot <path>` or `--pool <name>`
4. Update all shell scripts, cron jobs, and systemd timers with the new syntax
5. If using Docker containers, update command definitions

---

#### 3. Snapshot/Pool Argument Format Changed

**What changed:** The `--snapshot` and `--pool` options now accept a **single comma-separated value** (`path,hours` or `name,percent`) instead of **two separate positional values**.

**Impact:** Any shell scripts, cron jobs, or systemd units using the old two-value syntax will break.

**Before (v0.1.0) - Two separate values:**
```bash
# --snapshot takes two values: path and hours
kuma-scout kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  kopia-token

# --pool takes two values: name and percent
kuma-scout zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  zfs-token
```

**After (v0.2.0) - Single comma-separated value (hours/percent now optional):**
```bash
# --snapshot takes single value: path,hours or just path
kuma-scout kopiasnapshotstatus \
  --snapshot /data,24 \
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token

# --pool takes single value: name,percent or just name
kuma-scout zfspoolstatus \
  --pool tank,10 \
  --pool backup,20 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token zfs-token
```

**Migration Steps:**
1. Change `--snapshot <path> <hours>` to `--snapshot <path>,<hours>`
2. Change `--pool <name> <percent>` to `--pool <name>,<percent>`
3. Optionally remove the hours/percent if you want to use defaults: `--snapshot <path>` or `--pool <name>`
4. Update all shell scripts, cron jobs, and systemd timers with the new syntax
5. If using Docker containers, update command definitions

---

#### 4. Hours and Percent Parameters Now Optional

**What changed:** The hours and percent parameters are now **optional** in the comma-separated format. You can omit them to use default values.

**Before (v0.1.0):**
```bash
# Always required to specify hours/percent as the second value
kuma-scout kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  kopia-token

kuma-scout zfspoolstatus \
  --pool tank 10 \
  --pool backup 20 \
  http://uptimekuma:3001/api/push \
  heartbeat-token \
  zfs-token
```

**After (v0.2.0) - Can omit hours/percent to use defaults:**
```bash
# Option 1: Specify hours/percent in comma-separated format
kuma-scout kopiasnapshotstatus \
  --snapshot /data,24 \
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token

# Option 2: Omit hours/percent to use defaults
kuma-scout kopiasnapshotstatus \
  --snapshot /data \
  --snapshot /backups \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token

# Option 3: Mix both formats (some with, some without)
kuma-scout kopiasnapshotstatus \
  --snapshot /data \
  --snapshot /backups,48 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --heartbeat-token heartbeat-token \
  --token kopia-token
```

**Default Values:**
- **Kopia snapshots:** 24 hours (if not specified via `--max-age-hours` or per-snapshot value)
- **ZFS pools:** 10% free space (if not specified via `--min-free-percent` or per-pool value)

**Migration Steps:**

1. **If using YAML config:** No changes required—config format remains the same
   
2. **If using CLI arguments:** Convert from two-value format to comma-separated format

   **Example for Kopia:**
   ```bash
   # OLD (v0.1.0) - Two separate values per option
   kuma-scout kopiasnapshotstatus \
     --snapshot /data 24 \
     --snapshot /backups 48 \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token kopia-token
   
   # NEW (v0.2.0) - Comma-separated format with explicit hours
   kuma-scout kopiasnapshotstatus \
     --snapshot /data,24 \
     --snapshot /backups,48 \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token kopia-token
   
   # NEW (v0.2.0) - Simplified with defaults (optional hours)
   kuma-scout kopiasnapshotstatus \
     --snapshot /data \
     --snapshot /backups \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token kopia-token
   ```
   
   **Example for ZFS:**
   ```bash
   # OLD (v0.1.0) - Two separate values per option
   kuma-scout zfspoolstatus \
     --pool tank 10 \
     --pool backup 20 \
     --pool archive 30 \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token zfs-token
   
   # NEW (v0.2.0) - Comma-separated format with explicit percents
   kuma-scout zfspoolstatus \
     --pool tank,10 \
     --pool backup,20 \
     --pool archive,30 \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token zfs-token
   
   # NEW (v0.2.0) - Simplified with defaults (optional percents)
   kuma-scout zfspoolstatus \
     --pool tank \
     --pool backup \
     --pool archive \
     --uptime-kuma-url http://uptimekuma:3001/api/push \
     --heartbeat-token heartbeat-token \
     --token zfs-token
   ```

3. **Verify your changes:** Test CLI commands before deploying to production
   ```bash
   kuma-scout kopiasnapshotstatus --help
   kuma-scout zfspoolstatus --help
   ```

---

#### 5. Removed capture_output Configuration Option

**What changed:** The `capture_output` configuration option has been **removed** from the cmdcheck command. Output is always captured internally for proper functionality.

**Impact:** Any YAML configurations or CLI usage specifying `capture_output` will need to be updated. The option was unused in practice since output was always captured.

**Before (v0.1.0):**
```yaml
cmdcheck:
  commands:
    - command: "my-command"
      capture_output: true  # This option existed but was ignored
  capture_output: true      # Global default (also ignored)
```

**After (v0.2.0) - Option removed:**
```yaml
cmdcheck:
  commands:
    - command: "my-command"  # No capture_output option needed
  # No global capture_output setting
```

**Migration Steps:**
1. Remove `capture_output` from all YAML configuration files
2. Remove `--capture-output` from any CLI commands (the option no longer exists)
3. No functional changes - output capture behavior remains the same

---

### What Stayed the Same

✅ **YAML Configuration Format**: Unchanged. Your existing `config.yaml` files work without modification.

✅ **Heartbeat Functionality**: No changes.

✅ **Uptime Kuma Integration**: No changes.

✅ **Other Commands**: `cmdcheck`, `portscan` remain unchanged (they already use option-based arguments).

---


## Future Versions

Breaking changes for future major versions will be documented in this file with similar detail, allowing users to plan upgrades carefully.
