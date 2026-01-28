# Migration Guide

This guide helps you upgrade between major versions of Kuma-Scout. Each section documents breaking changes and how to migrate your configurations.

## v0.1.0 → v0.2.0

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

### What Stayed the Same

✅ **YAML Configuration Format**: Unchanged. Your existing `config.yaml` files work without modification.

✅ **Heartbeat Functionality**: No changes.

✅ **Uptime Kuma Integration**: No changes.

✅ **Other Commands**: `cmdcheck`, `portscan` remain unchanged (they already use option-based arguments).

---


## Future Versions

Breaking changes for future major versions will be documented in this file with similar detail, allowing users to plan upgrades carefully.
