import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.embeddings import VECTOR_SIZE, embed_text
from app.memory.qdrant_util import ensure_collection
from app.models.database import Message

logger = logging.getLogger(__name__)


class LongTermMemory:
    def __init__(self):
        self._qdrant: QdrantClient | None = None
        self._available = False

    def connect(self):
        self._qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        ensure_collection(self._qdrant, settings.qdrant_collection, VECTOR_SIZE)
        self._available = True

    async def _generate_embedding(self, text: str) -> list[float]:
        return await embed_text(text)

    async def save_message(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message: dict[str, Any],
    ) -> uuid.UUID:
        if not self._qdrant:
            try:
                self.connect()
            except Exception as e:
                logger.warning("Qdrant unavailable: %s", e)

        msg = Message(
            session_id=session_id,
            user_id=user_id,
            role=message["role"],
            content=message["content"],
            embedding_status="pending",
        )
        db.add(msg)
        await db.flush()

        try:
            if not self._qdrant:
                raise RuntimeError("Qdrant not connected")
            vector = await self._generate_embedding(message["content"])
            if len(vector) != VECTOR_SIZE:
                raise ValueError(f"Embedding dim {len(vector)} != {VECTOR_SIZE}")
            point_id = str(msg.id)
            self._qdrant.upsert(
                collection_name=settings.qdrant_collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "message_id": str(msg.id),
                            "session_id": str(session_id),
                            "user_id": str(user_id),
                            "role": message["role"],
                            "content": message["content"][:4000],
                        },
                    )
                ],
            )
            msg.embedding_status = "indexed"
        except Exception as e:
            logger.error("Failed to index message in Qdrant: %s", e)
            msg.embedding_status = "failed"

        await db.commit()
        return msg.id

    async def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = limit or settings.lt_memory_retrieval_limit
        if not self._qdrant:
            self.connect()

        try:
            query_vector = await self._generate_embedding(query)
            results = self._qdrant.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]
                ),
                limit=limit,
            )
            return [
                {
                    "content": hit.payload.get("content", ""),
                    "role": hit.payload.get("role", ""),
                    "session_id": hit.payload.get("session_id", ""),
                    "score": hit.score,
                    "source": "long_term",
                }
                for hit in results
            ]
        except Exception as e:
            logger.error("LT memory retrieval failed: %s", e)
            return []

    async def get_session_messages(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def count_points(self, user_id: uuid.UUID) -> int:
        if not self._qdrant:
            try:
                self.connect()
            except Exception:
                return 0
        res = self._qdrant.count(
            collection_name=settings.qdrant_collection,
            count_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]),
            exact=True,
        )
        return int(res.count)

    async def sample_points(self, user_id: uuid.UUID, limit: int = 8) -> list[dict[str, Any]]:
        if not self._qdrant:
            try:
                self.connect()
            except Exception:
                return []
        points, _ = self._qdrant.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id": str(p.id),
                "role": (p.payload or {}).get("role"),
                "session_id": (p.payload or {}).get("session_id"),
                "content": ((p.payload or {}).get("content") or "")[:240],
            }
            for p in points
        ]


lt_memory = LongTermMemory()
