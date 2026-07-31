FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# Keine Node.js-Runtime im Backend-Image (F-049): der einzige Node-Bedarf war der
# Notion-MCP-Server, und Notion ist mit dem Doctus-Fork entfallen. mcp-atlassian
# (Jira/Confluence) ist reines Python über requirements.txt.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

# Baked in at build time so GET /version can report what's actually running
# without relying on a bind-mounted .git dir (there isn't one in production).
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIME=$BUILD_TIME

ENTRYPOINT ["./docker-entrypoint.sh"]
