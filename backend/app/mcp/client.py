"""Minimal MCP HTTP client for Tavily and other MCP servers."""

import json
import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, server_url: str, name: str = "mcp"):
        self.server_url = server_url.rstrip("/")
        self.name = name
        self._initialized = False

    def _parse_response(self, resp: httpx.Response) -> Any:
        text = resp.text.strip()
        if text.startswith("event:"):
            for line in text.split("\n"):
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        return resp.json()

    async def _request(self, method: str, params: dict | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.server_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            resp.raise_for_status()
            return self._parse_response(resp)

    def _request_sync(self, method: str, params: dict | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                self.server_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            resp.raise_for_status()
            return self._parse_response(resp)

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            await self._request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "localai-agent", "version": "1.0.0"},
                },
            )
            self._initialized = True
        except Exception as e:
            logger.warning("MCP initialize failed for %s: %s", self.name, e)

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.initialize()
        try:
            result = await self._request("tools/list", {})
            if isinstance(result, dict):
                return result.get("result", {}).get("tools", [])
        except Exception as e:
            logger.warning("MCP tools/list failed for %s: %s", self.name, e)
        return []

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        await self.initialize()
        return self.call_tool_sync(tool_name, arguments)

    def call_tool_sync(self, tool_name: str, arguments: dict) -> str:
        try:
            if not self._initialized:
                self._request_sync(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "localai-agent", "version": "1.0.0"},
                    },
                )
                self._initialized = True
            result = self._request_sync(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            if isinstance(result, dict):
                content = result.get("result", {}).get("content", [])
                if content and isinstance(content, list):
                    parts = [c.get("text", str(c)) for c in content if isinstance(c, dict)]
                    return "\n".join(parts) if parts else str(result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return f"MCP tool error ({self.name}/{tool_name}): {e}"


def get_tavily_mcp_client() -> MCPClient | None:
    from app.config import settings

    url = settings.tavily_mcp_url
    if not url and settings.tavily_api_key:
        url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={settings.tavily_api_key}"
    if not url:
        return None
    return MCPClient(url, name="tavily")
