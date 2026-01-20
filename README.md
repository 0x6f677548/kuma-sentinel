[![PyPI - Version](https://img.shields.io/pypi/v/kuma-sentinel.svg)](https://pypi.org/project/kuma-sentinel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kuma-sentinel.svg)](https://pypi.org/project/kuma-sentinel)
[![Deploy to ghcr.io](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/build-and-publish-to-ghcr.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/build-and-publish-to-ghcr.yml)
[![Deploy to PyPI](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/build-and-publish-to-pypi.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/build-and-publish-to-pypi.yml)
[![Lint](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/lint.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/lint.yml)
[![Test](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/test.yml/badge.svg)](https://go.hugobatista.com/gh/kuma-sentinel/actions/workflows/test.yml)
[![GitMCP](https://img.shields.io/endpoint?url=https://gitmcp.io/badge/0x6f677548/kuma-sentinel)](https://gitmcp.io/0x6f677548/kuma-sentinel)


# Kuma-Sentinel

Extensible remote monitoring CLI tool for Uptime Kuma. Monitor various system conditions and push results to Uptime Kuma push monitors.

Useful for evaluating system health on remote machines and reporting back to a central Uptime Kuma instance. Currently includes:
- **Port scanning** - Scan TCP ports across IP ranges using nmap
- **Backup monitoring** - Check Kopia snapshot freshness and status

## Overview
A Python CLI tool that monitors system conditions locally and reports the results to a central Uptime Kuma instance with separate push tokens for heartbeat monitoring and alerting. Install on remote machines and run via cron jobs, systemd timers, or custom services to periodically check conditions like:
- **Port accessibility** - Verify expected ports are open/closed, detect exposed ports
- **Backup freshness** - Monitor Kopia snapshot age and completeness
- **System health** - Extensible design supports additional checks (ZFS pools, disk space, etc.)

Designed to be extended with additional monitoring checks and custom checkers.

## Diagram

```plaintext
┌─────────────────────────────┐
│   Monitoring Machine        │
│   (Kuma Sentinel)           │
│                             │
│  • Port Scanning (nmap)     │
│  • Backup Monitoring (Kopia)│
│  • Custom Checks (extensible)
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


## Features

- **Remote Monitoring**: Execute monitoring checks on remote systems and push results to Uptime Kuma
- **Port Scanning**: Scan TCP ports across IP ranges using nmap with configurable ports, timing profiles, and exclusion lists
- **Backup Monitoring**: Monitor Kopia backup snapshot freshness, detect stale or missing snapshots
- **Heartbeat Monitoring**: Sends periodic heartbeat pings during long operations to signal agent health and activity
- **Uptime Kuma Integration**: Reports monitoring results and health status to Uptime Kuma push monitors
- **Flexible Configuration**: Support for YAML config files, environment variables, and CLI arguments with clear priority
- **Multi-Source Configuration**:
  1. Command-line arguments (highest priority)
  2. YAML config file
  3. Environment variables
  4. Hardcoded defaults (lowest priority)
- **Comprehensive Logging**: File, console, and syslog/journalctl output
- **Extensible Architecture**: Built to support additional monitoring checks (ZFS pools, disk space, system metrics, etc.)

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

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` with your configuration:

```bash
# Set your Uptime Kuma URL and tokens
export UPTIME_KUMA_URL=http://uptimekuma:3001/api/push
export UPTIME_KUMA_HEARTBEAT_TOKEN=your-heartbeat-token
export UPTIME_KUMA_PORTSCAN_TOKEN=your-portscan-token
```

3. Build and run:

```bash
docker-compose up --build -it
```

4. Run a scan inside the container:

```bash
docker-compose exec kuma-sentinel portscan 192.168.100.110-199 $UPTIME_KUMA_URL $UPTIME_KUMA_HEARTBEAT_TOKEN $UPTIME_KUMA_PORTSCAN_TOKEN
```

#### Using docker run directly

```bash
docker build -t kuma-sentinel:latest .

# Linux/macOS
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-sentinel/config.yaml:ro \
  -v $(pwd)/logs:/var/log/kuma-sentinel \
  kuma-sentinel:latest \
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token

# Windows (PowerShell)
docker run -it --rm `
  -v ${pwd}/config.yaml:/etc/kuma-sentinel/config.yaml:ro `
  -v ${pwd}/logs:/var/log/kuma-sentinel `
  kuma-sentinel:latest `
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token
```

## Usage

### Port Scan

```bash
kuma-sentinel portscan 192.168.1.0/24 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token
```

### Kopia Snapshot Status

Monitor Kopia backup snapshot freshness with per-path age thresholds:

```bash
# Using configuration file (recommended)
kuma-sentinel kopiasnapshotstatus --config /etc/kuma-sentinel/config.yaml

# Or with CLI arguments
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48
```

Multiple snapshots with different age requirements:
```bash
kuma-sentinel kopiasnapshotstatus \
  --snapshot /data 24 \
  --snapshot /backups 48 \
  --snapshot /archive 168
```

## Use Cases

### Network Security Monitoring

Monitor ports on your local machine or network to ensure no unauthorized ports are exposed. Deploy Kuma Sentinel on your watchdog/monitoring machines and schedule it to run periodically via cron or systemd timer to push results to your central Uptime Kuma instance.

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
  targets:
    snapshots:
      - path: /data
        max_age_hours: 24      # Critical data - must be backed up daily
      - path: /backups
        max_age_hours: 48      # Important - allow 2 days
      - path: /archive
        max_age_hours: 168     # Archive - allow 1 week
    max_age_hours: 24          # Global default
```

**Result**:
- ✅ If all snapshots are fresh (within their thresholds) → Uptime Kuma shows UP
- ⚠️ If any snapshot is stale → Uptime Kuma shows DOWN and triggers alerts
- 📊 Details include age of each snapshot and its threshold for visibility

### Common Usage Examples

#### With Custom Ports and Timing

```bash
kuma-sentinel portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  192.168.100.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

#### Multiple IP Ranges

```bash
kuma-sentinel portscan \
  192.168.1.0/24 \
  10.0.0.0/8 \
  172.16.0.0/12 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

#### Using Configuration File

```bash
kuma-sentinel portscan --config /etc/kuma-sentinel/config.yaml
```

#### With Exclusions

```bash
kuma-sentinel portscan \
  --exclude 192.168.1.1,192.168.1.254 \
  192.168.1.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

### Help

```bash
kuma-sentinel --help
kuma-sentinel portscan --help
kuma-sentinel kopiasnapshotstatus --help
```

## Configuration

### YAML File Format

Default location: `/etc/kuma-sentinel/config.yaml`

```yaml
logging:
  log_file: /var/log/kuma-sentinel.log
  log_level: INFO

heartbeat:
  enabled: true
  interval: 300
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
  
  targets:
    ports: 1-1000
    exclude: [192.168.1.1, 192.168.1.254]
    ip_ranges:
      - 192.168.1.0/24
      - 10.0.0.0/8

kopiasnapshotstatus:
  uptime_kuma:
    token: your-kopia-token
  
  targets:
    # List of snapshots with per-path maximum age thresholds
    # Each snapshot can have a different age requirement
    snapshots:
      - path: /data
        max_age_hours: 24
      - path: /backups
        max_age_hours: 48
      - path: /archive
        # Omit max_age_hours to use the global default (24)
    
    # Global default for snapshots without explicit max_age_hours
    max_age_hours: 24
```

### Environment Variables

```bash
# Logging
KUMA_SENTINEL_LOG_FILE=/var/log/kuma-sentinel.log
KUMA_SENTINEL_LOG_LEVEL=INFO

# Heartbeat (shared across all commands)
KUMA_SENTINEL_HEARTBEAT_ENABLED=true
KUMA_SENTINEL_HEARTBEAT_INTERVAL=300
KUMA_SENTINEL_HEARTBEAT_TOKEN=your-heartbeat-token

# Port Scan Command
KUMA_SENTINEL_PORTSCAN_NMAP_PORTS=1-1000
KUMA_SENTINEL_PORTSCAN_NMAP_TIMING=T3
KUMA_SENTINEL_PORTSCAN_NMAP_TIMEOUT=3600
KUMA_SENTINEL_PORTSCAN_EXCLUDE="192.168.1.1,192.168.1.254"
KUMA_SENTINEL_PORTSCAN_NMAP_ARGUMENTS=--script vuln
KUMA_SENTINEL_PORTSCAN_NMAP_KEEP_XMLOUTPUT=false
KUMA_SENTINEL_PORTSCAN_TOKEN=your-portscan-token

# Kopia Snapshot Status Command
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_MAX_AGE_HOURS=24
KUMA_SENTINEL_KOPIASNAPSHOTSTATUS_TOKEN=your-kopia-token
```

**Configuration Priority**: CLI arguments > YAML file > Environment variables > Defaults

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

## Nmap Timing Profiles

- `T0`: Paranoid - Very slow, useful for IDS evasion
- `T1`: Sneaky - Slow, IDS evasion
- `T2`: Polite - Slowed to minimize network load
- `T3`: Normal - Default, no delays
- `T4`: Aggressive - Fast, assumes reasonable network
- `T5`: Insane - Very fast, assumes excellent network

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
