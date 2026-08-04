#!/usr/bin/env bash
# One-command dev launcher for LocalAI Agent
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[localai]${NC} $*"; }
warn() { echo -e "${YELLOW}[localai]${NC} $*"; }

chmod +x scripts/start_vllm.sh scripts/start_llm_mlx.sh scripts/start_dev.sh

# ── 1. Environment ──────────────────────────────────────────────
if [[ ! -f .env ]]; then
  log "Creating .env from .env.example"
  cp .env.example .env
fi
# shellcheck disable=SC1091
source .env

LLM_BACKEND="${LLM_BACKEND:-mlx}"

# ── 2. Infrastructure (Docker) ───────────────────────────────────
log "Starting infrastructure (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant 2>/dev/null || {
  warn "Docker compose failed — make sure Docker is running."
}

log "Waiting for services to be healthy..."
for i in $(seq 1 30); do
  pg_ok=$(docker compose exec -T postgres pg_isready -U localai 2>/dev/null && echo yes || echo no)
  redis_ok=$(docker compose exec -T redis redis-cli ping 2>/dev/null | grep -c PONG || true)
  if [[ "$pg_ok" == "yes" && "$redis_ok" -ge 1 ]]; then
    log "Infrastructure ready."
    docker compose exec -T postgres psql -U localai -d localai < scripts/init_db.sql >/dev/null 2>&1 || true
    break
  fi
  sleep 1
  if [[ $i -eq 30 ]]; then
    warn "Infrastructure may not be fully ready — continuing anyway."
  fi
done

# ── 3. Backend venv ──────────────────────────────────────────────
if [[ ! -d backend/.venv ]]; then
  log "Creating Python virtual environment..."
  python3 -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -q -r backend/requirements.txt

# ── 4. Frontend deps ─────────────────────────────────────────────
if [[ ! -d frontend/node_modules ]]; then
  log "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

# ── 5. Launch processes ──────────────────────────────────────────
PIDS=()
cleanup() {
  log "Shutting down..."
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# LLM server (Apple Silicon → mlx-lm)
if [[ "$LLM_BACKEND" == "mlx" ]]; then
  if curl -sf --max-time 2 http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then
    log "MLX-LM already running on http://localhost:8000"
  else
    log "Starting MLX-LM server (Apple Silicon) on http://localhost:8000 ..."
    RUN_IN_BACKGROUND=1 ./scripts/start_llm_mlx.sh &
    PIDS+=($!)
    log "Waiting for MLX model to load (may take 1-2 min on first run)..."
    for i in $(seq 1 90); do
      if curl -sf --max-time 2 http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then
        log "MLX-LM ready."
        break
      fi
      sleep 2
      if [[ $i -eq 90 ]]; then
        warn "MLX-LM still loading — chat may work once model finishes loading."
      fi
    done
  fi
elif [[ "$LLM_BACKEND" == "vllm" ]]; then
  warn "LLM_BACKEND=vllm — start ./scripts/start_vllm.sh manually (requires NVIDIA GPU)."
fi

log "Starting Celery worker..."
(cd backend && celery -A app.celery_app worker --loglevel=info) &
PIDS+=($!)

log "Starting backend API on http://localhost:8080 ..."
(cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload) &
PIDS+=($!)

log "Starting frontend UI on http://localhost:3000 ..."
(cd frontend && npm run dev) &
PIDS+=($!)

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}LocalAI Agent is starting!${NC}"
echo -e ""
echo -e "  Frontend UI:  ${GREEN}http://localhost:3000${NC}  ← open this"
echo -e "  Backend API:  http://localhost:8080"
echo -e "  LLM (${LLM_BACKEND}):  http://localhost:8000/v1"
echo -e ""
if [[ "$LLM_BACKEND" == "mlx" ]]; then
  echo -e "  ${YELLOW}MLX model loading — first request may take 1-2 min.${NC}"
fi
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo ""

wait
