FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY gh_summary_bot/ ./gh_summary_bot/

# Install uv and dependencies
RUN pip install uv
RUN uv sync --frozen

# Create supervisord configuration
RUN mkdir -p /var/log/supervisor

# Copy supervisord configuration
COPY devops/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create startup script
COPY devops/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose port (if needed for health checks)
EXPOSE 8080

# Run supervisord
CMD ["/usr/local/bin/docker-entrypoint.sh"]