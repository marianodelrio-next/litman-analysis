FROM python:3.11-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LITMAN_CORE_WORKSPACE_DIR=/tmp/litman-core HOME=/tmp/litman-core/home CODEX_HOME=/var/lib/litman-core/codex
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-deps --no-cache-dir --wheel-dir /dist .

FROM python:3.11-slim-bookworm
ARG CODEX_VERSION=0.156.1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LITMAN_CORE_WORKSPACE_DIR=/tmp/litman-core HOME=/tmp/litman-core/home CODEX_HOME=/var/lib/litman-core/codex
RUN apt-get update && apt-get install --no-install-recommends -y chromium nodejs npm ripgrep && npm install --global "@openai/codex@${CODEX_VERSION}" && ln -s /usr/bin/chromium /usr/local/bin/google-chrome && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /dist/litman_core-*.whl /tmp/
RUN pip install --no-cache-dir /tmp/litman_core-*.whl && useradd --uid 10001 --no-create-home litman && mkdir -p /tmp/litman-core/workspaces /var/lib/litman-core/codex && chown -R litman:litman /var/lib/litman-core && chmod -R a+rX /usr/local/lib/node_modules && chmod 1777 /tmp/litman-core /tmp/litman-core/workspaces
USER litman
ENTRYPOINT ["litman-core"]
