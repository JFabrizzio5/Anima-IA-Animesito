#!/usr/bin/env bash
# Local development inside WSL: datastores, migrations, worker, Vite and the API.
#
#   bash scripts/dev.sh            # http://localhost:7799 (Vite) -> API on :7789
#
# ComfyUI and Ollama run natively on Windows; with WSL in mirrored networking
# they answer on 127.0.0.1 here too. Ctrl+C stops everything this started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/bin:$HOME/.jfast-toolchains/node/bin:$PATH"
export PYTHONUNBUFFERED=1

# Killing the Windows-side wsl.exe does not signal the Linux processes it
# started, so a previous run can still hold the ports. Clear them first.
pkill -f "$ROOT/animesito/.venv/bin/uvicorn main:app" 2>/dev/null || true
pkill -f "$ROOT/animesito/.venv/bin/jfast worker" 2>/dev/null || true
pkill -f "$ROOT/animesito-web/node_modules/.bin/vite" 2>/dev/null || true
sleep 0.5

cd "$ROOT"
set -a
# shellcheck disable=SC1091
. ./.env
set +a

docker compose -p animesito up -d animesito-database animesito-cache
for _ in $(seq 1 30); do
  docker compose -p animesito exec -T animesito-database pg_isready -U app >/dev/null 2>&1 && break
  sleep 1
done

cd "$ROOT/animesito"
.venv/bin/alembic upgrade head

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

# --pdeathsig: each child gets SIGTERM when this script dies, however it dies.
run() { setpriv --pdeathsig TERM -- "$@" & pids+=($!); }

run "$ROOT/animesito/.venv/bin/jfast" worker --concurrency 2 --grace 10
run "$ROOT/animesito-web/node_modules/.bin/vite" "$ROOT/animesito-web" \
  --port 7799 --host 127.0.0.1 --strictPort
# The SSE stream holds a connection open for as long as the tab lives; without a
# graceful-shutdown timeout every --reload waits for the browser to give up.
run "$ROOT/animesito/.venv/bin/uvicorn" main:app --host 127.0.0.1 --port 7789 \
  --no-proxy-headers --reload --timeout-graceful-shutdown 2

wait -n
