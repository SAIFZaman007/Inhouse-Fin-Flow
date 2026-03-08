# ════════════════════════════════════════════════════════════════════════════
#  MAKTech FinFlow — Production Dockerfile
#  Stack : FastAPI · Prisma Python Client · PostgreSQL · Poetry
#  Build : python:3.11-slim  →  multi-stage  →  lean production image
# ════════════════════════════════════════════════════════════════════════════


# ── Stage 1 : Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry-cache \
    PRISMA_BINARY_CACHE_DIR=/prisma-binaries

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
        libpq-dev \
        curl \
        libatomic1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN pip install --no-cache-dir "poetry==2.3.1"

COPY pyproject.toml poetry.lock ./

RUN poetry install --only main --no-root \
    && rm -rf /tmp/poetry-cache

COPY prisma/ ./prisma/
RUN prisma generate

COPY app/ ./app/


# ── Stage 2 : Lean production runtime ────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="MAKTech FinFlow API" \
      org.opencontainers.image.description="Enterprise Finance Management API" \
      org.opencontainers.image.vendor="MAKTech" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PRISMA_BINARY_CACHE_DIR=/prisma-binaries

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libatomic1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --shell /bin/sh --create-home appuser

WORKDIR /app

COPY --from=builder \
    /usr/local/lib/python3.11/site-packages \
    /usr/local/lib/python3.11/site-packages

COPY --from=builder /usr/local/bin/prisma  /usr/local/bin/prisma
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

COPY --from=builder --chown=appuser:appuser \
    /prisma-binaries /prisma-binaries

COPY --from=builder --chown=appuser:appuser \
    /build/prisma ./prisma

COPY --from=builder --chown=appuser:appuser \
    /build/app ./app

RUN chown -R appuser:appuser /app

RUN printf '#!/bin/sh\nset -e\necho "[finflow] Running prisma migrate deploy..."\n/usr/local/bin/prisma migrate deploy\necho "[finflow] Starting uvicorn..."\nexec /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1} --log-level ${LOG_LEVEL:-info}\n' \
    > /start.sh && chmod +x /start.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/bin/sh", "/start.sh"]