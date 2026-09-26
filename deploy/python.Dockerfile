# syntax=docker/dockerfile:1.7
# One dev image for every Python service (api, authoring-mcp, proxy, tools, agent) and the
# tests: the uv workspace with all packages installed editable from /app/packages.
FROM ghcr.io/astral-sh/uv:0.11 AS uv

FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 app && mkdir -p /app/data /opt/venv \
    && chown -R app:app /app /opt/venv
WORKDIR /app

# Dependency layer: only re-runs when a pyproject or the lockfile changes.
FROM base AS deps
USER app
COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app packages/core/pyproject.toml packages/core/
COPY --chown=app:app packages/translator/pyproject.toml packages/translator/
COPY --chown=app:app packages/server/pyproject.toml packages/server/
COPY --chown=app:app packages/mcp-proxy/pyproject.toml packages/mcp-proxy/
COPY --chown=app:app packages/lab/pyproject.toml packages/lab/
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000 \
    uv sync --frozen --all-groups --no-install-workspace

# Dev image (also used for tests): the repo is bind-mounted over /app in compose.
FROM deps AS dev
COPY --chown=app:app packages/ packages/
COPY --chown=app:app examples/ examples/
COPY --chown=app:app deploy/entrypoint.sh deploy/entrypoint.sh
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000 \
    uv sync --frozen --all-groups
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["uvicorn", "precheck.server.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/packages"]
