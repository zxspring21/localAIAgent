"""Shared embeddings. Qdrant collections are 384-dimensional.

localhost:8000 MLX chat servers usually have no /embeddings. SHA-384
digests are 48 bytes and must never be upserted as vectors.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

VECTOR_SIZE = 384
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{1,32}")

_client: AsyncOpenAI | None = None
_warned_api = False


def vector_size() -> int:
    return VECTOR_SIZE


def _encoder() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = settings.openai_api_key or settings.llm_api_key or "local"
        base = settings.embedding_base_url
        if settings.openai_api_key and "localhost" in (base or ""):
            base = "https://api.openai.com/v1"
            api_key = settings.openai_api_key
        _client = AsyncOpenAI(base_url=base, api_key=api_key, timeout=8.0)
    return _client


def lexical_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    """Signed feature hashing — works offline and is always `dim` floats."""
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower()) or ["empty"]
    for token in tokens[:4000]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] & 1 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _decode_embedding(raw) -> list[float]:
    if isinstance(raw, str):
        import base64
        import struct

        data = base64.b64decode(raw)
        n = len(data) // 4
        return list(struct.unpack(f"<{n}f", data[: n * 4]))
    return list(raw)


async def embed_text(text: str) -> list[float]:
    global _warned_api
    snippet = (text or "")[:8000]
    try:
        resp = await _encoder().embeddings.create(
            input=[snippet],
            model=settings.embedding_model,
        )
        vector = _decode_embedding(resp.data[0].embedding)
        if len(vector) == VECTOR_SIZE:
            return vector
        if not _warned_api:
            logger.warning(
                "Embedding API returned dim %s, need %s — using lexical hash",
                len(vector),
                VECTOR_SIZE,
            )
            _warned_api = True
    except Exception as e:
        if not _warned_api:
            logger.warning("Embedding API unavailable (%s); using lexical hash of dim %s", e, VECTOR_SIZE)
            _warned_api = True
    return lexical_embedding(snippet)
