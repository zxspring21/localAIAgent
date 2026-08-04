#!/usr/bin/env bash
# Start MLX-LM OpenAI-compatible server (Apple Silicon M1/M2/M3/M4)
# Usage: ./scripts/start_llm_mlx.sh [model] [port]
#
# Recommended models for MacBook Air M2:
#   mlx-community/Llama-3.2-3B-Instruct-4bit   (8GB RAM, fast)
#   mlx-community/Meta-Llama-3.1-8B-Instruct-4bit (16GB+ RAM)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[mlx]${NC} $*"; }
warn() { echo -e "${YELLOW}[mlx]${NC} $*"; }
err()  { echo -e "${RED}[mlx]${NC} $*" >&2; }

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

MODEL="${1:-${LLM_DEFAULT_MODEL:-${VLLM_DEFAULT_MODEL:-mlx-community/Llama-3.2-3B-Instruct-4bit}}}"
PORT="${2:-${LLM_PORT:-8000}}"
HOST="${LLM_HOST:-127.0.0.1}"

if [[ "$(uname -s)" != "Darwin" ]] || [[ "$(uname -m)" != "arm64" ]]; then
  warn "mlx-lm is optimized for Apple Silicon (arm64 macOS)."
fi

# Prefer backend venv, then project root venv
PYTHON=""
for candidate in "$ROOT/backend/.venv/bin/python3" "$ROOT/.venv/bin/python3"; do
  if [[ -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

if ! "$PYTHON" -c "import mlx_lm" 2>/dev/null; then
  log "Installing mlx-lm..."
  "$PYTHON" -m pip install -r "$ROOT/requirements-mlx.txt"
fi

llm_health_ok() {
  curl -sf --max-time 3 "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1
}

port_pids() {
  lsof -ti ":${PORT}" 2>/dev/null || true
}

ensure_port_free() {
  local pids
  pids=$(port_pids)
  if [[ -z "$pids" ]]; then
    return 0
  fi

  if llm_health_ok; then
    log "MLX-LM already running on http://127.0.0.1:${PORT}/v1"
    log "Model endpoint ready — no need to restart."
    exit 0
  fi

  warn "Port ${PORT} is in use but not responding (stale process)."
  warn "Stopping PID(s): $(echo "$pids" | tr '\n' ' ')"
  # shellcheck disable=SC2046
  kill $(echo "$pids") 2>/dev/null || true
  sleep 2

  pids=$(port_pids)
  if [[ -n "$pids" ]]; then
    warn "Force-killing PID(s): $(echo "$pids" | tr '\n' ' ')"
    # shellcheck disable=SC2046
    kill -9 $(echo "$pids") 2>/dev/null || true
    sleep 1
  fi

  if [[ -n "$(port_pids)" ]]; then
    err "Port ${PORT} still in use. Run manually:"
    err "  lsof -i :${PORT}"
    err "  kill \$(lsof -ti :${PORT})"
    exit 1
  fi
}

prefetch_model() {
  log "Ensuring model is cached (first run downloads from Hugging Face)..."
  "$PYTHON" <<PY
import sys
try:
    from huggingface_hub import snapshot_download
    path = snapshot_download("${MODEL}")
    print(f"Model cached at: {path}", flush=True)
except Exception as e:
    print(f"WARNING: model prefetch failed: {e}", file=sys.stderr, flush=True)
    print("Server will retry download on startup.", flush=True)
PY
}

wait_for_server() {
  local i
  for i in $(seq 1 120); do
    if llm_health_ok; then
      log "Server ready: http://127.0.0.1:${PORT}/v1"
      return 0
    fi
    sleep 2
  done
  warn "Server started but /v1/models not responding yet (model may still be loading)."
  return 0
}

ensure_port_free
prefetch_model

log "Starting MLX-LM server (Apple Silicon)..."
echo "  Python:  $("$PYTHON" -c 'import sys; print(sys.executable)')"
echo "  Model:   ${MODEL}"
echo "  API:     http://127.0.0.1:${PORT}/v1"
echo ""

# When invoked directly, run in foreground. When sourced with RUN_IN_BACKGROUND=1, caller manages PID.
if [[ "${RUN_IN_BACKGROUND:-0}" == "1" ]]; then
  "$PYTHON" -m mlx_lm server \
    --model "${MODEL}" \
    --host "${HOST}" \
    --port "${PORT}" &
  SERVER_PID=$!
  log "MLX server PID: ${SERVER_PID}"
  wait_for_server
  exit 0
fi

exec "$PYTHON" -m mlx_lm server \
  --model "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}"
