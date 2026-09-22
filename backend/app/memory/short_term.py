import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings


class ShortTermMemory:
    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._available = True

    async def connect(self):
        try:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            self._available = True
        except Exception:
            self._available = False
            self._redis = None
            raise

    async def disconnect(self):
        if self._redis:
            await self._redis.close()

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}:history"

    async def save_message(self, session_id: str, message: dict[str, Any]):
        if not self._available:
            return
        if not self._redis:
            try:
                await self.connect()
            except Exception:
                return
        key = self._key(session_id)
        await self._redis.lpush(key, json.dumps(message, ensure_ascii=False))
        await self._redis.ltrim(key, 0, settings.st_memory_max_messages - 1)

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        if not self._available or not self._redis:
            return []
        try:
            key = self._key(session_id)
            raw = await self._redis.lrange(key, 0, -1)
            messages = [json.loads(m) for m in raw]
            return list(reversed(messages))
        except Exception:
            return []

    async def inspect(self, session_id: str | None = None) -> dict[str, Any]:
        if not self._available or not self._redis:
            try:
                await self.connect()
            except Exception as e:
                return {"ok": False, "error": str(e), "keys": []}
        info = {"ok": True, "url": settings.redis_url, "keys": []}
        try:
            keys = []
            async for key in self._redis.scan_iter(match="session:*:history", count=50):
                keys.append(key)
                if len(keys) >= 40:
                    break
            preview = []
            for key in keys[:20]:
                n = await self._redis.llen(key)
                ttl = await self._redis.ttl(key)
                preview.append({"key": key, "messages": n, "ttl": ttl})
            info["keys"] = preview
            info["key_count"] = len(keys)
            if session_id:
                hist = await self.get_history(session_id)
                info["active_session"] = {
                    "id": session_id,
                    "messages": len(hist),
                    "preview": [{"role": m.get("role"), "content": str(m.get("content") or "")[:160]} for m in hist[-6:]],
                }
        except Exception as e:
            info["ok"] = False
            info["error"] = str(e)
        return info

    async def clear(self, session_id: str):
        if not self._available or not self._redis:
            return
        await self._redis.delete(self._key(session_id))


st_memory = ShortTermMemory()
