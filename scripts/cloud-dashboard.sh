#!/bin/sh
# Open the Dagster dashboard on your laptop, connected to the Railway database.
# It shows every cloud run (they're stored in Postgres), the asset lineage and the data checks.
#
#   ./scripts/cloud-dashboard.sh        then open http://localhost:3001
#
# Needs: the Railway CLI, logged in and linked to the fighterprints project (railway link).
# Railway injects the Postgres variables; the password never gets written to disk.
set -eu
cd "$(dirname "$0")/.."

exec railway run --service Postgres -- sh -c '
  export DAGSTER_PG_URL="$DATABASE_PUBLIC_URL"
  export UFC_DATABASE_URL="$DATABASE_PUBLIC_URL"
  eval "$(uv run python -c "
import os, shlex
from urllib.parse import urlparse
u = urlparse(os.environ[\"DATABASE_PUBLIC_URL\"])
for k, v in {\"UFC_DB_HOST\": u.hostname, \"UFC_DB_PORT\": u.port, \"UFC_DB_USER\": u.username,
             \"UFC_DB_PASSWORD\": u.password, \"UFC_DB_NAME\": u.path.lstrip(\"/\")}.items():
    print(f\"export {k}={shlex.quote(str(v))}\")
")"
  export DAGSTER_HOME="$PWD/docker/dagster-cloud"
  exec uv run dagster dev -p 3001 -m ufc.orchestration.definitions
'
