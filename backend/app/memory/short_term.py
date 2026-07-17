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

    async def clear(self, session_id: str):
        if not self._available or not self._redis:
            return
        await self._redis.delete(self._key(session_id))


st_memory = ShortTermMemory()
