"""Read-only snapshots of Redis / PostgreSQL / Qdrant / RAG for the memory UI."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.long_term import lt_memory
from app.memory.rag import rag_store
from app.memory.short_term import st_memory
from app.models.database import Document, Message, Session


async def postgres_snapshot(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    sessions = await db.execute(select(func.count()).select_from(Session).where(Session.user_id == user_id))
    messages = await db.execute(select(func.count()).select_from(Message).where(Message.user_id == user_id))
    documents = await db.execute(select(func.count()).select_from(Document).where(Document.user_id == user_id))
    status_rows = await db.execute(
        select(Message.embedding_status, func.count())
        .where(Message.user_id == user_id)
        .group_by(Message.embedding_status)
    )
    recent = await db.execute(
        select(Message).where(Message.user_id == user_id).order_by(Message.created_at.desc()).limit(8)
    )
    return {
        "ok": True,
        "store": "postgresql",
        "purpose": "Canonical chat history, users, sessions, document metadata",
        "counts": {
            "sessions": int(sessions.scalar() or 0),
            "messages": int(messages.scalar() or 0),
            "documents": int(documents.scalar() or 0),
        },
        "embedding_status": {row[0] or "unknown": int(row[1]) for row in status_rows.all()},
        "recent_messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "embedding_status": m.embedding_status,
                "content": (m.content or "")[:200],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in recent.scalars().all()
        ],
    }


async def memory_overview(db: AsyncSession, user_id: uuid.UUID, session_id: str | None = None) -> dict[str, Any]:
    redis_info = await st_memory.inspect(session_id)
    pg = await postgres_snapshot(db, user_id)
    try:
        lt_count = await lt_memory.count_points(user_id)
        lt_ok = True
        lt_error = None
        lt_samples = await lt_memory.sample_points(user_id)
    except Exception as e:
        lt_count, lt_ok, lt_error, lt_samples = 0, False, str(e), []
    try:
        rag_count = await rag_store.count_points(user_id)
        rag_ok = True
        rag_error = None
        rag_samples = await rag_store.sample_chunks(user_id)
        docs = await rag_store.list_documents(db, user_id)
    except Exception as e:
        rag_count, rag_ok, rag_error, rag_samples, docs = 0, False, str(e), [], []

    return {
        "user_id": str(user_id),
        "vector_size": 384,
        "stores": {
            "redis": {
                **redis_info,
                "store": "redis",
                "purpose": "Short-term rolling window for the current session",
                "max_messages": settings.st_memory_max_messages,
                "ttl_seconds": settings.st_memory_ttl_seconds,
            },
            "postgresql": pg,
            "qdrant_long_term": {
                "ok": lt_ok,
                "error": lt_error,
                "store": "qdrant",
                "collection": settings.qdrant_collection,
                "purpose": "Semantic recall of past turns across sessions",
                "points": lt_count,
                "samples": lt_samples,
            },
            "qdrant_rag": {
                "ok": rag_ok,
                "error": rag_error,
                "store": "qdrant",
                "collection": settings.qdrant_rag_collection,
                "purpose": "Uploaded document chunks",
                "points": rag_count,
                "documents": [
                    {
                        "id": str(d.id),
                        "filename": d.filename,
                        "chunk_count": d.chunk_count,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                    }
                    for d in docs[:20]
                ],
                "samples": rag_samples,
            },
        },
        "context_limits": {
            "st_memory_max_messages": settings.st_memory_max_messages,
            "st_memory_ttl_seconds": settings.st_memory_ttl_seconds,
            "st_history_max_chars": settings.st_history_max_chars,
            "rag_retrieval_limit": settings.rag_retrieval_limit,
            "lt_memory_retrieval_limit": settings.lt_memory_retrieval_limit,
            "memory_context_char_budget": settings.memory_context_char_budget,
            "llm_max_tokens": settings.llm_max_tokens,
        },
    }
