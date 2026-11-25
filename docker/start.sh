#!/bin/sh
# One image, two Railway services. UFC_ROLE picks what this container does.
#   web       the public website (Railway gives us $PORT)
#   pipeline  one full pipeline run, then exit (Railway's cron starts it weekly)
set -eu

case "${UFC_ROLE:-}" in
  web)
    set -- streamlit run app/streamlit_app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0 --server.headless true
    ;;
  pipeline)
    set -- dagster asset materialize --select '*' -m ufc.orchestration.definitions
    ;;
  *)
    echo "UFC_ROLE must be 'web' or 'pipeline' (got '${UFC_ROLE:-}')" >&2
    exit 1
    ;;
esac

if [ "${UFC_DRY_RUN:-}" = "1" ]; then
  echo "$@"
  exit 0
fi
exec "$@"
