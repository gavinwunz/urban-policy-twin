#!/usr/bin/env bash
#
# GOV SIM dev runner — boots the backend (FastAPI/uvicorn) and the frontend
# (Next.js) together for local development, with one-line setup on first run.
#
# Usage:
#   ./scripts/dev.sh            # set up (if needed) + run backend + frontend
#   ./scripts/dev.sh backend    # backend only
#   ./scripts/dev.sh frontend   # frontend only
#   ./scripts/dev.sh setup      # install deps + generate dataset, then exit
#
# Env overrides:
#   BACKEND_PORT   (default 8000)
#   FRONTEND_PORT  (default 3000)
#   SKIP_INSTALL=1 skip dependency installation
#
# Ctrl-C stops both processes cleanly.

set -euo pipefail

# --- locate repo root (this script lives in <root>/scripts) ---------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-3000}"
VENV="$ROOT/backend/.venv"

# --- pretty logging -------------------------------------------------------
c_reset=$'\033[0m'; c_blue=$'\033[34m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'
log()  { printf '%s[dev]%s %s\n' "$c_blue" "$c_reset" "$*"; }
ok()   { printf '%s[dev]%s %s\n' "$c_green" "$c_reset" "$*"; }
warn() { printf '%s[dev]%s %s\n' "$c_yellow" "$c_reset" "$*"; }

# --- dependency checks ----------------------------------------------------
need() { command -v "$1" >/dev/null 2>&1 || { warn "missing '$1' — please install it"; exit 1; }; }

python_bin() {
  if command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi
}

setup_backend() {
  local py; py="$(python_bin)"
  if [ ! -d "$VENV" ]; then
    log "creating backend virtualenv ($VENV)"
    "$py" -m venv "$VENV"
  fi
  if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    log "installing backend requirements"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$ROOT/backend/requirements.txt"
  fi
  # Generate the synthetic city dataset if it's missing (it is normally committed).
  if [ ! -f "$ROOT/data/city/manifest.json" ]; then
    log "generating synthetic city dataset"
    "$py" "$ROOT/data/generate_city.py"
  fi
  # Generate the synthetic commuter population if it's missing (SPEC §6).
  if [ ! -f "$ROOT/data/city/population.json" ]; then
    log "generating synthetic population"
    "$py" "$ROOT/data/generate_population.py"
  fi
  # Generate the prebuilt 3D city if it's missing. Also mirrors into
  # frontend/public/city/, which is what the 3D scene fetches.
  if [ ! -f "$ROOT/frontend/public/city/buildings.geojson" ]; then
    log "generating prebuilt 3D city"
    "$py" "$ROOT/data/generate_buildings.py"
  fi
  ok "backend ready"
}

setup_frontend() {
  need node
  if [ "${SKIP_INSTALL:-0}" != "1" ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
    log "installing frontend dependencies (npm install)"
    (cd "$ROOT/frontend" && npm install --silent)
  fi
  ok "frontend ready"
}

run_backend() {
  log "starting backend on http://localhost:$BACKEND_PORT (docs: /docs)"
  cd "$ROOT/backend"
  exec "$VENV/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
}

run_frontend() {
  log "starting frontend on http://localhost:$FRONTEND_PORT"
  cd "$ROOT/frontend"

  # `next build` and `next dev` share the .next directory but write different
  # chunk names: a production build leaves hashed files (main-app-<hash>.js)
  # where dev expects unhashed ones, so dev then serves HTML referencing chunks
  # that 404. React never hydrates and every client component is stuck on its
  # server-rendered placeholder — a blank page with no console error to explain
  # it. BUILD_ID only exists in a production build, so it is the tell.
  if [ -f .next/BUILD_ID ]; then
    warn "clearing .next — it holds a production build, which breaks next dev"
    rm -rf .next
  fi

  # Point the browser client at the backend unless the caller already set it.
  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:$BACKEND_PORT}"
  exec npm run dev -- --port "$FRONTEND_PORT"
}

# --- process management for the combined run ------------------------------
# Each child is launched in its own session/process group (setsid) so we can
# kill the whole tree — uvicorn's reloader and next-server run as grandchildren
# that a plain `kill <pid>` would leave orphaned.
pids=()
cleaned=0
cleanup() {
  [ "$cleaned" = 1 ] && return; cleaned=1
  log "shutting down…"
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] || continue
    kill -KILL "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

run_both() {
  setup_backend
  setup_frontend
  trap cleanup INT TERM EXIT

  # Children re-enter this script per-service; setup already ran, so skip installs.
  # Each is launched via `setsid` as a direct background job so (a) `wait` can
  # reap it and (b) `$!` is the new group's PGID, letting cleanup kill the whole
  # tree. Backgrounding must NOT happen inside $(...) — that reparents the job.
  export SKIP_INSTALL=1
  setsid bash "$SCRIPT_DIR/dev.sh" backend &
  pids+=("$!")
  setsid bash "$SCRIPT_DIR/dev.sh" frontend &
  pids+=("$!")

  ok "backend → http://localhost:$BACKEND_PORT   frontend → http://localhost:$FRONTEND_PORT"
  log "press Ctrl-C to stop both"
  # Exit as soon as either child dies so a crash is visible, not silently hung.
  wait -n
  cleanup
}

case "${1:-all}" in
  setup)     setup_backend; setup_frontend; ok "setup complete" ;;
  backend)   setup_backend; run_backend ;;
  frontend)  setup_frontend; run_frontend ;;
  all|"")    run_both ;;
  *) warn "unknown command '$1' (use: all|setup|backend|frontend)"; exit 1 ;;
esac
