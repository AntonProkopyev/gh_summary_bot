# DevOps

This directory contains deployment and infrastructure configuration files.

## Files

- **`Dockerfile`** - Docker container configuration
- **`supervisord.conf`** - Process management with log rotation
- **`docker-entrypoint.sh`** - Container startup script with env validation

## Usage

Build and run the Docker container:

```bash
# Build
docker build -f devops/Dockerfile -t gh-summary-bot .

# Run
docker run -e GITHUB_TOKEN=xxx -e TELEGRAM_TOKEN=xxx -e DATABASE_URL=xxx gh-summary-bot
```

## Log Management

Supervisord handles automatic log rotation:
- Max 50MB per log file
- Keeps 10 backup files
- Separate stdout/stderr logs