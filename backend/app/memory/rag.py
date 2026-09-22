"""RAG: document chunking, indexing (Qdrant), and semantic retrieval."""

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.embeddings import VECTOR_SIZE, embed_text
from app.memory.extract import extract_file_text
from app.memory.qdrant_util import ensure_collection
from app.models.database import Document

logger = logging.getLogger(__name__)

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


class RAGStore:
    def __init__(self):
        self._qdrant: QdrantClient | None = None
        self._collection = settings.qdrant_rag_collection

    def connect(self):
        self._qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        ensure_collection(self._qdrant, self._collection, VECTOR_SIZE)

    async def _embed(self, text: str) -> list[float]:
        return await embed_text(text)

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

        raw = extract_file_text(path)
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
            if len(vector) != VECTOR_SIZE:
                raise ValueError(f"Embedding dim {len(vector)} != {VECTOR_SIZE}")
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
                query_filter=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]
                ),
                limit=limit,
            )
            return [
                {
                    "content": hit.payload.get("content", ""),
                    "filename": hit.payload.get("filename", ""),
                    "score": hit.score,
                    "source": "rag",
                    "document_id": hit.payload.get("document_id", ""),
                    "chunk_index": hit.payload.get("chunk_index", 0),
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

    async def count_points(self, user_id: uuid.UUID | None = None) -> int:
        if not self._qdrant:
            try:
                self.connect()
            except Exception:
                return 0
        if user_id is None:
            info = self._qdrant.get_collection(self._collection)
            return int(info.points_count or 0)
        res = self._qdrant.count(
            collection_name=self._collection,
            count_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]),
            exact=True,
        )
        return int(res.count)

    async def sample_chunks(self, user_id: uuid.UUID, limit: int = 8) -> list[dict[str, Any]]:
        if not self._qdrant:
            try:
                self.connect()
            except Exception:
                return []
        points, _ = self._qdrant.scroll(
            collection_name=self._collection,
            scroll_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id": str(p.id),
                "filename": (p.payload or {}).get("filename"),
                "chunk_index": (p.payload or {}).get("chunk_index"),
                "content": ((p.payload or {}).get("content") or "")[:240],
            }
            for p in points
        ]


rag_store = RAGStore()
