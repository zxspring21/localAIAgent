# LocalAI Agent — System Architecture

Enterprise-shaped **product / inference / training** planes on a codebase that today runs as Vite + Expo + FastAPI + MLX (or cloud APIs). Closed-lab internals (Claude, etc.) are not public; this maps those **design logics** onto this repo.

Memory packing, retrieval, and forgetting: **[docs/Memory.md](Memory.md)**.

---

## 1. Overview

- **Product plane:** accounts (email / Google / Apple), sessions, RAG uploads, agent UX, billing-ready JWT gateway.
- **Inference plane:** model registry + router, SSE, Hermes loop, Kimi-style swarm, sandbox/hooks/plugins, packed memory context.
- **Training plane (offline, target):** data lake of traces, SFT / RLHF / evals, model registry that **publishes into** the inference gateway — not in the request path.
- **Cross-cutting:** input/output guardrails (validator + hooks), OpenTelemetry-style traces (to add), tenant isolation on every Qdrant filter.

---

## 2. System diagrams (GitHub-safe Mermaid)

GitHub’s Mermaid parser rejects unquoted `*`, `+`, and some `/` in node text. Every label below is quoted.

### 2.1 Three planes (product, inference, training)

```mermaid
flowchart TB
  subgraph Product["Product plane"]
    C["Clients: Web, App, API"]
    E["Edge: CDN, WAF"]
    G["API gateway: JWT, rate limit, route"]
    IG["Input guards: PII, injection hooks"]
    AR["Agent runtime: Hermes, Swarm, tools"]
    MM["MemoryManager"]
  end

  subgraph Inference["Inference plane"]
    MR["Model router"]
    SV["Serving: MLX, vLLM, or cloud APIs"]
    OG["Output guards: validator, web check"]
  end

  subgraph Data["Online data"]
    PG[("PostgreSQL")]
    Redis[("Redis ST")]
    Qd[("Qdrant LT and RAG")]
  end

  subgraph Train["Training plane offline"]
    DL[("Object store / data lake")]
    PRE["Pretrain / continue-pretrain"]
    POST["SFT, RLHF, evals"]
    REG["Model registry"]
  end

  C --> E --> G --> IG --> AR
  AR --> MM
  MM --> PG
  MM --> Redis
  MM --> Qd
  AR --> MR --> SV --> OG
  OG --> C
  REG -.-> SV
  G -.-> DL
  POST --> EV["Evals and red team"]
  EV --> REG
  DL --> PRE --> POST
```

### 2.2 High-level components

```mermaid
flowchart TB
  subgraph Client["Web and Expo"]
    UI["Chat UI"]
    AuthUI["Email, Google, Apple"]
    ModelPicker["Model picker"]
    FeatureBar["Swarm, upload, stream"]
  end

  subgraph API["FastAPI gateway"]
    Routes["API v1 routes"]
    Auth["JWT and OAuth"]
    Brain["Core and Hermes"]
    Swarm["Swarm orchestrator"]
    Validator["Answer validator"]
    Runtime["Hooks, plugins, sandbox"]
    MCP["MCP loader"]
  end

  subgraph Memory["Memory layer"]
    MM["MemoryManager"]
    ST[("Redis short-term")]
    PG[("PostgreSQL")]
    Qdrant[("Qdrant vectors")]
    RAG["RAG store"]
  end

  subgraph LLM["Inference"]
    Registry["Model catalog"]
    Router["Model router"]
    MLX["MLX-LM or vLLM"]
    Cloud["Cloud APIs"]
  end

  AuthUI --> Auth
  UI --> Routes
  Routes --> Auth
  Routes --> Brain
  Routes --> Swarm
  Brain --> Runtime
  Swarm --> Runtime
  Brain --> MM
  Swarm --> MM
  MM --> ST
  MM --> PG
  MM --> RAG
  RAG --> Qdrant
  MM --> Qdrant
  Brain --> Registry
  Swarm --> Registry
  Registry --> Router
  Router --> MLX
  Router --> Cloud
  Brain --> Validator
  Swarm --> Validator
  Validator --> RAG
  Brain --> MCP
```

