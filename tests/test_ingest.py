"""Tests for ingest: path resolution, manifest/chunking load."""
from pathlib import Path
import pytest
from app.core.config import load_config
from app.core.ingest import load_documents, resolve_text_path


def test_resolve_text_path_relative(tmp_path):
    assert resolve_text_path(tmp_path, "extracted/foo.md") == (tmp_path / "extracted" / "foo.md").resolve()


def test_resolve_text_path_app_data(tmp_path):
    out = resolve_text_path(tmp_path, "/app/data/extracted/primary/foo.md")
    assert "extracted" in str(out)
    assert out.name == "foo.md"


def test_load_documents_empty_dir(tmp_path):
    load_config()
    docs = load_documents(str(tmp_path))
    assert docs == []
