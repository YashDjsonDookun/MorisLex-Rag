"""Chroma vector store wrapper (persistent, configurable path)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import get_config
from app.models.schemas import Chunk, ChunkWithMetadata

log = logging.getLogger(__name__)

_collection = None


def _client_closed_error(exc: BaseException) -> bool:
    """True if the exception (or its cause) indicates the Chroma/httpx client was closed."""
    def check(e: BaseException | None) -> bool:
        if e is None:
            return False
        msg = (getattr(e, "message", "") or str(e)).lower()
        if "client has been closed" in msg or "cannot send a request" in msg:
            return True
        return check(getattr(e, "__cause__", None)) or check(getattr(e, "__context__", None))
    return check(exc)


def _reset_collection() -> None:
    global _collection
    _collection = None


def reset_client() -> None:
    """Drop the Chroma client so the next call uses a fresh connection. Use after 'client has been closed' errors."""
    _reset_collection()


def is_client_closed_error(exc: BaseException) -> bool:
    """True if the exception indicates the Chroma/httpx client was closed."""
    return _client_closed_error(exc)


def _get_collection():
    global _collection
    for attempt in range(2):
        try:
            if _collection is None:
                import chromadb
                from chromadb.config import Settings
                config = get_config()
                path = config.resolve_path(config.vector_store.path)
                path.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
                _collection = client.get_or_create_collection(
                    name=config.vector_store.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            return _collection
        except Exception as e:
            if _client_closed_error(e) and attempt == 0:
                log.warning("Chroma client closed in _get_collection; reconnecting: %s", e)
                _reset_collection()
                continue
            raise


def add_chunks(chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    """Upsert chunks with embeddings into Chroma. Retries once with fresh client if connection was closed."""
    if not chunks or not embeddings:
        return
    ids = [f"{c.document_uid}_{c.chunk_index}" for c in chunks]
    metadatas = [
        {
            "document_uid": c.document_uid,
            "version_id": c.version_id,
            "chunk_index": c.chunk_index,
            "title": (c.title or "")[:500],
            "top_level_class": (c.top_level_class or "")[:200],
        }
        for c in chunks
    ]
    payload = (ids, embeddings, metadatas, [c.text for c in chunks])
    for attempt in range(2):
        try:
            coll = _get_collection()
            coll.upsert(ids=payload[0], embeddings=payload[1], metadatas=payload[2], documents=payload[3])
            return
        except Exception as e:
            if _client_closed_error(e) and attempt == 0:
                log.warning("Chroma client closed (e.g. long run in background thread); reconnecting: %s", e)
                _reset_collection()
                continue
            raise


# SQLite (Chroma backend) limits bind params per statement; delete in batches.
_CLEAR_BATCH_SIZE = 500


def clear_collection() -> None:
    """Delete all vectors (for full rebuild). Batched to avoid SQLite 'too many SQL variables'. Retries with fresh client if closed."""
    for attempt in range(2):
        try:
            coll = _get_collection()
            while True:
                n = coll.count()
                if n == 0:
                    return
                batch_size = min(n, _CLEAR_BATCH_SIZE)
                ids = coll.get(limit=batch_size)["ids"]
                if not ids:
                    return
                coll.delete(ids=ids)
        except Exception as e:
            if _client_closed_error(e) and attempt == 0:
                log.warning("Chroma client closed during clear_collection; reconnecting: %s", e)
                _reset_collection()
                continue
            raise


def query_vectors(query_embedding: list[float], top_k: int = 5, where: dict[str, Any] | None = None) -> list[ChunkWithMetadata]:
    """Return top-k chunks by similarity."""
    coll = _get_collection()
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out: list[ChunkWithMetadata] = []
    ids = res["ids"][0] if res["ids"] else []
    docs = res["documents"][0] if res["documents"] else []
    metas = res["metadatas"][0] if res["metadatas"] else []
    dists = res["distances"][0] if res.get("distances") else []
    for i, id_ in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        # Chroma cosine distance: lower is better; convert to score ~ 1 - distance
        dist = dists[i] if i < len(dists) else 0.0
        score = max(0.0, 1.0 - dist) if dist is not None else 0.0
        text = docs[i] if i < len(docs) else ""
        out.append(
            ChunkWithMetadata(
                id=id_,
                document_uid=meta.get("document_uid", ""),
                version_id=meta.get("version_id", ""),
                chunk_index=int(meta.get("chunk_index", 0)),
                text=text,
                title=meta.get("title", ""),
                top_level_class=meta.get("top_level_class", ""),
                metadata=meta,
                score=score,
            )
        )
    return out


def count() -> int:
    """Return number of vectors in collection."""
    coll = _get_collection()
    return coll.count()
