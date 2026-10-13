FROM python:3.11-slim-bookworm
ARG CODEX_VERSION=0.156.1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LITMAN_ANALYSIS_RUNS_DIR=/data/runs LITMAN_ANALYSIS_WORKSPACE_DIR=/tmp/litman-analysis HOME=/tmp/litman-analysis/home CODEX_HOME=/var/lib/litman-analysis/codex
RUN apt-get update && apt-get install --no-install-recommends -y chromium nodejs npm ripgrep && npm install --global "@openai/codex@${CODEX_VERSION}" && ln -s /usr/bin/chromium /usr/local/bin/google-chrome && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir "." && useradd --uid 10001 --no-create-home litman && mkdir -p /tmp/litman-analysis/workspaces /var/lib/litman-analysis/codex /data/runs && chown -R litman:litman /var/lib/litman-analysis /data/runs && chmod -R a+rX /app /usr/local/lib/node_modules && chmod 1777 /tmp/litman-analysis /tmp/litman-analysis/workspaces
USER litman
ENTRYPOINT ["litman-core"]
