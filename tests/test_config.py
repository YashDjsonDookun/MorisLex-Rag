"""Tests for config loading."""
from pathlib import Path
from app.core.config import load_config, get_config, AppConfig


def test_load_config_defaults():
    load_config()
    c = get_config()
    assert c.project.name == "MorisLex-RAG"
    assert c.chunking.chunk_size == 512
    assert isinstance(c.get_data_directory(), str)
