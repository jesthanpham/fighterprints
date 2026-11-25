#!/bin/sh
# Deploy to Railway: ./scripts/deploy.sh [web|pipeline|all]   (default: all)
#
# Both services build the same Dockerfile from the committed code (git archive HEAD), so what's
# deployed is exactly what's in git. UFC_ROLE (set on each Railway service) picks web vs pipeline.
# Service settings live in Railway itself: the pipeline's weekly cron (0 15 * * 0 = Sundays 15:00 UTC)
# was set in the dashboard, because Railway doesn't read railway.json from CLI uploads.
set -eu
cd "$(dirname "$0")/.."

deploy_role() {
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  git archive HEAD | tar -x -C "$tmp"
  railway up "$tmp" --path-as-root --service "$1" --detach --message "deploy $(git rev-parse --short HEAD)"
  rm -rf "$tmp"
  trap - EXIT
}

case "${1:-all}" in
  web|pipeline) deploy_role "$1" ;;
  all) deploy_role pipeline; deploy_role web ;;
  *) echo "usage: $0 [web|pipeline|all]" >&2; exit 1 ;;
esac
