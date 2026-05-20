FROM node:24-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@latest

RUN (userdel -r node 2>/dev/null || true) \
    && (groupdel node 2>/dev/null || true) \
    && groupadd --gid 1000 codex \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash codex \
    && mkdir -p /app /workspace /home/codex/.codex \
    && chown -R codex:codex /app /workspace /home/codex/.codex

COPY --chown=codex:codex src/codex_openai_bridge.py /app/codex_openai_bridge.py

USER codex
WORKDIR /workspace

ENV CODEX_HOME=/home/codex/.codex \
    CODEX_BRIDGE_HOST=0.0.0.0 \
    CODEX_BRIDGE_PORT=4010 \
    CODEX_BRIDGE_WORKDIR=/workspace \
    CODEX_BRIDGE_TIMEOUT=900

EXPOSE 4010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"CODEX_BRIDGE_PORT\", \"4010\")}/health', timeout=4).read()"

CMD ["python3", "/app/codex_openai_bridge.py"]
