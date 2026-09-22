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
        return self._fit_context(ctx)

    def _fit_context(self, ctx: MemoryContext) -> MemoryContext:
        """Keep prompt sections inside a character budget (small MLX windows)."""
        budget = settings.memory_context_char_budget
        st_cap = settings.st_history_max_chars
        rag_cap = settings.rag_chunk_max_chars

        trimmed_st: list[dict[str, Any]] = []
        used = 0
        for msg in reversed(ctx.st_history):
            content = str(msg.get("content") or "")
            if used + len(content) > st_cap and trimmed_st:
                break
            if len(content) > 1200:
                content = content[:1200] + "…"
            trimmed_st.append({**msg, "content": content})
            used += len(content)
        ctx.st_history = list(reversed(trimmed_st))

        for chunk in ctx.rag_chunks:
            text = str(chunk.get("content") or "")
            if len(text) > rag_cap:
                chunk["content"] = text[:rag_cap] + "…"
        for mem in ctx.lt_memories:
            text = str(mem.get("content") or "")
            if len(text) > rag_cap:
                mem["content"] = text[:rag_cap] + "…"

        sections = ctx.to_system_sections()
        total = len(sections["lt_memories"]) + len(sections["rag_context"])
        while total > budget and (ctx.rag_chunks or ctx.lt_memories):
            if len(ctx.rag_chunks) >= len(ctx.lt_memories) and ctx.rag_chunks:
                ctx.rag_chunks.pop()
            elif ctx.lt_memories:
                ctx.lt_memories.pop()
            else:
                break
            sections = ctx.to_system_sections()
            total = len(sections["lt_memories"]) + len(sections["rag_context"])
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
