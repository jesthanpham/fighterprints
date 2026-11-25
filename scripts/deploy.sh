#!/bin/sh
# Deploy to Railway: ./scripts/deploy.sh [web|pipeline|all]   (default: all)
#
# Both services build the same Dockerfile; each gets its own Railway config (deploy/railway.<role>.json):
# the pipeline is a weekly cron job, the web service is always on. The upload is the committed code
# (git archive HEAD) plus that role's config as railway.json, so what's deployed is what's in git.
set -eu
cd "$(dirname "$0")/.."

deploy_role() {
  role="$1"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  git archive HEAD | tar -x -C "$tmp"
  cp "deploy/railway.$role.json" "$tmp/railway.json"
  railway up "$tmp" --path-as-root --service "$role" --detach --message "deploy $(git rev-parse --short HEAD)"
  rm -rf "$tmp"
  trap - EXIT
}

case "${1:-all}" in
  web|pipeline) deploy_role "$1" ;;
  all) deploy_role pipeline; deploy_role web ;;
  *) echo "usage: $0 [web|pipeline|all]" >&2; exit 1 ;;
esac
