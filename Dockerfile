FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime

RUN useradd -u 1000 -m app
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY backend/app /app/app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

USER app
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
