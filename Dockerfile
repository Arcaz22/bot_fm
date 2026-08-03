# ---- Builder stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy manifest dulu supaya layer ini ke-cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ---- Runtime stage ----
FROM python:3.12-slim

WORKDIR /app

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app app

# Copy virtualenv hasil build (tanpa ikut binary uv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY . .

RUN chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    APP_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
