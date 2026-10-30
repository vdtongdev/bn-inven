#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
SERVICE_PIDS=()

for command_name in uv node npm; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$command_name" >&2
    exit 1
  fi
done

stop_services() {
  local exit_status=$?
  trap - EXIT INT TERM

  for pid in "${SERVICE_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${SERVICE_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done

  exit "$exit_status"
}

trap stop_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Preparing backend dependencies...\n'
(cd "$BACKEND_DIR" && uv sync --extra dev)

if [[ ! -d "$FRONTEND_DIR/node_modules" ]] || \
  ! (cd "$FRONTEND_DIR" && node --input-type=module -e "import('rollup')" >/dev/null 2>&1); then
  printf 'Installing or repairing frontend dependencies...\n'
  # Avoid npm ci here: it removes node_modules before reinstalling, and that
  # removal previously hit EACCES in this Windows-mounted WSL workspace.
  (cd "$FRONTEND_DIR" && npm install --include=optional)
fi

printf 'Applying database migrations...\n'
(cd "$BACKEND_DIR" && uv run alembic upgrade head)

printf 'Starting API, extraction worker, and PWA. Press Ctrl+C to stop all services.\n'
printf 'App: http://localhost:5173  API: http://localhost:8000  API docs: http://localhost:8000/docs\n'

(cd "$BACKEND_DIR" && exec uv run uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0) &
SERVICE_PIDS+=("$!")
(cd "$BACKEND_DIR" && exec uv run python -m app.workers.extraction) &
SERVICE_PIDS+=("$!")
(cd "$FRONTEND_DIR" && exec npm run dev) &
SERVICE_PIDS+=("$!")

# Exit and clean up the remaining services if any one service stops unexpectedly.
wait -n "${SERVICE_PIDS[@]}"
