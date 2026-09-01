# Agents

LocalAI Agent uses a layered agent architecture: a **Core Controller** for single-agent CoT chat, and an optional **Swarm Orchestrator** for multi-agent tasks.

## Core Controller (`backend/app/brain/controller.py`)

The default agent for `/chat` and `/chat/stream`.

**Flow:**
1. Resolve model via registry → router (MLX local or cloud API)
2. Build context from `MemoryManager` (ST + LT + RAG)
3. Run Chain-of-Thought loop with optional tool calls
4. Save turn to short-term (Redis) and long-term (PostgreSQL + Qdrant)

**System prompts** include:
- Long-term semantic memories from past conversations
- RAG document chunks from uploaded files

## Swarm Orchestrator (`backend/app/agents/swarm.py`)

Enabled with `use_swarm: true` on `/chat`. Mimics Kimi-style multi-agent workflow.

**Agents:**
| Agent | Role |
|-------|------|
| `planner` | Breaks user request into 1–3 subtasks |
| `researcher` | Web search, Tavily MCP |
| `analyst` | File/directory analysis |
| `executor` | Shell commands, file writes |
| `synthesizer` | Merges sub-agent outputs into final answer |

Swarm reads memory/RAG context before planning and saves the final turn via `MemoryManager`.

## Answer Validator (`backend/app/agents/validator.py`)

Runs after draft generation (single-agent and swarm):

1. Cross-checks answer against **RAG document chunks**
2. Optionally runs **web search** for factual/time-sensitive claims
3. Revises answer if contradictions are found

Config: `ANSWER_VALIDATION_ENABLED=true`, `VALIDATION_USE_WEB_SEARCH=true`

## Repetition Guard (`backend/app/brain/repetition.py`)

Prevents MLX models from looping identical tokens during SSE streaming:

- `repetition_penalty` is sent only in `extra_body` for MLX (OpenAI SDK rejects it as a `create()` kwarg)
- `frequency_penalty` / `presence_penalty` on OpenAI-compatible requests
- Stream circuit breaker (stops after 8 identical deltas)
- Post-processing `collapse_repetition()` on final text

## Hermes protocol (`backend/app/brain/hermes.py`)

When native tool-calling is off (typical MLX), the controller parses Thought / Action / Final Answer and runs skills through hooks.

## Runtime (`backend/app/runtime/`)

- **Hooks** — AgentStart, PreToolUse, PostToolUse, AgentComplete
- **Plugins** — `plugins/*/plugin.json` + SKILL.md + hooks.json
- **Sandbox** — isolated workdir per run; `AgentComplete` + directory delete when the agent loop finishes (`finally`)

## Auth (web + mobile)

Email register/login, Google OAuth, Apple (web form_post + native ID token). JWT for all `/api/v1` routes except auth + health.

See `docs/ARCHITECTURE.md` for full technical reference and Mermaid diagrams.

## Model Router (`backend/app/llm/router.py`)

Routes each request to the correct backend:

- **mlx** → local MLX server (`LLM_BASE_URL`, default port 8000)
- **openai / anthropic / google / deepseek / moonshot / xai** → cloud APIs (requires API keys)

Catalog ids (e.g. `mlx-llama-3.2-3b`) are resolved to API model ids (e.g. `mlx-community/Llama-3.2-3B-Instruct-4bit`).

## MCP Integration (`backend/app/mcp/`)

On startup, MCP servers register their tools as skills (`mcp_{server}_{tool}`).

Configured servers:
- **Tavily** — auto from `TAVILY_API_KEY`
- **Slack / Notion / Gmail / Facebook** — via `MCP_*_URL` env vars

## Memory Layers

| Layer | Store | Purpose |
|-------|-------|---------|
| Short-term | Redis | Last N messages per session |
| Long-term | PostgreSQL + Qdrant | Persistent messages + semantic recall |
| RAG | PostgreSQL + Qdrant | User-uploaded document chunks |

Unified API: `backend/app/memory/manager.py`

## Recommended Defaults (Mac M2)

```env
LLM_BACKEND=mlx
LLM_DEFAULT_MODEL=mlx-llama-3.2-3b
LLM_ENABLE_TOOLS=false
RAG_ENABLED=true
```

Start MLX: `./scripts/start_llm_mlx.sh`  
Start stack: `./scripts/start_dev.sh`
