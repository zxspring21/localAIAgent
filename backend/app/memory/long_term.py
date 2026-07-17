import hashlib
import logging
import uuid
from typing import Any

from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import Message

logger = logging.getLogger(__name__)

VECTOR_SIZE = 384


class LongTermMemory:
    def __init__(self):
        self._qdrant: QdrantClient | None = None
        self._encoder: AsyncOpenAI | None = None
        self._available = False

    def connect(self):
        self._qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._encoder = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.vllm_api_key,
        )
        self._ensure_collection()
        self._available = True

    def _ensure_collection(self):
        if not self._qdrant:
            return
        collections = [c.name for c in self._qdrant.get_collections().collections]
        if settings.qdrant_collection not in collections:
            self._qdrant.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    async def _generate_embedding(self, text: str) -> list[float]:
        try:
            response = await self._encoder.embeddings.create(
                input=[text],
                model=settings.embedding_model,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("Embedding API unavailable, using hash fallback: %s", e)
            return self._hash_embedding(text)

    def _hash_embedding(self, text: str) -> list[float]:
        digest = hashlib.sha384(text.encode()).digest()
        return [b / 255.0 for b in digest]

    async def save_message(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message: dict[str, Any],
    ) -> uuid.UUID:
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
            vector = await self._generate_embedding(message["content"])
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
                            "content": message["content"],
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
                query_filter={
                    "must": [{"key": "user_id", "match": {"value": str(user_id)}}]
                },
                limit=limit,
            )
            return [
                {
                    "content": hit.payload.get("content", ""),
                    "role": hit.payload.get("role", ""),
                    "session_id": hit.payload.get("session_id", ""),
                    "score": hit.score,
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


lt_memory = LongTermMemory()
