"""
Ingest: load documents from Engine export (for_chunking.csv + manifest).
Data directory = Engine data root (contains exports/ and extracted/).
Paths in CSV are resolved relative to that root; /app/data/ prefix is stripped.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterator

from app.core.config import get_config
from app.models.schemas import Document


# ── Data directory (single source of truth) ─────────────────────────────────

def resolve_data_dir(data_directory: str | Path | None = None) -> Path:
    """
    Resolve the Engine data root to an absolute path.
    Use this for all ingest operations so UI and worker agree.
    """
    config = get_config()
    raw = data_directory if data_directory is not None and str(data_directory).strip() else config.get_data_directory()
    raw = str(raw or "").strip() or "."
    data_dir = Path(raw)
    if not data_dir.is_absolute():
        data_dir = (Path(__file__).resolve().parent.parent.parent / data_dir).resolve()
    return data_dir.resolve()


def _find_file(data_dir: Path, *candidates: str) -> Path | None:
    for name in candidates:
        p = data_dir / name
        if p.exists():
            return p
    return None


def get_chunking_csv_path(data_dir: Path) -> Path | None:
    """Location of for_chunking.csv (exports/ or root)."""
    return _find_file(data_dir, "exports/for_chunking.csv", "for_chunking.csv")


def resolve_text_path(data_dir: Path, text_path: str) -> Path:
    """
    Resolve CSV text_path to an absolute path under data_dir.
    - /app/data/... -> data_dir / suffix (Engine convention)
    - relative -> data_dir / text_path
    - other absolute -> try under data_dir/extracted/... or data_dir/exports/...
    """
    text_path = (text_path or "").strip()
    if not text_path:
        return data_dir / "_empty"
    # Engine writes /app/data/extracted/... or /app/data/exports/...
    if text_path.startswith("/app/data/"):
        suffix = text_path[len("/app/data/"):].lstrip("/")
        return (data_dir / suffix).resolve()
    if text_path.startswith("/data/"):
        suffix = text_path[len("/data/"):].lstrip("/")
        return (data_dir / suffix).resolve()
    # Relative path
    if not Path(text_path).is_absolute():
        return (data_dir / text_path).resolve()
    # Absolute path from another machine: take extracted/ or exports/ tail
    p = Path(text_path)
    parts = p.parts
    if "extracted" in parts:
        idx = list(parts).index("extracted")
        return (data_dir / Path(*parts[idx:])).resolve()
    if "exports" in parts:
        idx = list(parts).index("exports")
        return (data_dir / Path(*parts[idx:])).resolve()
    return (data_dir / p.name).resolve()


# ── Diagnostics (for 0 documents / 0 chunks) ────────────────────────────────

def check_data_directory(data_directory: str | Path | None = None) -> dict:
    """
    Basic diagnostic: does the data dir exist, is for_chunking.csv present?
    """
    data_dir = resolve_data_dir(data_directory)
    out = {
        "data_dir": str(data_dir),
        "exists": data_dir.exists(),
        "chunking_found": False,
        "chunking_path": None,
        "top_level": [],
    }
    if not data_dir.exists():
        return out
    try:
        out["top_level"] = [p.name for p in data_dir.iterdir()][:25]
    except (OSError, PermissionError):
        pass
    chunking_path = get_chunking_csv_path(data_dir)
    if chunking_path:
        out["chunking_found"] = True
        out["chunking_path"] = str(chunking_path)
    return out


def diagnose_ingest(data_dir: Path, documents: list[Document] | None = None) -> dict:
    """
    Rich diagnostic when we get 0 documents or 0 chunks.
    Returns: data_dir, chunking_path, chunking_exists, num_docs, sample_paths (first 5 with exists), num_files_exist.
    """
    data_dir = data_dir.resolve()
    diag: dict = {
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.exists(),
        "chunking_path": None,
        "chunking_exists": False,
        "num_documents_from_csv": 0,
        "sample_resolved_paths": [],
        "num_files_exist": 0,
    }
    chunking_path = get_chunking_csv_path(data_dir)
    if chunking_path:
        diag["chunking_path"] = str(chunking_path)
        diag["chunking_exists"] = chunking_path.exists()
    if documents:
        diag["num_documents_from_csv"] = len(documents)
        exist_count = 0
        for i, doc in enumerate(documents):
            if i >= 5 and exist_count > 0:
                break
            p = Path(doc.text_path)
            exists = p.exists()
            if exists:
                exist_count += 1
            if i < 5:
                diag["sample_resolved_paths"].append({
                    "path": doc.text_path,
                    "exists": exists,
                })
        diag["num_files_exist"] = sum(1 for doc in documents if Path(doc.text_path).exists())
    return diag


# ── Load documents (Engine contract) ───────────────────────────────────────

def load_documents(data_directory: str | Path | None = None) -> list[Document]:
    """
    Load document list from for_chunking.csv; resolve each text_path under data_dir.
    Optional: rag_manifest.csv for title/top_level_class; exports/metadata/*.json for metadata.
    """
    data_dir = resolve_data_dir(data_directory)
    if not data_dir.exists():
        return []

    chunking_path = get_chunking_csv_path(data_dir)
    if not chunking_path or not chunking_path.exists():
        return []

    manifest_path = _find_file(data_dir, "exports/rag_manifest.csv", "rag_manifest.csv")
    metadata_dir = _find_file(data_dir, "exports/metadata", "metadata")
    manifest_row_by_uid: dict[str, dict] = {}
    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row.get("document_uid", "")
                    if uid:
                        manifest_row_by_uid[uid] = row
        except (OSError, csv.Error):
            pass

    documents: list[Document] = []
    try:
        with open(chunking_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = (row.get("document_uid") or "").strip()
                if not uid:
                    continue
                version_id = (row.get("version_id") or "").strip()
                text_path_raw = (row.get("text_path") or "").strip()
                content_hash = (row.get("content_hash") or "").strip()
                resolved_path = resolve_text_path(data_dir, text_path_raw)
                meta = manifest_row_by_uid.get(uid, {})
                title = (meta.get("title") or "").strip()
                top_level_class = (meta.get("top_level_class") or "").strip()
                source_id = (meta.get("source_id") or "").strip()
                metadata: dict = {}
                if metadata_dir:
                    meta_path = metadata_dir / f"{uid}.json"
                    if meta_path.exists():
                        try:
                            with open(meta_path, encoding="utf-8") as mf:
                                metadata = json.load(mf)
                        except (json.JSONDecodeError, OSError):
                            pass
                documents.append(
                    Document(
                        document_uid=uid,
                        version_id=version_id,
                        text_path=str(resolved_path),
                        content_hash=content_hash,
                        title=title or (metadata.get("title") or ""),
                        top_level_class=top_level_class or (metadata.get("top_level_class") or ""),
                        source_id=source_id or (metadata.get("source_id") or ""),
                        metadata=metadata,
                    )
                )
    except (OSError, csv.Error):
        return []
    return documents


def iter_document_texts(
    documents: list[Document],
) -> Iterator[tuple[Document, str]]:
    """Yield (document, text) only for documents whose resolved text file exists and is readable."""
    for doc in documents:
        p = Path(doc.text_path)
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield doc, text


def count_readable_documents(documents: list[Document]) -> int:
    """Number of documents that have an existing, readable text file."""
    return sum(1 for _ in iter_document_texts(documents))


# ── Preflight (for UI: file list, sizes, previews) ──────────────────────────

def preflight(
    data_directory: str | Path | None = None,
    max_files: int = 100,
    preview_chars: int = 400,
) -> dict:
    """
    Discovery for the UI: what files will the pipeline see?
    Counts existence for ALL documents; detailed list (size, preview) only for first max_files.
    Returns: data_dir, diagnostic, total_documents, num_files_exist, files (list of file info).
    """
    data_dir = resolve_data_dir(data_directory)
    diagnostic = {**check_data_directory(data_dir), "hint": "Use the Engine data root (contains exports/ and extracted/). In K8s use /data."}
    documents = load_documents(data_dir)
    total = len(documents)
    # Count existence for every document (no cap)
    num_exist = sum(1 for doc in documents if Path(doc.text_path).exists())
    # Build detailed list only for first max_files (size, preview)
    files: list[dict] = []
    for i, doc in enumerate(documents):
        if i >= max_files:
            break
        p = Path(doc.text_path)
        exists = p.exists()
        size_bytes: int | None = None
        size_chars: int | None = None
        preview = ""
        if exists:
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
                size_chars = len(raw)
                size_bytes = p.stat().st_size
                preview = (raw[:preview_chars] + ("…" if len(raw) > preview_chars else "")).strip()
            except OSError:
                pass
        files.append({
            "document_uid": doc.document_uid,
            "path": doc.text_path,
            "path_short": p.name if p else "",
            "exists": exists,
            "size_bytes": size_bytes,
            "size_chars": size_chars,
            "preview": preview,
            "title": (getattr(doc, "title", None) or "")[:80],
        })
    return {
        "data_dir": str(data_dir),
        "diagnostic": diagnostic,
        "total_documents": total,
        "num_files_exist": num_exist,
        "num_files_missing": total - num_exist,
        "files": files,
    }
