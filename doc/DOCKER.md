# Docker Deployment

Run Kuma-Scout in Docker for isolated execution and easy deployment.

## Quick Start

### Using docker-compose (Recommended)

1. Clone the repository and prepare configuration:

```bash
git clone https://go.hugobatista.com/gh/kuma-scout.git
cd kuma-scout
cp example.config.yaml config.yaml
```

2. Edit `config.yaml` with your settings

3. Run with docker-compose:

```bash
docker-compose up --build
```

### Using GHCR Image (Pre-built)

Pull and run the pre-built image from GitHub Container Registry:

```bash
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  -e UPTIME_KUMA_TOKEN=your-token \
  ghcr.io/hugobatista/kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

## Installation Options

### Option 1: docker-compose (Easiest)

```bash
docker-compose up --build -d
```

The `docker-compose.yml` file in the repository handles all setup.

### Option 2: Manual docker build

```bash
# Build image
docker build -t kuma-scout:latest .

# Run with config file
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

### Option 3: Pre-built GHCR image

```bash
# No build needed, pull from registry
docker pull ghcr.io/hugobatista/kuma-scout:latest

# Run directly
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  ghcr.io/hugobatista/kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

## Usage Examples

### Run All Checks from Config

```bash
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

### Run Single Check

```bash
docker run -it --rm \
  kuma-scout:latest \
  cmdcheck "systemctl is-active nginx" \
  --uptime-kuma-url http://uptime-kuma:3001/api/push \
  --token your-token \
  --name "nginx-health"
```

### Port Scan

```bash
docker run -it --rm \
  kuma-scout:latest \
  portscan 192.168.100.0/24 \
  --uptime-kuma-url http://uptimekuma:3001/api/push \
  --token your-portscan-token \
  --name "network-scan"
```

### With Environment Variables

Tokens support variable expansion using `${VAR}` syntax. Set any environment variables and reference them in your config:

```bash
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  -e MY_UPTIME_TOKEN=your-uptime-kuma-token \
  -e MY_HEARTBEAT_TOKEN=your-heartbeat-token \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

In your `config.yaml`, reference the variables:
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${MY_UPTIME_TOKEN}

heartbeat:
  enabled: true
  uptime_kuma:
    token: ${MY_HEARTBEAT_TOKEN}
```

### With Volume Mounts

```bash
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  -v $(pwd)/logs:/var/log/kuma-scout \
  -v ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

## Platform-Specific Examples

### Linux/macOS

```bash
docker run -it --rm \
  -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro \
  -v $(pwd)/kuma-scout.log:/var/log/kuma-scout.log \
  -e MY_HEARTBEAT_TOKEN=your-heartbeat-token \
  -e MY_PORTSCAN_TOKEN=your-portscan-token \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

Reference variables in config using `${VAR}` syntax.

### Windows (PowerShell)

```powershell
docker run -it --rm `
  -v ${pwd}/config.yaml:/etc/kuma-scout/config.yaml:ro `
  -v ${pwd}/kuma-scout.log:/var/log/kuma-scout.log `
  -e MY_HEARTBEAT_TOKEN=your-heartbeat-token `
  -e MY_PORTSCAN_TOKEN=your-portscan-token `
  kuma-scout:latest `
  run /etc/kuma-scout/config.yaml
```

Reference variables in config using `${VAR}` syntax.

## Environment Variables

Tokens support variable expansion using `${VAR}` syntax. You can use any environment variable names you choose:

**Example:** Set environment variables with custom names:
```bash
docker run -it --rm \
  -e MY_UPTIME_TOKEN=secure-token \
  -e MY_HEARTBEAT_TOKEN=heartbeat-token \
  kuma-scout:latest \
  run /etc/kuma-scout/config.yaml
```

**In config.yaml, reference them:**
```yaml
uptime_kuma:
  url: http://uptimekuma:3001/api/push
  token: ${MY_UPTIME_TOKEN}

heartbeat:
  enabled: true
  uptime_kuma:
    token: ${MY_HEARTBEAT_TOKEN}

checks:
  - name: scan
    type: portscan
    targets: 192.168.1.0/24
    uptime_kuma:
      token: ${MY_PORTSCAN_TOKEN}  # Use any variable name
```

