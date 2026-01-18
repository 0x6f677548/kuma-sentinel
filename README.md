# Kuma Sentinel

Extensible monitoring agent with Uptime Kuma integration. Currently includes port scanning with heartbeat health monitoring.

A Python CLI tool that scans specified IP ranges for open TCP ports using nmap and reports the results to Uptime Kuma with separate push tokens for heartbeat monitoring and port-scan alerts. Designed to be extended with additional monitoring checks like ZFS pools, disk space, etc.

## Features

- **Nmap Integration**: Powerful network scanning with configurable port ranges and timing profiles
- **Uptime Kuma Integration**: Reports scan results and health status to Uptime Kuma monitoring
- **Heartbeat Monitoring**: Sends periodic heartbeat pings during long scans to signal agent health and activity
- **Flexible Configuration**: Support for INI config files, environment variables, and CLI arguments with clear priority
- **Multi-Source Configuration**:
  1. Command-line arguments (highest priority)
  2. INI config file
  3. Environment variables
  4. Hardcoded defaults (lowest priority)
- **Comprehensive Logging**: File, console, and syslog/journalctl output
- **Exclusion Lists**: Exclude specific IPs/ranges from scans
- **Extensible Architecture**: Built to support additional monitoring checks beyond port scanning

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
  -v $(pwd)/config.ini:/etc/kuma-sentinel/config.ini:ro \
  -v $(pwd)/logs:/var/log/kuma-sentinel \
  kuma-sentinel:latest \
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token

# Windows (PowerShell)
docker run -it --rm `
  -v ${pwd}/config.ini:/etc/kuma-sentinel/config.ini:ro `
  -v ${pwd}/logs:/var/log/kuma-sentinel `
  kuma-sentinel:latest `
  portscan 192.168.100.110-199 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token
```

## Usage

### Port Scan

```bash
kuma-sentinel portscan 192.168.1.0/24 http://uptimekuma:3001/api/push your-heartbeat-token your-portscan-token
```


### With Custom Ports and Timing

```bash
kuma-sentinel portscan \
  --ports 22,80,443,3389 \
  --timing T4 \
  192.168.100.0/24 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

### Multiple IP Ranges

```bash
kuma-sentinel portscan \
  192.168.1.0/24 \
  10.0.0.0/8 \
  172.16.0.0/12 \
  http://uptimekuma:3001/api/push \
  your-heartbeat-token \
  your-portscan-token
```

### Using Configuration File

```bash
kuma-sentinel portscan --config /etc/kuma-sentinel/config.ini
```

### With Exclusions

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
```

## Configuration

### INI File Format

Default location: `/etc/kuma-sentinel/config.ini`

```ini
[logging]
log_file = /var/log/kuma-sentinel.log

[heartbeat]
enabled = true
interval = 300

[uptime_kuma]
url = http://uptimekuma:3001/api/push
heartbeat_token = your-heartbeat-token
portscan_token = your-portscan-token

[portscan.nmap]
timing = T3
arguments = 
keep_xml_output = false

[portscan.targets]
ports = 1-1000
exclude_ips = 192.168.1.1,192.168.1.254
ip_ranges = 192.168.1.0/24,10.0.0.0/8
```

### Environment Variables

```bash
KUMA_SENTINEL_LOG_FILE=/var/log/kuma-sentinel.log
KUMA_SENTINEL_HEARTBEAT_ENABLED=true
KUMA_SENTINEL_HEARTBEAT_INTERVAL=300
KUMA_SENTINEL_NMAP_PORTS=1-1000
KUMA_SENTINEL_NMAP_TIMING=T3
KUMA_SENTINEL_NMAP_EXCLUDE_IPS=192.168.1.1
KUMA_SENTINEL_NMAP_ARGUMENTS=--script vuln
KUMA_SENTINEL_NMAP_KEEP_XMLOUTPUT=false
```

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
*/30 * * * * kuma-sentinel portscan --config /etc/kuma-sentinel/config.ini
```

### Systemd Timer Example

Create `/etc/systemd/system/kuma-sentinel.service`:

```ini
[Unit]
Description=Kuma Sentinel Monitoring Agent
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/kuma-sentinel portscan --config /etc/kuma-sentinel/config.ini
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
2. **Console**: Standard output for direct execution
3. **Journalctl**: Syslog integration for systemd systems

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

- Python 3.7+
- nmap (must be installed on system and in PATH)
- click (installed automatically)

## Development

### Setup

```bash
git clone https://go.hugobatista.com/gh/kuma-sentinel.git
cd kuma-sentinel
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
pytest --cov=src/kuma_sentinel
pytest -v
```

### Code Quality

```bash
# Lint with ruff
ruff check src/ tests/

# Format with black
black src/ tests/

# Fix linting issues
ruff check --fix src/ tests/
```

### Building Package

```bash
python -m pip install build
python -m build
```

## License

MIT License - See [LICENSE](LICENSE) file for details

## Author

Hugo Batista - [GitHub](https://go.hugobatista.com/gh)

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run tests and linting
6. Submit a pull request

## Issues

Found a bug? Report it on [GitHub Issues](https://go.hugobatista.com/gh/kuma-sentinel/issues)

## Related Projects

- [Uptime Kuma](https://github.com/louislam/uptime-kuma) - Self-hosted monitoring tool
- [Nmap](https://nmap.org/) - Network mapper and security scanner
- [Click](https://click.palletsprojects.com/) - Python CLI framework
