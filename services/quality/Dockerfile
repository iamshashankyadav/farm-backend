# Build from the repo root:  docker build -f services/quality/Dockerfile -t farm-quality .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . .
RUN uv sync --frozen --no-dev --package farm-quality

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "quality_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
