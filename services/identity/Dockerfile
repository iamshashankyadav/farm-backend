# Build from the repo root:  docker build -f services/identity/Dockerfile -t farm-identity .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . .
RUN uv sync --frozen --no-dev --package farm-identity

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "identity_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
