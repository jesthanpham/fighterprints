#!/bin/sh
# Open the Dagster dashboard on your laptop, connected to the Railway database.
# It shows every cloud run (they're stored in Postgres), the asset lineage and the data checks.
#
#   ./scripts/cloud-dashboard.sh        then open http://localhost:3001   (Ctrl+C to stop)
#
# Needs the Railway CLI (logged in, `railway link`ed) and Postgres public access enabled
# (password-protected, SSL). Railway injects the credentials; nothing is written to disk.
set -eu
cd "$(dirname "$0")/.."

exec railway run --service Postgres -- sh -c '
  env_lines="$(uv run python scripts/cloud_env.py)" || exit 1
  eval "$env_lines"
  export DAGSTER_HOME="$PWD/docker/dagster-cloud"
  exec uv run dagster dev -p 3001 -m ufc.orchestration.definitions
'
