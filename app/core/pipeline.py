"""Orchestrate ingest -> chunk -> embed -> index with progress callbacks and logging."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from app.core.config import get_config
from app.core.chunker import chunk
from app.core.ingest import (
    resolve_data_dir,
    load_documents,
    iter_document_texts,
    check_data_directory,
    diagnose_ingest,
    count_readable_documents,
)
from app.core.embedder import embed_chunks, ensure_model_loaded, get_embedding_device
from app.core.vector_store import add_chunks, clear_collection, reset_client, is_client_closed_error
from app.core.run_control import clear_stop, stop_requested
from app.core.indexed_state import (
    load_indexed_state,
    save_indexed_state,
    mark_indexed,
    clear_indexed_state,
    documents_to_index,
)
from app.models.schemas import Chunk

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str | None], None]

# Defaults if config is missing
DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP = 64
DEFAULT_EMBED_BATCH_SIZE = 128


def _format_eta(seconds: float) -> str:
    """Format seconds as human ETA e.g. '~5m' or '~1h 2m'."""
    if seconds < 0 or not (seconds < 1e6):
        return ""
    if seconds < 60:
        return f"~{int(round(seconds))}s"
    if seconds < 3600:
        m = int(round(seconds / 60))
        return f"~{m}m"
    h = int(seconds // 3600)
    m = int(round((seconds % 3600) / 60))
    if m == 0:
        return f"~{h}h"
    return f"~{h}h {m}m"


def _eta_suffix(current: int, total: int, phase_start: float) -> str:
    """Return ' ETA ~Xm' when we have progress and total; else ''."""
    if total <= 0 or current <= 0 or current >= total:
        return ""
    elapsed = time.monotonic() - phase_start
    if elapsed <= 0:
        return ""
    rate = current / elapsed
    remaining = total - current
    eta_sec = remaining / rate
    eta_str = _format_eta(eta_sec)
    return f" ETA {eta_str}" if eta_str else ""


def run_pipeline(
    data_directory: str | None = None,
    full_rebuild: bool = True,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """
    Run full pipeline: ingest -> chunk -> embed -> index.
    Returns summary: documents_loaded, chunks_created, indexed, errors.
    """
    def report(phase: str, current: int, total: int, message: str | None = None) -> None:
        if on_progress:
            on_progress(phase, current, total, message)

    clear_stop()
    summary = {"documents_loaded": 0, "chunks_created": 0, "indexed": 0, "errors": []}

    try:
        config = get_config()
        data_dir = resolve_data_dir(data_directory or config.get_data_directory())
    except Exception as e:
        log.exception("Pipeline config/path failed")
        summary["errors"].append(str(e))
        return summary

    chunk_size = DEFAULT_CHUNK_SIZE
    overlap = DEFAULT_OVERLAP
    try:
        chunk_size = max(64, getattr(config.chunking, "chunk_size", None) or DEFAULT_CHUNK_SIZE)
        overlap = max(0, getattr(config.chunking, "overlap", None) or DEFAULT_OVERLAP)
        overlap = min(overlap, chunk_size // 2)
    except Exception:
        pass

    log.info("Pipeline starting: data_dir=%s chunk_size=%s overlap=%s", data_dir, chunk_size, overlap)

    all_chunks: list[Chunk] = []
    total_docs = 0
    documents: list = []
    try:
        report("ingesting", 0, 0, "Loading documents from CSV...")
        documents = load_documents(data_dir)
        summary["documents_loaded"] = len(documents)
        report("ingesting", 1, 1, f"Loaded {len(documents)} documents from for_chunking.csv")

        if not documents:
            log.warning("No documents loaded from %s", data_dir)
            report("ingesting", 0, 0, "No documents found.")
            summary["diagnostic"] = {**check_data_directory(data_dir), "hint": "Ensure data_dir is the Engine data root. In K8s use /data."}
            return summary

        report("ingesting", 0, 0, "Counting readable text files...")
        num_readable = count_readable_documents(documents)
        report("ingesting", 1, 1, f"Found {num_readable} readable text files (of {len(documents)} in CSV)")
        if num_readable == 0:
            log.warning("CSV has %s documents but no readable text files", len(documents))
            summary["diagnostic"] = diagnose_ingest(data_dir, documents)
            summary["diagnostic"]["hint"] = "No resolved text files exist. In K8s ensure the pipeline pod has data mounted at this path."
            report("chunking", 0, len(documents), "No readable text files.")
            return summary

        indexed_state = load_indexed_state()
        if full_rebuild:
            report("indexing", 0, 0, "Clearing existing index...")
            clear_collection()
            clear_indexed_state()
            indexed_state = {}
            report("indexing", 0, 0, "Index cleared.")

        to_process = documents_to_index(documents, indexed_state)
        num_new = len(to_process)
        report("ingesting", 0, 0, f"Incremental: {num_new} new/changed of {len(documents)} total (skipping {len(documents) - num_new} already indexed)")
        if num_new == 0:
            report("chunking", 0, 0, "Nothing new to index.")
            summary["chunks_created"] = 0
            summary["indexed"] = 0
            return summary

        all_chunks.clear()
        total_docs = num_new
        report("chunking", 0, total_docs, f"Chunking {num_new} documents (chunk_size={chunk_size} overlap={overlap})")
        log.info("Chunking %s new documents (chunk_size=%s)", total_docs, chunk_size)

        t_chunk_start = time.monotonic()
        for i, (doc, text) in enumerate(iter_document_texts(to_process)):
            if stop_requested():
                summary["errors"].append("Stop requested by user.")
                break
            fname = Path(doc.text_path).name if getattr(doc, "text_path", None) else ""
            eta = _eta_suffix(i + 1, total_docs, t_chunk_start)
            report("chunking", i + 1, total_docs, f"{doc.document_uid} | {fname} | {len(text):,} chars{eta}")
            if i == 0:
                log.info("First doc: %s %s chars", doc.document_uid, len(text))
            chunks = chunk(doc, text, chunk_size=chunk_size, overlap=overlap)
            all_chunks.extend(chunks)
            mark_indexed(indexed_state, doc.document_uid, doc.content_hash or "")
            if i == 0 and chunks:
                log.info("First doc produced %s chunks", len(chunks))

        summary["chunks_created"] = len(all_chunks)
        t_chunk_sec = time.monotonic() - t_chunk_start
        summary["chunking_seconds"] = round(t_chunk_sec, 1)
        report("chunking", total_docs, total_docs, f"Chunking done: {len(all_chunks)} chunks from {total_docs} documents")
        log.info("Chunking done: %s total chunks in %.1fs", len(all_chunks), t_chunk_sec)

        if not all_chunks:
            summary["diagnostic"] = diagnose_ingest(data_dir, documents)
            summary["diagnostic"]["hint"] = "Chunker produced 0 chunks. Check chunk_size."
            report("chunking", total_docs, total_docs, "No chunks produced.")
            return summary

        try:
            batch_size = max(1, getattr(config.embedding, "batch_size", None) or DEFAULT_EMBED_BATCH_SIZE)
        except Exception:
            batch_size = DEFAULT_EMBED_BATCH_SIZE
        # Use larger batches on GPU for much faster embedding (mps/cuda)
        device = get_embedding_device()
        if device in ("mps", "cuda") and batch_size < 256:
            batch_size = 256
        # Pre-load model and log device so console shows whether GPU is used
        actual_device = ensure_model_loaded()
        device_label = {"cpu": "CPU", "cuda": "NVIDIA GPU", "mps": "Apple Silicon (MPS)"}.get(actual_device, actual_device)
        report("embedding", 0, len(all_chunks), f"Using {device_label} | Embedding {len(all_chunks)} chunks in batches of {batch_size}...")
        num_batches = (len(all_chunks) + batch_size - 1) // batch_size
        t_embed_start = time.monotonic()
        for batch_num, start in enumerate(range(0, len(all_chunks), batch_size)):
            if stop_requested():
                break
            end = min(start + batch_size, len(all_chunks))
            batch = all_chunks[start:end]
            eta = _eta_suffix(end, len(all_chunks), t_embed_start)
            report("embedding", start, len(all_chunks), f"Embedding batch {batch_num + 1}/{num_batches} ({len(batch)} chunks){eta}")
            for batch_attempt in range(2):
                try:
                    embeddings = embed_chunks(batch)
                    report("indexing", end, len(all_chunks), f"Indexing batch {batch_num + 1}/{num_batches}{eta}")
                    add_chunks(batch, embeddings)
                    summary["indexed"] += len(batch)
                    break
                except Exception as e:
                    if is_client_closed_error(e) and batch_attempt == 0:
                        log.warning("Client closed during batch (embed/index); resetting Chroma and retrying: %s", e)
                        reset_client()
                        continue
                    raise
        save_indexed_state(indexed_state)
        t_embed_sec = time.monotonic() - t_embed_start
        summary["embedding_seconds"] = round(t_embed_sec, 1)
        summary["indexed"] = summary["indexed"]  # already set in loop
        report("indexing", len(all_chunks), len(all_chunks), f"Done. Indexed {summary['indexed']} chunks.")
        total_sec = (summary.get("chunking_seconds") or 0) + t_embed_sec
        log.info(
            "Pipeline done: indexed %s chunks | chunking %.1fs embedding %.1fs total ~%.1fs",
            summary["indexed"], summary.get("chunking_seconds", 0), t_embed_sec, total_sec,
        )

    except Exception as e:
        log.exception("Pipeline failed")
        summary["chunks_created"] = len(all_chunks)
        summary["errors"].append(str(e))
        try:
            if documents:
                summary["diagnostic"] = diagnose_ingest(data_dir, documents)
        except Exception:
            pass
        report("chunking", total_docs, total_docs, f"Error: {e}")
    return summary