### 2.3 Agent core — Hermes, Swarm, hooks, plugins, sandbox

```mermaid
flowchart TB
  Gateway["Gateway SSE"] --> Orchestrator["Core or Swarm"]
  Orchestrator --> Start["Hook AgentStart"]
  Start --> Sandbox["Create run workdir"]
  Sandbox --> Router["Model router"]
  Router -->|"mlx"| MLX["Local MLX extra_body"]
  Router -->|"cloud"| Cloud["OpenAI-compatible APIs"]
  Router --> Loop{"Mode"}
  Loop -->|"single"| Hermes["Hermes Thought Action loop"]
  Loop -->|"swarm"| Swarm["Planner then sub-agents"]
  PluginReg["Plugin packs SKILL.md"] --> Hermes
  PluginReg --> Swarm
  Hermes --> Pre["Hook PreToolUse"]
  Swarm --> Pre
  Pre --> Skills["Skills and MCP tools"]
  Skills --> Post["Hook PostToolUse"]
  Post --> Verifier["Validator plus RAG"]
  Verifier --> MemWrite["MemoryManager save_turn"]
  MemWrite --> End["Hook AgentComplete"]
  End --> Teardown["Delete sandbox workdir"]
```

### 2.4 Sandbox lifecycle

```mermaid
sequenceDiagram
  participant API as FastAPI
  participant SB as agent_run_sandbox
  participant H as Hooks
  participant AG as Hermes or Swarm
  participant FS as Temp workdir

  API->>SB: enter chat or swarm
  SB->>FS: mkdtemp
  SB->>H: AgentStart
  SB->>AG: run loop
  Note over AG: tools stay inside workdir
  AG-->>SB: return or error
  SB->>H: AgentComplete
  SB->>FS: rmtree if isolated
```

### 2.5 Auth

```mermaid
flowchart TD
  U["User"] --> W{"Channel"}
  W -->|"Web"| EmailForm["Register or login"]
  W -->|"Web"| GStart["Google OAuth start"]
  W -->|"Web"| AStart["Apple OAuth start"]
  W -->|"Mobile"| GTok["Google id_token"]
  W -->|"iOS"| ATok["Apple identity token"]
  EmailForm --> JWT["JWT"]
  GStart --> GCB["Google callback"]
  AStart --> ACB["Apple form_post"]
  GCB --> Upsert["upsert users"]
  ACB --> Upsert
  GTok --> Upsert
  ATok --> Upsert
  Upsert --> JWT
  JWT --> API["Protected API"]
```

### 2.6 Chat plus validation

```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend
  participant API as FastAPI
  participant MM as MemoryManager
  participant BR as CoreController
  participant LLM as MLX or Cloud
  participant VAL as Validator

  U->>FE: Send message
  FE->>API: POST chat stream
  API->>MM: build_context
  MM-->>BR: MemoryContext
  BR->>LLM: create_chat_completion
  Note over BR,LLM: extra_body only for MLX penalties
  loop SSE
    LLM-->>BR: delta
    BR-->>FE: token event
  end
  BR->>VAL: validate_answer
  VAL-->>BR: ValidationResult
  BR->>MM: save_turn
  BR-->>FE: done event
```

### 2.7 Swarm

```mermaid
flowchart LR
  Q["User query"] --> P["Planner"]
  P --> SA1["Researcher"]
  P --> SA2["Analyst"]
  P --> SA3["Executor"]
  SA1 --> WS["Web search MCP"]
  SA2 --> FS["File skills"]
  SA3 --> CMD["Shell write"]
  SA1 --> SYN["Synthesizer"]
  SA2 --> SYN
  SA3 --> SYN
  SYN --> VAL["Validator"]
  VAL --> OUT["Final answer"]
```

### 2.8 Model routing (inference gateway)

