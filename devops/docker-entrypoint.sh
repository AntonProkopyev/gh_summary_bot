#!/bin/bash

# Wait for environment variables to be available
if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: GITHUB_TOKEN environment variable is required"
    exit 1
fi

if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "ERROR: TELEGRAM_TOKEN environment variable is required"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is required"
    exit 1
fi

echo "Starting GitHub Summary Bot with supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf