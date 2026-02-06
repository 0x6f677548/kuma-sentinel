[![PyPI - Version](https://img.shields.io/pypi/v/kuma-scout.svg)](https://pypi.org/project/kuma-scout)
[![GitHub Tag](https://img.shields.io/github/v/tag/hugobatista/kuma-scout?logo=github&label=latest)](https://go.hugobatista.com/gh/kuma-scout/releases)
[![GHCR Tag](https://img.shields.io/github/v/tag/hugobatista/kuma-scout?logo=docker&logoColor=white&label=GHCR)](https://go.hugobatista.com/gh/kuma-scout/packages)
[![Test](https://go.hugobatista.com/gh/kuma-scout/actions/workflows/test.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-scout/actions/workflows/test.yml)
[![Lint](https://go.hugobatista.com/gh/kuma-scout/actions/workflows/lint.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-scout/actions/workflows/lint.yml)

# Kuma-Scout 🧭

**Uptime Kuma's monitoring agent.** Execute custom checks locally or remotely via SSH and report results to Uptime Kuma's push API.

Monitor anything that can be checked with a shell command: system health, backups, storage, ports, network devices, and custom scripts. Deploy via cron, systemd timer, or Docker.

## Quick Start

```bash
# Install
pip install kuma-scout

# Single check via CLI
kuma-scout cmdcheck "systemctl is-active nginx" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \

# Multiple checks via YAML config
kuma-scout run /etc/kuma-scout/config.yaml

# Remote execution via SSH
kuma-scout cmdcheck "systemctl is-active nginx" \
  --ssh user@remote-server \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
```

Result: ✅ UP (all checks pass) or ⚠️ DOWN (any check fails) in Uptime Kuma dashboard.

## Features

- **Command Execution**: Execute arbitrary shell commands and monitor results (cmdcheck plugin)
- **SSH Remote Execution**: Run checks remotely on any SSH-accessible system
- **Port Scanning**: Scan TCP ports across IP ranges using nmap (portscan plugin)
- **Backup Monitoring**: Monitor Kopia backup snapshot freshness (kopiasnapshotstatus plugin)
- **Storage Monitoring**: Monitor ZFS pool health and free space (zfspoolstatus plugin)
- **Heartbeat Monitoring**: Send periodic health signals during long operations
- **Pattern Matching**: Use regex patterns for flexible success/failure detection
- **Multi-Check Support**: Run multiple checks with per-check configuration and tokens
- **Tag-Based Filtering**: Group checks by tags for selective execution
- **Plugin Architecture**: Extensible system with auto-discovery
- **Flexible Configuration**: YAML config files, environment variables, CLI arguments
- **Security First**: Commands executed safely without shell injection; SSH with host key verification

## Installation

### Via pip (PyPI)

```bash
pip install kuma-scout
```

### From source

```bash
git clone https://go.hugobatista.com/gh/kuma-scout.git
cd kuma-scout
pip install -e .
```

### Docker

See [doc/DOCKER.md](doc/DOCKER.md) for Docker installation and usage.

## Documentation

- **[Configuration Guide](doc/CONFIGURATION_GUIDE.md)** - Detailed configuration reference with all options and examples
- **[CLI Usage](doc/CLI.md)** - Command-line interface documentation and examples
- **[Security](doc/SECURITY.md)** - Security considerations and best practices
- **[Docker](doc/DOCKER.md)** - Docker installation and containerized deployment
- **[Migration Guide](doc/MIGRATION.md)** - Upgrading between versions
- **[Development](doc/DEVELOPMENT.md)** - Plugin development and contributing

## Use Cases

### Universal Monitoring

Monitor any condition using shell commands:
- Service health: `systemctl is-active nginx`
- Database connectivity: `psql -c "SELECT 1"`
- Health endpoints: `curl -sf http://api:8080/health`
- Custom scripts: `/usr/local/bin/custom-check.sh`

### Remote Infrastructure Monitoring

Monitor systems remotely via SSH without installing agents:

**CLI - Single remote check:**
```bash
kuma-scout cmdcheck "systemctl is-active nginx" \
  --ssh admin@remote-server \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
```

**YAML - Multiple remote servers:**
```yaml
uptime_kuma:
  url: http://uptime-kuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}

ssh:
  host: app-server.prod.example.com
  user: monitoring
  key_file: /root/.ssh/prod_key

checks:
  - name: app_service
    type: cmdcheck
    command: "systemctl is-active myapp"
    
  - name: db_health
    type: cmdcheck
    command: "systemctl is-active postgresql"
    ssh:
      host: db-server.prod.example.com
```

### Backup Monitoring

Ensure backups are running on schedule with Kopia snapshot checks:
```yaml
checks:
  - name: daily_backup
    type: kopiasnapshotstatus
    path: "/data"
    max_age_hours: 24
```

### Storage Health

Monitor ZFS pools and ensure adequate free space:
```yaml
checks:
  - name: tank_pool
    type: zfspoolstatus
    pool: "tank"
    min_free_percent: 10
```

### Network Security

Monitor exposed ports on your infrastructure:
```bash
kuma-scout portscan 192.168.1.0/24 \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token YOUR_TOKEN \
```

## How It Works

1. **Define checks** in YAML config or via CLI
2. **Run checks** locally or remotely via SSH
3. **Get results** as UP/DOWN status in Uptime Kuma dashboard
4. **Receive alerts** when checks fail

## Help

```bash
kuma-scout --help                      # Show available commands
kuma-scout cmdcheck --help             # Show command execution options
kuma-scout run --help                  # Show run command options
```

## Requirements

- Python 3.10+
- nmap (for port scanning)
- Kopia (for backup monitoring)
- ZFS tools (for storage monitoring)

## Quick Example

### Configuration File

Create `/etc/kuma-scout/config.yaml`:

```yaml
uptime_kuma:
  url: http://uptime-kuma:3001/api/push
  token: ${UPTIME_KUMA_TOKEN}

logging:
  level: INFO

checks:
  - name: nginx_health
    type: cmdcheck
    command: "systemctl is-active nginx"
    tags: [web, critical]
    
  - name: disk_space
    type: cmdcheck
    command: "df -h / | grep -E '^/'"
    tags: [storage]
    timeout: 10
    
  - name: backup_check
    type: kopiasnapshotstatus
    path: "/data"
    max_age_hours: 24
    tags: [backups]
```

### Run

```bash
export UPTIME_KUMA_TOKEN=your-push-token
kuma-scout run /etc/kuma-scout/config.yaml
```

Or schedule with cron:

```bash
# Run every 5 minutes
*/5 * * * * kuma-scout run /etc/kuma-scout/config.yaml
```

## Security

⚠️ **Key Points:**
- Configuration files contain authentication tokens - restrict permissions to `600`
- Run as non-root user with minimal privileges when possible
- Commands executed without shell interpretation (injection-safe)
- SSH strict host key checking enabled by default

See [doc/SECURITY.md](doc/SECURITY.md) for comprehensive security guidance.

## Upgrading

For migration notes between versions, see [doc/MIGRATION.md](doc/MIGRATION.md).

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

Contributions welcome! See [doc/DEVELOPMENT.md](doc/DEVELOPMENT.md) for development setup.

1. Fork and create a feature branch
2. Make your changes with tests
3. Run `hatch run check` to validate
4. Submit a pull request

## Issues

Report bugs on [GitHub Issues](https://go.hugobatista.com/gh/kuma-scout/issues)

## Related

- [Uptime Kuma](https://github.com/louislam/uptime-kuma) - Self-hosted monitoring tool
