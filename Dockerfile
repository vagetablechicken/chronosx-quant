FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    CALENDAR_NAME=SSE \
    SCHEDULE_START=2022-01-01 \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY chronosx_quant ./chronosx_quant
COPY docker ./docker

RUN uv sync --frozen --no-dev --group docker

EXPOSE 8000

CMD ["python", "-m", "docker.service"]
