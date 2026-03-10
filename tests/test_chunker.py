"""Tests for chunker."""
from app.models.schemas import Document
from app.core.chunker import chunk


def test_chunk_fixed():
    doc = Document(document_uid="doc_1", version_id="v1")
    chunks = chunk(doc, "Hello world. " * 100, chunk_size=50, overlap=5)
    assert len(chunks) >= 2
    assert all(c.document_uid == "doc_1" for c in chunks)


def test_chunk_with_headers():
    doc = Document(document_uid="doc_1", version_id="v1")
    text = "# Title\n\nFirst section.\n\n## Section 2\n\nSecond."
    chunks = chunk(doc, text)
    assert len(chunks) >= 1
    assert chunks[0].text
