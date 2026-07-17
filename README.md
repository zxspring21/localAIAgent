# LocalAI Agent

Multi-Agent automation system integrating vLLM inference, Chain-of-Thought reasoning, skill execution, memory management, multi-user authentication, and a Claude-like web interface.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React UI   │────▶│  FastAPI     │────▶│  vLLM       │
│  (port 3000)│     │  Backend     │     │  (port 8000)│
└─────────────┘     │  (port 8080) │     └─────────────┘
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌─────────┐
         │ Redis  │  │Postgres│  │ Qdrant  │
         │ (ST)   │  │ (SQL)  │  │ (LT)    │
         └────────┘  └────────┘  └─────────┘
```

### Modules

| Module | Path | Description |
|--------|------|-------------|
| vLLM Backend | `scripts/start_vllm.sh` | OpenAI-compatible LLM inference server |
| Skills | `backend/app/skills/` | Decorator-based skill registry with built-in tools |
| Memory | `backend/app/memory/` | Redis (short-term) + PostgreSQL/Qdrant (long-term) |
| Brain | `backend/app/brain/` | CoT loop with tool calling and memory integration |
| Auth | `backend/app/auth/` | JWT-based multi-user authentication |
| Automation | `backend/app/automation/` | APScheduler for recurring skill execution |
| API | `backend/app/api/` | REST endpoints for chat, sessions, models |
| Frontend | `frontend/` | Claude-inspired React chat interface |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 20+ (for frontend development)
- vLLM with GPU (for LLM inference)

### 1. Infrastructure Services

```bash
cp .env.example .env
docker compose up -d postgres redis qdrant
```

### 2. Start vLLM (requires GPU)

```bash
chmod +x scripts/start_vllm.sh
./scripts/start_vllm.sh meta-llama/Meta-Llama-3-8B-Instruct 8000 1
```

For larger models with multi-GPU:

```bash
./scripts/start_vllm.sh meta-llama/Meta-Llama-3-70B-Instruct 8000 4
```

### 3. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Full Docker Stack

```bash
docker compose up -d
```

Note: vLLM must be started separately on the host with GPU access.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, get JWT token |
| GET | `/api/v1/auth/me` | Current user info |
| GET | `/api/v1/models` | List available LLM models |
| GET | `/api/v1/skills` | List registered skills |
| POST | `/api/v1/sessions` | Create chat session |
| GET | `/api/v1/sessions` | List user sessions |
| GET | `/api/v1/sessions/{id}/messages` | Get session messages |
| POST | `/api/v1/chat` | Send message (CoT + tools) |
| POST | `/api/v1/automation/schedule-skill` | Schedule recurring skill |
| DELETE | `/api/v1/automation/tasks/{id}` | Cancel scheduled task |

## Built-in Skills

- `run_github_code` — Clone and run scripts from GitHub repos
- `execute_system_command` — Safe read-only shell commands
- `read_file` / `write_file` — Workspace file operations
- `list_directory` — Directory listing
- `web_search` — Web search (placeholder for real API integration)

## Adding Custom Skills

```python
from app.skills.registry import skill

@skill(name="my_skill", description="Does something useful")
def my_skill(param: str) -> str:
    return f"Result: {param}"
```

Import the module in `backend/app/skills/__init__.py` to register it.

## Environment Variables

See `.env.example` for all configuration options including vLLM URL, database connections, JWT secrets, and memory limits.

## License

MIT
