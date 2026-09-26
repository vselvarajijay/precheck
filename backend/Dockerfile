# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11 AS uv

FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 app && mkdir -p /app/backend /app/data /opt/venv \
    && chown -R app:app /app /opt/venv
WORKDIR /app/backend

# Dependency layer: only re-runs when the lockfile changes.
FROM base AS deps
USER app
COPY --chown=app:app backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000 \
    uv sync --frozen --no-install-project

# Dev image (also used for tests): source is bind-mounted over /app/backend in compose.
FROM deps AS dev
COPY --chown=app:app backend/ ./
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000 \
    uv sync --frozen
EXPOSE 8000
ENTRYPOINT ["/app/backend/scripts/entrypoint.sh"]
CMD ["uvicorn", "precheck.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend/src"]