The variable expansion happens at runtime for tokens only.

## Scheduling with Docker

### crontab

```bash
# Run every 5 minutes
*/5 * * * * docker run -it --rm -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro kuma-scout:latest run /etc/kuma-scout/config.yaml
```

### docker-compose with cron

```bash
# Run every 5 minutes
*/5 * * * * cd /path/to/kuma-scout && docker-compose run kuma-scout run /etc/kuma-scout/config.yaml
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: kuma-scout
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: kuma-scout
            image: ghcr.io/hugobatista/kuma-scout:latest
            args: ["run", "/etc/kuma-scout/config.yaml"]
            volumeMounts:
            - name: config
              mountPath: /etc/kuma-scout
          volumes:
          - name: config
            configMap:
              name: kuma-scout-config
          restartPolicy: OnFailure
```

## Configuration Files

### Volumes

- `/etc/kuma-scout/config.yaml` - Configuration file (mount read-only)
- `/var/log/kuma-scout.log` - Log file (optional)
- `/root/.ssh` - SSH keys for remote execution (optional, mount read-only)

### docker-compose

The provided `docker-compose.yml` handles volumes automatically:

```yaml
volumes:
  - ./config.yaml:/etc/kuma-scout/config.yaml:ro
  - ./kuma-scout.log:/var/log/kuma-scout.log
```

### Manual Volume Mounting

```bash
# Read-only config
docker run ... -v $(pwd)/config.yaml:/etc/kuma-scout/config.yaml:ro ...

# Writable logs
docker run ... -v $(pwd)/logs:/var/log/kuma-scout ...

# SSH keys (read-only)
docker run ... -v ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro ...
```

## Dockerfile Details

The provided [Dockerfile](../Dockerfile) includes:

- **Base Image**: `python:3.12-slim` - Minimal Python image
- **Security**: Runs as non-root user `app`
- **Requirements**: Pre-installs `nmap` for port scanning
- **Volumes**: `/var/log/kuma-scout` and `/data`
- **Healthcheck**: Uses `kuma-scout --version` as healthcheck probe

See [../Dockerfile](../Dockerfile) for full details.

## Troubleshooting

### Permission Denied

Ensure volumes are mounted with correct permissions:

```bash
# Config should be readable
chmod 644 config.yaml

# Logs directory should be writable
chmod 755 logs/
```

### SSH Key Issues

SSH keys must have correct permissions:

```bash
# Keys should be read-only to the container
chmod 600 ~/.ssh/id_rsa
```

Mount as read-only:

```bash
docker run ... -v ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro ...
```

### Network Issues

If running checks against other containers, use docker networks:

```bash
# Create network
docker network create kuma-network

# Run Uptime Kuma on network
docker run --network kuma-network --name uptime-kuma ...

# Run Kuma-Scout on same network
docker run --network kuma-network ...
  # Now can reach uptime-kuma by hostname: http://uptime-kuma:3001/api/push
```

### View Logs

```bash
# Docker run logs
docker logs <container-id>

# docker-compose logs
docker-compose logs -f

# Log file
cat logs/kuma-scout.log
```

## Image Versions

Pre-built images are available at GitHub Container Registry:

- `ghcr.io/hugobatista/kuma-scout:latest` - Latest release
- `ghcr.io/hugobatista/kuma-scout:v0.2.0` - Specific version
- `ghcr.io/hugobatista/kuma-scout:main` - Latest development build

## Building for Different Architectures

```bash
# Build for current architecture
docker build -t kuma-scout:latest .

# Build for specific architecture
docker buildx build --platform linux/amd64,linux/arm64 -t kuma-scout:latest .

# Push to registry
docker push kuma-scout:latest
```

## Further Reading

- [Configuration Guide](CONFIGURATION_GUIDE.md) - Detailed configuration options
- [CLI Usage](CLI.md) - Command-line interface documentation
- [Security](SECURITY.md) - Security considerations and best practices
