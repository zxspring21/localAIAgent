"""Ensure Qdrant collections match VECTOR_SIZE."""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.memory.embeddings import VECTOR_SIZE

logger = logging.getLogger(__name__)


def ensure_collection(client: QdrantClient, name: str, size: int = VECTOR_SIZE) -> None:
    existing = {c.name: c for c in client.get_collections().collections}
    if name in existing:
        info = client.get_collection(name)
        current = None
        params = info.config.params.vectors
        if hasattr(params, "size"):
            current = params.size
        elif isinstance(params, dict) and "" in params:
            current = params[""].size
        if current == size:
            return
        logger.warning("Recreating Qdrant collection %s (had dim %s, need %s)", name, current, size)
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=size, distance=Distance.COSINE),
    )
