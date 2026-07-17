#!/usr/bin/env bash
# One-command dev launcher for LocalAI Agent
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[localai]${NC} $*"; }
warn() { echo -e "${YELLOW}[localai]${NC} $*"; }
err()  { echo -e "${RED}[localai]${NC} $*" >&2; }

# ── 1. Environment ──────────────────────────────────────────────
if [[ ! -f .env ]]; then
  log "Creating .env from .env.example"
  cp .env.example .env
fi

# ── 2. Infrastructure (Docker) ───────────────────────────────────
log "Starting infrastructure (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant 2>/dev/null || {
  warn "Docker compose failed — make sure Docker is running."
  warn "You can also install postgres/redis/qdrant locally."
}

log "Waiting for services to be healthy..."
for i in $(seq 1 30); do
  pg_ok=$(docker compose exec -T postgres pg_isready -U localai 2>/dev/null && echo yes || echo no)
  redis_ok=$(docker compose exec -T redis redis-cli ping 2>/dev/null | grep -c PONG || true)
  if [[ "$pg_ok" == "yes" && "$redis_ok" -ge 1 ]]; then
    log "Infrastructure ready."
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
echo -e "  API Health:   http://localhost:8080/health"
echo -e "  vLLM (LLM):   http://localhost:8000  (start separately with GPU)"
echo -e ""
echo -e "  ${YELLOW}Note: port 8000 is vLLM inference only — no web UI.${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo ""

wait
