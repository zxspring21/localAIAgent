"""Register MCP server tools into the skill registry."""

import asyncio
import logging
from typing import Any

from app.config import settings
from app.mcp.client import MCPClient, get_tavily_mcp_client
from app.skills.registry import SKILL_REGISTRY, skill

logger = logging.getLogger(__name__)
_mcp_registered = False


def _register_mcp_tool(client: MCPClient, tool: dict[str, Any]) -> None:
    name = tool.get("name", "")
    description = tool.get("description", f"MCP tool from {client.name}")
    if not name or name in SKILL_REGISTRY:
        return

    input_schema = tool.get("inputSchema", {"type": "object", "properties": {}})

    def make_handler(c: MCPClient, tool_name: str):
        def handler(**kwargs) -> str:
            return asyncio.run(c.call_tool(tool_name, kwargs))

        handler.__annotations__ = {
            k: str for k in input_schema.get("properties", {}).keys()
        }
        return handler

    handler = make_handler(client, name)
    skill(name=f"mcp_{client.name}_{name}", description=f"[MCP/{client.name}] {description}")(handler)


async def register_mcp_skills() -> int:
    global _mcp_registered
    if _mcp_registered:
        return len([k for k in SKILL_REGISTRY if k.startswith("mcp_")])

    count = 0
    clients: list[MCPClient] = []

    tavily = get_tavily_mcp_client()
    if tavily:
        clients.append(tavily)

    for url_attr, name in [
        ("mcp_slack_url", "slack"),
        ("mcp_notion_url", "notion"),
        ("mcp_gmail_url", "gmail"),
    ]:
        url = getattr(settings, url_attr, "")
        if url:
            clients.append(MCPClient(url, name=name))

    for client in clients:
        try:
            tools = await client.list_tools()
            for tool in tools:
                _register_mcp_tool(client, tool)
                count += 1
            logger.info("Registered %d MCP tools from %s", len(tools), client.name)
        except Exception as e:
            logger.warning("Failed to register MCP tools from %s: %s", client.name, e)

    _mcp_registered = True
    return count


def ensure_mcp_skills_sync() -> None:
    try:
        asyncio.get_event_loop().run_until_complete(register_mcp_skills())
    except RuntimeError:
        asyncio.run(register_mcp_skills())
