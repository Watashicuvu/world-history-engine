FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project

COPY . .

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create dirs for logs and output
RUN mkdir -p world_output

# 8000 - Web UI / API
# 8001 - MCP Server (SSE)
EXPOSE 8000 8001

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