```mermaid
flowchart TD
  IN["model id"] --> ALIAS{"Alias map"}
  ALIAS --> CAT["Catalog id"]
  CAT --> SPEC["ModelSpec"]
  SPEC --> BACK{"Backend"}
  BACK -->|"mlx"| MLX["MLX server"]
  BACK -->|"openai"| OAI["api.openai.com"]
  BACK -->|"anthropic"| ANT["Anthropic"]
  BACK -->|"google"| GEM["Gemini"]
  BACK -->|"other"| OTHER["DeepSeek Moonshot xAI"]
```

Target serving (when leaving a single Mac): cache-aware scheduler → **prefill** nodes for long packed prompts → **decode** nodes for tokens → shared KV pool (Mooncake / vLLM PagedAttention). Local MLX is the current single-node stand-in.

### 2.9 Memory and RAG

Full write-up: [Memory.md](Memory.md).

```mermaid
flowchart LR
  Query["User message"] --> MM["MemoryManager"]
  MM --> ST["Redis last N"]
  MM --> LT["Qdrant user_memory"]
  MM --> RAG["Qdrant user_documents"]
  ST --> CTX["Packed prompt"]
  LT --> CTX
  RAG --> CTX
  CTX --> Agent["Hermes or Swarm"]
  Agent --> Save["save_turn"]
  Save --> PG[("PostgreSQL")]
  Save --> ST
  Save --> LT
```

### 2.10 RAG pipeline (product + retrieval)

```mermaid
flowchart LR
  DOC["Uploads"] --> CH["Parse and chunk"]
  CH --> EM["embed_text 384-d"]
  EM --> VS["Qdrant plus user_id ACL"]
  Q["Question"] --> HY["Vector search with tenant filter"]
  VS --> HY
  HY --> PACK["Character budget"]
  PACK --> LLM["Generate with citations"]
  LLM --> CK["Validator vs chunks"]
```

---

## 3. Layer mapping (design logic → this repo)

| Plane | Design logic | This repo today | Scale-up |
|-------|----------------|-----------------|----------|
| Product | One gateway for identity, tenancy, uploads | FastAPI JWT, OAuth, sessions, RAG upload | Envoy/Kong, Redis rate limit, Stripe/metering |
| Auth | User + agent identity, short-lived creds | JWT, Google, Apple | OIDC (Keycloak), mTLS for tools, OPA |
| Memory | ST vs LT vs RAG, pack under window | Redis + PG + Qdrant, `_fit_context` | BM25 hybrid, reranker, session summaries |
| Inference | Throughput, TTFB, long-context KV | MLX or cloud `create_chat_completion` | vLLM/SGLang, prefill/decode split, FP8 |
| Tools | Least privilege + sandbox | Hooks, plugins, tempdir teardown | gVisor/Firecracker, approval queues |
| Guardrails | Input, tool, output | PreToolUse, validator, web check | Llama Guard, Presidio PII |
| Training | Offline, published models only | Not in request path | Lake + SFT/RLHF + evals → registry |
| Observe | Replay every request | Logs, memory overview | OpenTelemetry, Langfuse, eval gates |

Clipboard systems → code:

| Pattern | Source | Implementation |
|---------|--------|----------------|
| Observe / think / act | Hermes | `brain/hermes.py` |
| Planner swarm | Kimi | `agents/swarm.py` |
| Skills, hooks, plugins | Claude | `runtime/`, `plugins/` |
| Isolated exec | Codex / Cursor | `runtime/sandbox.py` `finally` |
| KV-centric serving | Mooncake | Target on inference plane, not MemoryManager |

---

## 4. Repetition token fix

| Layer | Location | Mechanism |
|-------|----------|-----------|
| 1 | `sanitize_completion_kwargs` | MLX `extra_body.repetition_penalty` only — never a `create()` kwarg |
| 2 | `normalize_stream_delta` | Cumulative vs delta streams |
| 3 | `should_stop_stream` | Stop after 8 identical deltas |
| 4 | `collapse_repetition` | Post-process final text |

---

## 5. Answer validation

