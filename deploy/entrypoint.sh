#!/bin/sh
# Container entrypoint: prepare data dir + run DB migrations (once they exist), then exec CMD.
set -e
mkdir -p /app/data
if [ -f /app/packages/server/alembic.ini ] && [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic -c /app/packages/server/alembic.ini upgrade head
fi
exec "$@"
