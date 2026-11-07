#!/bin/sh
# Wait for PostgreSQL, apply migrations, then run the given command.
#
# Migrations belong to the API container only (the worker sets RUN_MIGRATIONS=false
# and starts after the API is healthy), so two containers never race on Alembic.
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set (see deploy/docker/.env.example)}"

echo "api-entrypoint: waiting for the database"
python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
budget = int(os.environ.get("DB_WAIT_SECONDS", "60"))
deadline = time.monotonic() + budget
last: Exception | None = None
while time.monotonic() < deadline:
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - retried until the deadline
        last = exc
        time.sleep(2)
print(f"api-entrypoint: database not reachable within {budget}s: {last}", file=sys.stderr)
sys.exit(1)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "api-entrypoint: applying migrations"
    alembic upgrade head
fi

exec "$@"
