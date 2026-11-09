#!/usr/bin/env bash
# Deploy origin/main into this production checkout with Docker Compose.
# Run by hand (`bash deploy/deploy.sh`, or `--force` to rebuild an unchanged commit)
# or from bn-inven-deploy.timer. It refuses to run in a checkout with modified
# tracked files, so development work never happens in the production folder.
set -Eeuo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
STATE_DIR="${DEPLOY_STATE_DIR:-${HOME}/.local/state/bn-inven}"
KEEP_BACKUPS="${DEPLOY_KEEP_BACKUPS:-10}"
FORCE=0

case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  *) printf 'Usage: %s [--force]\n' "$0" >&2; exit 2 ;;
esac

log() { printf '[deploy %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

for command_name in git flock docker; do
  command -v "$command_name" >/dev/null 2>&1 || die "Missing required command: $command_name"
done

mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
if ! flock -n 9; then
  log "Another deploy is running; skipping."
  exit 0
fi

cd "$APP_DIR"
[[ -f .env ]] || die "$APP_DIR/.env is missing. Copy .env.example and fill in production values."

[[ "$(git rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] \
  || die "Checkout is not on '$BRANCH'. The production folder must track $BRANCH only."
[[ -z "$(git status --porcelain --untracked-files=no)" ]] \
  || die "Tracked files are modified. Do development in a separate clone; reset this one with 'git checkout -- .'."

git fetch --quiet origin "$BRANCH"
target="$(git rev-parse "origin/$BRANCH")"
deployed="$(cat "$STATE_DIR/deployed-commit" 2>/dev/null || true)"

if [[ "$target" == "$deployed" && "$FORCE" -eq 0 ]]; then
  log "Already deployed ${target:0:7}."
  exit 0
fi

previous="${deployed:0:7}"
log "Deploying ${target:0:7} (previous: ${previous:-none})."
git merge --ff-only --quiet "origin/$BRANCH" \
  || die "origin/$BRANCH cannot be fast-forwarded. Production never merges or rebases; inspect the checkout."

docker compose config --quiet
docker compose build --pull

log "Backing up the SQLite database before migrations."
docker compose run --rm --no-deps -T \
  -e DEPLOY_SHA="${target:0:7}" -e KEEP_BACKUPS="$KEEP_BACKUPS" \
  api python - <<'PY'
import datetime, os, pathlib, sqlite3

source = pathlib.Path("/data/bn-inven.db")
if not source.exists():
    print("No database yet; skipping backup.")
    raise SystemExit(0)
backups = pathlib.Path("/data/backups")
backups.mkdir(exist_ok=True)
stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
target = backups / f"pre-deploy-{stamp}-{os.environ['DEPLOY_SHA']}.db"
src, dst = sqlite3.connect(source), sqlite3.connect(target)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
print(f"Saved {target}")
keep = int(os.environ["KEEP_BACKUPS"])
for old in sorted(backups.glob("pre-deploy-*.db"))[:-keep]:
    old.unlink()
PY

log "Applying migrations."
docker compose run --rm --no-deps api alembic upgrade head

log "Recreating all services."
# Always recreate: Compose has been observed keeping a container on its old image
# after a rebuild, which would leave a frontend-only change undeployed.
docker compose up -d --force-recreate --remove-orphans

log "Waiting for the API health check."
for _ in $(seq 1 30); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" \
    >/dev/null 2>&1; then
    printf '%s\n' "$target" > "$STATE_DIR/deployed-commit"
    docker image prune -f >/dev/null
    log "Deployed ${target:0:7}."
    exit 0
  fi
  sleep 2
done

docker compose ps
docker compose logs --tail=50 api worker
die "API did not become healthy. The commit stays unrecorded, so the next run retries."
