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
kuma-scout run config.yaml
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
| `kuma-scout cmdcheck --config config.yaml` | `kuma-scout run config.yaml` |
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
   - Tokens now support variable expansion using `${VAR}` syntax (any variable name)
   - Use in YAML config: `token: ${MY_TOKEN}`
   - Use on CLI: `--token "${MY_TOKEN}"`
   - No predefined variable names required

4. **Test Thoroughly:**
   - The new architecture maintains the same monitoring capabilities
   - All plugins support SSH remote execution
   - Tag-based filtering allows running subsets of checks

#### 5. Tag-Based Result Aggregation (New in v0.2.0)

**What changed:** v0.2.0 introduces automatic tag-based result aggregation. Each check can be tagged, and results are automatically aggregated by tag and sent to tag-specific tokens.

**How it works:**
- Each check gets an individual result sent to its token (or global token if not configured)
- Checks with tags are ALSO aggregated and results sent to the tag's configured token
- This means each check generates TWO API calls to Uptime Kuma (individual + aggregated)

**Configuration Example:**

```yaml
# Global token for individual check results
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: DEFAULT_TOKEN  # Each check sends individual result here

# Tag-specific tokens for aggregated results
tags:
  web:
    uptime_kuma:
      token: WEB_AGGREGATION_TOKEN
  critical:
    uptime_kuma:
      token: CRITICAL_AGGREGATION_TOKEN

# Checks with tags
checks:
  - name: nginx
    type: cmdcheck
    command: systemctl is-active nginx
    tags: [web, critical]  # Sends to DEFAULT_TOKEN + WEB_AGGREGATION_TOKEN + CRITICAL_AGGREGATION_TOKEN
  
  - name: postgres
    type: cmdcheck
    command: systemctl is-active postgresql
    tags: [database, critical]  # Sends to DEFAULT_TOKEN + CRITICAL_AGGREGATION_TOKEN
```

**API Call Breakdown Example:**
- 2 checks with tags: 2 individual results + 2 aggregated by tag = 4 total API calls
- 3 checks with tags: 3 individual results + 3 aggregated by tag = 6 total API calls
- Checks without tags: Only individual results sent (no additional aggregation calls)

**Token Precedence:**
For individual check results:
1. Check-level `uptime_kuma.token` (if configured)
2. Global `uptime_kuma.token` (if configured)
3. No report (if neither configured)

For aggregated results by tag:
1. Tag-level `uptime_kuma.token` (if configured)
2. No report (aggregation only happens if tag token configured)

See [Tag-Based Result Aggregation](CONFIGURATION_GUIDE.md#tag-based-result-aggregation) for complete details.

#### 6. Benefits of the New Architecture

- **70% Less Code**: ~60-80 lines per plugin vs ~525 lines per command
- **Auto-Discovery**: Drop a plugin file and it's automatically available
- **Tag-Based Filtering and Aggregation**: Filter with `--tag critical` and aggregate results automatically
- **Consistent Patterns**: All plugins follow the same structure
- **Flat Config**: Simple YAML that's easy to read and maintain
- **Dual Reporting**: Get both granular per-check AND high-level tag aggregation monitoring

---

## v0.2.0 → v0.2.1 (Behavior Change)

### CLI overrides now take precedence over per-check config

**What changed:** CLI arguments (`--timeout`, `--uptime-kuma-url`, `--token`, `--ssh*`) now override per-check YAML settings for the run invocation. Previously per-check values took precedence over CLI flags.

**Impact:**
- `kuma-scout run config.yaml --timeout 5` now applies 5s to every check, even those with a per-check `timeout`.
- `--uptime-kuma-url` / `--token` override per-check `uptime_kuma` (a CLI token is applied only together with a CLI url).
- `--ssh` replaces per-check `ssh` settings entirely.
- Without CLI flags, behavior is unchanged (per-check overrides global YAML, global is the fallback).

**Migration:** Review automation that passes CLI flags alongside config files that define per-check `timeout`, `uptime_kuma`, or `ssh`. The CLI values now win.

---

## Future Versions

Breaking changes for future major versions will be documented in this file with similar detail, allowing users to plan upgrades carefully.
