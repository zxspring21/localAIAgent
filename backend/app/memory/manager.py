"""Unified memory layer: ST (Redis) + LT (PG/Qdrant) + RAG (documents)."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.long_term import lt_memory
from app.memory.rag import rag_store
from app.memory.short_term import st_memory

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    st_history: list[dict[str, Any]] = field(default_factory=list)
    lt_memories: list[dict[str, Any]] = field(default_factory=list)
    rag_chunks: list[dict[str, Any]] = field(default_factory=list)

    def to_system_sections(self) -> dict[str, str]:
        return {
            "lt_memories": json.dumps(self.lt_memories, ensure_ascii=False, indent=2) if self.lt_memories else "None",
            "rag_context": self._format_rag(),
        }

    def _format_rag(self) -> str:
        if not self.rag_chunks:
            return "None"
        lines = []
        for i, c in enumerate(self.rag_chunks, 1):
            fname = c.get("filename", "document")
            lines.append(f"[{i}] ({fname}, score={c.get('score', 0):.2f})\n{c.get('content', '')}")
        return "\n\n".join(lines)


class MemoryManager:
    async def build_context(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        query: str,
        use_rag: bool = True,
    ) -> MemoryContext:
        ctx = MemoryContext()
        ctx.st_history = await st_memory.get_history(str(session_id))
        try:
            ctx.lt_memories = await lt_memory.retrieve(user_id, query)
        except Exception as e:
            logger.warning("LT retrieve failed: %s", e)
        if use_rag and settings.rag_enabled:
            try:
                ctx.rag_chunks = await rag_store.retrieve(user_id, query)
            except Exception as e:
                logger.warning("RAG retrieve failed: %s", e)
        return ctx

    async def save_turn(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        user_input: str,
        assistant_output: str,
    ):
        user_msg = {"role": "user", "content": user_input}
        assistant_msg = {"role": "assistant", "content": assistant_output}
        await st_memory.save_message(str(session_id), user_msg)
        await st_memory.save_message(str(session_id), assistant_msg)
        try:
            await lt_memory.save_message(db, session_id, user_id, user_msg)
            await lt_memory.save_message(db, session_id, user_id, assistant_msg)
        except Exception as e:
            logger.error("LT save failed: %s", e)

    async def index_uploaded_files(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        file_paths: list[str],
    ) -> list[dict]:
        indexed = []
        for fp in file_paths:
            try:
                result = await rag_store.index_file(db, user_id, fp)
                indexed.append(result)
            except Exception as e:
                indexed.append({"file": fp, "error": str(e)})
        return indexed


memory_manager = MemoryManager()
