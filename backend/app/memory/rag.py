"""RAG: document chunking, indexing (Qdrant), and semantic retrieval."""

import hashlib
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import Document

logger = logging.getLogger(__name__)

VECTOR_SIZE = 384
CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


class RAGStore:
    def __init__(self):
        self._qdrant: QdrantClient | None = None
        self._encoder: AsyncOpenAI | None = None
        self._collection = settings.qdrant_rag_collection

    def connect(self):
        self._qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._encoder = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.llm_api_key,
        )
        collections = [c.name for c in self._qdrant.get_collections().collections]
        if self._collection not in collections:
            self._qdrant.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    async def _embed(self, text: str) -> list[float]:
        try:
            resp = await self._encoder.embeddings.create(
                input=[text[:8000]],
                model=settings.embedding_model,
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning("Embedding fallback for RAG: %s", e)
            digest = hashlib.sha384(text.encode()).digest()
            return [b / 255.0 for b in digest]

    @staticmethod
    def chunk_text(text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
        return chunks

    async def index_file(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        file_path: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        if not self._qdrant:
            self.connect()

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)

        raw = path.read_text(encoding="utf-8", errors="replace")
        chunks = self.chunk_text(raw)
        if not chunks:
            raise ValueError("No indexable text in file")

        doc = Document(
            user_id=user_id,
            filename=filename or path.name,
            file_path=str(path),
            chunk_count=len(chunks),
        )
        db.add(doc)
        await db.flush()

        points = []
        for i, chunk in enumerate(chunks):
            vector = await self._embed(chunk)
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": str(doc.id),
                        "user_id": str(user_id),
                        "filename": doc.filename,
                        "chunk_index": i,
                        "content": chunk,
                    },
                )
            )

        self._qdrant.upsert(collection_name=self._collection, points=points)
        await db.commit()
        await db.refresh(doc)

        return {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "chunks_indexed": len(chunks),
        }

    async def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = limit or settings.rag_retrieval_limit
        if not self._qdrant:
            try:
                self.connect()
            except Exception:
                return []

        try:
            vector = await self._embed(query)
            results = self._qdrant.search(
                collection_name=self._collection,
                query_vector=vector,
                query_filter={"must": [{"key": "user_id", "match": {"value": str(user_id)}}]},
                limit=limit,
            )
            return [
                {
                    "content": hit.payload.get("content", ""),
                    "filename": hit.payload.get("filename", ""),
                    "score": hit.score,
                    "source": "rag",
                }
                for hit in results
            ]
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e)
            return []

    async def list_documents(self, db: AsyncSession, user_id: uuid.UUID) -> list[Document]:
        result = await db.execute(
            select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())


rag_store = RAGStore()
