"""
Track which documents are already indexed (by document_uid + content_hash).
Enables incremental pipeline: only process new or changed documents.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_config


FILENAME = "indexed_docs.json"


def _state_path() -> Path:
    config = get_config()
    return config.state_path / FILENAME


def load_indexed_state() -> dict[str, str]:
    """Return { document_uid: content_hash } for all indexed docs."""
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_indexed_state(state: dict[str, str]) -> None:
    """Persist indexed state."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=0), encoding="utf-8")


def mark_indexed(state: dict[str, str], document_uid: str, content_hash: str) -> None:
    state[document_uid] = content_hash


def clear_indexed_state() -> None:
    """Remove state file (for full rebuild)."""
    path = _state_path()
    if path.exists():
        path.unlink()


def documents_to_index(documents: list, state: dict[str, str]) -> list:
    """Filter to documents not yet indexed or with changed content_hash."""
    to_index = []
    for doc in documents:
        uid = getattr(doc, "document_uid", None) or ""
        ch = getattr(doc, "content_hash", None) or ""
        if not uid:
            continue
        if state.get(uid) != ch:
            to_index.append(doc)
    return to_index
