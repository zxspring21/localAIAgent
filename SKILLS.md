# Skills

Skills are executable tools registered in `backend/app/skills/registry.py` and exposed to the LLM when tool calling is enabled.

## Built-in Skills

| Skill | Description |
|-------|-------------|
| `web_search` | Search the web (Tavily / SerpAPI / DuckDuckGo) |
| `read_file` | Read a file from the workspace |
| `write_file` | Write content to a file |
| `list_directory` | List directory contents |
| `execute_system_command` | Run a shell command |
| `run_github_code` | Fetch and run code from a GitHub gist/repo |

## MCP Skills (dynamic)

Registered at startup from configured MCP servers. Naming: `mcp_{server}_{tool_name}`.

Examples:
- `mcp_tavily_tavily_search` — Tavily web search via MCP
- `mcp_slack_*` — Slack integration (when `MCP_SLACK_URL` is set)

Check registered MCP tools: `GET /api/v1/mcp/status`

## Tool Calling

- **MLX local**: disabled by default (`LLM_ENABLE_TOOLS=false`) — MLX server lacks OpenAI tool API
- **Cloud models** (GPT-4o, Claude, Gemini): enabled when `LLM_ENABLE_TOOLS=true` and API key is set

Without tool calling, web search still works via:
- Swarm mode (`researcher` agent calls `web_search` directly)
- Prompt-injected RAG/LT memory context

## Adding a Skill

```python
from app.skills.registry import skill

@skill(name="my_skill", description="Does something useful")
def my_skill(arg1: str) -> str:
    return f"Result: {arg1}"
```

Import the module in `backend/app/skills/builtin.py` to register on startup.

## RAG Document Indexing

Upload files via `POST /api/v1/uploads` (auto-indexes when `RAG_ENABLED=true`).

Supported text formats: `.txt`, `.md`, `.json`, `.csv`, `.py`, `.js`, `.ts`, `.html`, `.xml`, `.yaml`

List indexed docs: `GET /api/v1/rag/documents`

Manual re-index: `POST /api/v1/rag/index` with `{ "file_paths": ["uploads/user-id/file.txt"] }`
