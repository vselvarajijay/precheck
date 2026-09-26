# syntax=docker/dockerfile:1.7
FROM node:24-slim AS base
RUN corepack enable && corepack install -g pnpm@12.6.0
WORKDIR /app
RUN chown node:node /app
USER node

FROM base AS deps
COPY --chown=node:node frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/home/node/.local/share/pnpm/store,uid=1000 \
    pnpm install --frozen-lockfile

# Dev server (source bind-mounted over /app in compose; node_modules stays in the image).
FROM deps AS dev
COPY --chown=node:node frontend/ ./
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

# Playwright runner: browsers preinstalled in the official image (version matches package.json).
FROM mcr.microsoft.com/playwright:v1.63.0-noble AS e2e
RUN corepack enable && corepack install -g pnpm@12.6.0
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
CMD ["pnpm", "exec", "playwright", "test"]
