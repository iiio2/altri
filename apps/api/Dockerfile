# syntax=docker/dockerfile:1
# Build from the repo root: docker build -f apps/api/Dockerfile .
# The repo layout is kept (/app/apps/api, /app/docs/seed.json) because altri_api.config resolves the repo root
# from its own file path; the project is therefore installed editable, pointing at /app/apps/api/src.

FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/api/.venv/bin:$PATH"

WORKDIR /app/apps/api

# Dependencies first, so source edits don't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=apps/api/uv.lock,target=uv.lock \
    --mount=type=bind,source=apps/api/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini ./
COPY apps/api/migrations ./migrations
COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Seed data (git-ignored docs/ — must exist locally when building).
COPY docs/seed.json /app/docs/seed.json

RUN useradd --no-create-home --uid 10001 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "altri_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
