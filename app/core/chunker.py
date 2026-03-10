"""
Chunker: split document text into fixed-size overlapping chunks.
Rebuilt from scratch - no config, no strategies, no dependencies.
"""

from __future__ import annotations

from app.models.schemas import Document, Chunk


def chunk(document: Document, text: str, chunk_size: int = 512, overlap: int = 64) -> list[Chunk]:
    """
    Split text into chunks of chunk_size chars with overlap between chunks.
    Returns list of Chunk objects. Never raises.
    """
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    if not text:
        return []

    overlap = max(0, min(overlap, chunk_size - 1))

    chunks = []
    start = 0
    index = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end]
        if piece.strip():
            chunks.append(Chunk(
                document_uid=document.document_uid,
                version_id=document.version_id or "",
                chunk_index=index,
                text=piece,
                title=document.title or "",
                top_level_class=document.top_level_class or "",
                metadata=document.metadata if isinstance(document.metadata, dict) else {},
            ))
            index += 1
        start = end - overlap

    return chunks
