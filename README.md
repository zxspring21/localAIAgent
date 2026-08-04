# LocalAI Agent

Multi-Agent automation system integrating vLLM inference, Chain-of-Thought reasoning, skill execution, memory management, multi-user authentication, SSE streaming, Celery async tasks, and a Claude-like web interface.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React UI   │────▶│  FastAPI     │────▶│  vLLM       │
│  (port 3000)│     │  Backend     │     │  (port 8000)│
└─────────────┘     │  (port 8080) │     └─────────────┘
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌────────┐       ┌──────────┐      ┌─────────┐
    │ Redis  │       │ Postgres │      │ Qdrant  │
    │ (ST)   │       │ (SQL)    │      │ (LT)    │
    └────────┘       └──────────┘      └─────────┘
                           │
                    ┌──────┴──────┐
                    │ Celery Worker│
                    │ (async jobs) │
                    └─────────────┘
```

## Quick Start (MacBook Air M2 — Apple Silicon)

```bash
cp .env.example .env
./scripts/start_dev.sh    # starts mlx-lm + backend + frontend
```

Open **http://localhost:3000**. The default LLM is **MLX-LM** on port 8000.

### Manual MLX-LM start (separate terminal)

```bash
./scripts/start_llm_mlx.sh
# or with 8B model (16GB+ RAM recommended):
./scripts/start_llm_mlx.sh mlx-community/Meta-Llama-3.1-8B-Instruct-4bit
```

### LLM Backend Switch

| Platform | Backend | Start script | Model example |
|----------|---------|--------------|---------------|
| Mac M1/M2/M3/M4 | `mlx` | `./scripts/start_llm_mlx.sh` | `mlx-community/Llama-3.2-3B-Instruct-4bit` |
| NVIDIA GPU | `vllm` | `./scripts/start_vllm.sh` | `meta-llama/Llama-3.1-8B-Instruct` |

Set in `.env`:

```bash
LLM_BACKEND=mlx
LLM_BASE_URL=http://localhost:8000/v1
LLM_DEFAULT_MODEL=mlx-community/Llama-3.2-3B-Instruct-4bit
```

## Quick Start (NVIDIA GPU + vLLM)

```bash
cp .env.example .env
./scripts/start_dev.sh          # infra + backend + celery + frontend
./scripts/start_vllm.sh ...     # separate terminal, requires GPU
```

Open **http://localhost:3000** for the chat UI.

## Three Response Modes

| Mode | Endpoint | Description |
|------|----------|-------------|
| **SSE Stream** | `POST /api/v1/chat/stream` | Real-time token streaming + tool events |
| **Sync** | `POST /api/v1/chat` | Wait for full CoT response |
| **Celery Async** | `POST /api/v1/chat/async` | Background processing, poll for result |

Select mode in the chat UI top bar, or use the System Tests page to verify SSE and Celery.

## Web Search API

Configure in `.env`:

```bash
# Provider: tavily | serpapi | duckduckgo
WEB_SEARCH_PROVIDER=duckduckgo
TAVILY_API_KEY=tvly-...        # https://tavily.com
SERPAPI_API_KEY=...              # https://serpapi.com
```

Fallback chain: configured provider → Tavily (if key set) → SerpAPI (if key set) → DuckDuckGo (free, no key).

The `web_search` skill is callable by the CoT loop or asynchronously via Celery:

```bash
POST /api/v1/skills/execute-async
{"skill_name": "web_search", "args": {"query": "latest AI news"}}
```

## Celery Async Tasks

```bash
# Start worker (included in start_dev.sh and docker-compose)
cd backend && celery -A app.celery_app worker --loglevel=info
```

| Task | Celery name | Purpose |
|------|-------------|---------|
| Chat processing | `tasks.process_chat` | Full CoT loop in background |
| Skill execution | `tasks.execute_skill` | Run any registered skill async |
| Scheduled skill | `tasks.run_scheduled_skill` | Automation via Celery |

## SSE Event Types

The `/chat/stream` endpoint emits Server-Sent Events:

| Event | Data | When |
|-------|------|------|
| `start` | `{session_id, model}` | Stream begins |
| `token` | `{content}` | Each LLM token |
| `thinking` | `{iteration}` | CoT loop iteration |
| `tool_start` | `{name, args}` | Skill execution begins |
| `tool_result` | `{name, result}` | Skill execution completes |
| `done` | `{content, tool_calls_made}` | Final response |
| `error` | `{message}` | Failure |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat` | Sync chat (CoT + tools) |
| POST | `/api/v1/chat/stream` | SSE streaming chat |
| POST | `/api/v1/chat/async` | Celery background chat |
| GET | `/api/v1/chat/async/{task_id}` | Poll async chat result |
| POST | `/api/v1/skills/execute-async` | Celery background skill |
| GET | `/api/v1/skills/execute-async/{task_id}` | Poll skill result |
| GET | `/api/v1/tests/overview` | Run all module tests |

See full endpoint list in previous sections and `backend/app/api/routes.py`.

## System Test Dashboard

Navigate to **System Tests** in the UI (`/test`) to independently verify:

- vLLM, PostgreSQL, Redis, Qdrant connectivity
- Skill registry and web search
- Celery worker availability
- SSE streaming and async chat integration
- Multi-session isolation, auth, memory

## Built-in Skills

- `web_search` — Tavily / SerpAPI / DuckDuckGo
- `run_github_code` — Clone and run GitHub skill repos
- `execute_system_command` — Safe read-only shell commands
- `read_file` / `write_file` — Workspace file operations
- `list_directory` — Directory listing

## License

MIT