`backend/app/agents/validator.py`: RAG cross-check, optional web search, JSON revise. Config `ANSWER_VALIDATION_ENABLED`, `VALIDATION_USE_WEB_SEARCH`.

---

## 6. Memory architecture

See **[docs/Memory.md](Memory.md)** for retrieval, packing, TTL, and forget APIs.

| Lane | Storage | API |
|------|---------|-----|
| ST | Redis | `st_memory` |
| Canonical + LT | PostgreSQL + Qdrant `user_memory` | `lt_memory` |
| RAG | PostgreSQL + Qdrant `user_documents` | `rag_store` |

```python
ctx = await memory_manager.build_context(user_id, session_id, query)
await memory_manager.save_turn(db, session_id, user_id, user_msg, assistant_msg)
```

---

## 7. Model catalog

`backend/app/llm/registry.py`. Catalog ids (example `mlx-llama-3.2-3b`) map to local MLX ids or cloud API ids.

---

## 8. API reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Email/username |
| POST | `/api/v1/auth/login` | Username or email |
| GET | `/api/v1/auth/providers` | `{ email, google, apple }` |
| GET | `/api/v1/auth/oauth/google/start` | Browser Google |
| GET | `/api/v1/auth/oauth/apple/start` | Browser Apple |
| POST | `/api/v1/auth/oauth/google` | Native Google token |
| POST | `/api/v1/auth/oauth/apple` | Native Apple token |
| GET | `/api/v1/models` | Catalog |
| POST | `/api/v1/sessions` | Chat session |
| DELETE | `/api/v1/sessions/{id}` | Forget ST + LT for session |
| POST | `/api/v1/chat` | Sync chat |
| POST | `/api/v1/chat/stream` | SSE |
| POST | `/api/v1/uploads` | Upload + RAG index |
| GET | `/api/v1/rag/documents` | List uploads |
| DELETE | `/api/v1/rag/documents/{id}` | Forget one document |
| GET | `/api/v1/memory/overview` | Store snapshot |
| GET | `/api/v1/runtime/plugins` | Plugins |
| GET | `/health` | Health |

---

## 9. Mobile

`mobile/` Expo. `eas build` / `eas submit`. `EXPO_PUBLIC_API_URL` must be public HTTPS. Google/Apple client ids must match backend.

---

## 10. Infrastructure (dev)

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | Vite |
| Backend | 8080 | FastAPI |
| MLX-LM | 8000 | Local generate |
| PostgreSQL | 5432 | Canonical data |
| Redis | 6379 | ST + Celery |
| Qdrant | 6333 | LT + RAG |

```bash
./scripts/start_llm_mlx.sh
./scripts/start_dev.sh
```

---

## 11. Directory structure

```
localAIAgent/
├── backend/app/
│   ├── agents/
│   ├── auth/
│   ├── brain/
│   ├── llm/
│   ├── memory/          # see docs/Memory.md
│   ├── runtime/
│   ├── skills/
│   └── api/routes.py
├── frontend/src/
├── mobile/
├── plugins/
├── docs/ARCHITECTURE.md
├── docs/Memory.md
├── AGENTS.md
└── SKILLS.md
```

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| GitHub Mermaid lexical error | Unquoted `*` in `/api/v1/*` | Quoted labels only (this file) |
| `repetition_penalty` TypeError | OpenAI SDK kwargs | `create_chat_completion` |
| Backend import SyntaxError | `global` after use | `embeddings.py` global at function top |
| Auth proxy ECONNREFUSED | API not running | Restart `start_dev.sh` |
| RAG empty | No upload / Qdrant down | Attach file; check overview |
| Context overflow / ramble | Budget too high | Lower `MEMORY_CONTEXT_CHAR_BUDGET` |

---

## 13. Security

- JWT on API except auth + health
- Uploads under `uploads/{user_id}/`
- Qdrant filters always include `user_id`
- PreToolUse hooks; sandbox deleted on AgentComplete
- Do not commit `.env`
