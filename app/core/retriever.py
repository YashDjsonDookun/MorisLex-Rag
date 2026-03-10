"""Retriever: query -> top-k chunks (wrapper-ready for API/MCP later)."""

from __future__ import annotations

from app.core.config import get_config
from app.core.embedder import embed_texts
from app.core.vector_store import query_vectors
from app.models.schemas import ChunkWithMetadata


def retrieve(
    query: str,
    top_k: int | None = None,
    filters: dict | None = None,
) -> list[ChunkWithMetadata]:
    """
    Retrieve top-k chunks for a query.
    Same interface for future HTTP GET /retrieve or LangChain retriever wrapper.
    """
    config = get_config()
    k = top_k if top_k is not None else config.retrieval.top_k
    if not query or k <= 0:
        return []
    query_embedding = embed_texts([query.strip()])[0]
    return query_vectors(query_embedding, top_k=k, where=filters)
