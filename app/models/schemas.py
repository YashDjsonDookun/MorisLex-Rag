"""Pydantic models for documents, chunks, and retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Single document from ingest (Engine contract)."""

    document_uid: str
    version_id: str = ""
    text_path: str = ""
    content_hash: str = ""
    title: str = ""
    top_level_class: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """One chunk of text for embedding/indexing."""

    document_uid: str
    version_id: str = ""
    chunk_index: int = 0
    text: str = ""
    title: str = ""
    top_level_class: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkWithMetadata(Chunk):
    """Chunk as returned by retriever (e.g. with score, id)."""

    score: float = 0.0
    id: str = ""
