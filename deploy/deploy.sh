#!/usr/bin/env bash
# Starts release <tag> of the images in BACKEND_IMAGE / WEB_IMAGE (deploy/.env),
# smoke-tests it and rolls back to the previous release if it isn't healthy.
#
#   ./deploy.sh 3f2c1e4            # run from deploy/ on the server (CI does this)
#   ./deploy.sh --rollback         # go back to the previous release by hand
#
# Migrations run first (the migrate service) and are NOT undone by a rollback:
# migrations must stay compatible with the previous release - see
# backend/scripts/check_migrations.py, which CI runs on every pull request.
set -euo pipefail
cd "$(dirname "$0")"

STATE=.deployed_tag
PREVIOUS_STATE=.previous_tag
SMOKE_TRIES=${SMOKE_TRIES:-40}

current() { cat "$STATE" 2>/dev/null || true; }

smoke() {
  local tag=$1
  echo "smoke test for $tag..."
  for i in $(seq 1 "$SMOKE_TRIES"); do
    if docker compose exec -T api python - "$tag" <<'PY' && \
       docker compose exec -T web node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"; then
import json, sys, urllib.request, urllib.error
try:
    body = urllib.request.urlopen("http://localhost:8000/health/ready", timeout=5).read()
except urllib.error.HTTPError as e:  # 503 = degraded: still readable
    body = e.read()
r = json.loads(body)
if r.get("release") != sys.argv[1] or r.get("checks", {}).get("database") != "ok":
    sys.exit(1)
for p in r.get("problems", []):
    print("  warning:", p)
PY
      echo "release $tag is healthy"
      return 0
    fi
    sleep 3
  done
  return 1
}

start() {
  local tag=$1; shift
  IMAGE_TAG="$tag" GIT_SHA="$tag" docker compose up -d --no-build --remove-orphans "$@"
}

# Back to an older release: only the app containers, never its (older)
# migrate step - the database is already ahead of it.
start_app() {
  local tag=$1
  IMAGE_TAG="$tag" GIT_SHA="$tag" docker compose up -d --no-build --no-deps api worker web
}

if [ "${1:-}" = "--rollback" ]; then
  target=$(cat "$PREVIOUS_STATE" 2>/dev/null || true)
  [ -n "$target" ] || { echo "no previous release recorded"; exit 1; }
  start_app "$target"
  smoke "$target"
  echo "$(current)" > "$PREVIOUS_STATE"
  echo "$target" > "$STATE"
  exit 0
fi

TAG=${1:?usage: deploy.sh <image-tag> | --rollback}
PREVIOUS=$(current)
echo "deploying $TAG (currently ${PREVIOUS:-nothing})"

# SKIP_PULL=1 uses images already on this machine (a local drill).
[ "${SKIP_PULL:-}" = "1" ] || IMAGE_TAG="$TAG" docker compose pull migrate api worker web
# Migrations first; a failed migration stops here with the old release still serving.
IMAGE_TAG="$TAG" GIT_SHA="$TAG" docker compose run --rm migrate

if start "$TAG" && smoke "$TAG"; then
  [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$TAG" ] && echo "$PREVIOUS" > "$PREVIOUS_STATE"
  echo "$TAG" > "$STATE"
  docker image prune -f --filter "until=336h" >/dev/null || true
  exit 0
fi

echo "release $TAG failed its smoke test"
docker compose logs --tail 80 api worker web || true
if [ -n "$PREVIOUS" ]; then
  echo "rolling back to $PREVIOUS (the database is left as migrated)"
  start_app "$PREVIOUS"
  smoke "$PREVIOUS" || echo "previous release is not healthy either - check the server now"
fi
exit 1
