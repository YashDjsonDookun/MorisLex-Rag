"""Embedding: sentence-transformers, fully local (no HuggingFace API calls)."""

from __future__ import annotations

import logging
import os
import sys

from app.core.config import get_config
from app.models.schemas import Chunk

log = logging.getLogger(__name__)
_model = None


def _mps_available() -> bool:
    """True if PyTorch has MPS built and available (Apple Silicon)."""
    try:
        import torch
        if not getattr(torch.backends, "mps", None):
            return False
        if not torch.backends.mps.is_built():
            return False
        return torch.backends.mps.is_available()
    except Exception:
        return False


def _resolve_device() -> str:
    """Use config device; if 'cpu' or 'auto', use cuda (NVIDIA) or mps (Apple Silicon) when available."""
    config = get_config()
    device = (getattr(config.embedding, "device", None) or "cpu").strip().lower()
    # Treat "cpu" and "auto" as "auto-detect GPU"
    if device in ("cpu", "auto", ""):
        try:
            import torch
            if torch.cuda.is_available():
                log.info("Embedding device: cuda (NVIDIA GPU)")
                return "cuda"
            # Prefer MPS on macOS (Apple Silicon)
            if sys.platform == "darwin" and getattr(torch.backends, "mps", None):
                if torch.backends.mps.is_built() and torch.backends.mps.is_available():
                    log.info("Embedding device: mps (Apple Silicon GPU)")
                    return "mps"
                log.warning(
                    "Apple Silicon detected but MPS not available (is_built=%s, is_available=%s). "
                    "Use native ARM64 Python and: pip install torch --force-reinstall",
                    torch.backends.mps.is_built(),
                    torch.backends.mps.is_available(),
                )
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                log.info("Embedding device: mps (Apple Silicon GPU)")
                return "mps"
            # Diagnose why no GPU (so user can fix)
            if sys.platform == "darwin":
                mps = getattr(torch.backends, "mps", None)
                import platform
                built = mps.is_built() if mps else False
                avail = mps.is_available() if mps else False
                log.warning(
                    "Embedding device: cpu — MPS not used. Python arch=%s | MPS built=%s | MPS available=%s. "
                    "On Apple Silicon use native ARM64 Python and run: pip install torch --force-reinstall",
                    platform.machine(),
                    built,
                    avail,
                )
            else:
                # Linux container (e.g. Rancher Desktop): no MPS (macOS only), no CUDA unless NVIDIA
                log.warning(
                    "Embedding device: cpu — no GPU available in this environment. "
                    "Running in a Linux container? Apple MPS is macOS-only; run the pipeline on the host (Mac) to use the M4 GPU."
                )
        except Exception as e:
            log.warning("Could not detect GPU for embedding: %s — using cpu", e)
        return "cpu"
    return device


def get_embedding_device() -> str:
    """Return the device actually used for embedding (cpu, cuda, or mps)."""
    return _resolve_device()


def ensure_model_loaded() -> str:
    """Load the embedding model if needed and return the device it is on. Call at pipeline start to log device."""
    _get_model()
    return _resolve_device()


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        config = get_config()
        device = _resolve_device()
        model_name = config.embedding.model

        def _load(offline: bool):
            if offline:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
            else:
                os.environ.pop("HF_HUB_OFFLINE", None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
            # local_files_only=True avoids any HEAD request to huggingface.co when cache exists
            try:
                return SentenceTransformer(model_name, device=device, local_files_only=offline)
            except TypeError:
                return SentenceTransformer(model_name, device=device)

        try:
            _model = _load(offline=True)
        except Exception as e:
            err_msg = str(e).lower()
            if "couldn't connect" in err_msg or "cached files" in err_msg or "huggingface.co" in err_msg:
                log.warning("Model not in cache (offline). Trying once with network to download...")
                try:
                    _model = _load(offline=False)
                    log.info("Model downloaded. Future runs will use offline cache.")
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                except Exception as e2:
                    raise RuntimeError(
                        f"Could not load embedding model: {e2}. "
                        "Ensure network access to download once, or run: python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')\""
                    ) from e2
            elif device in ("mps", "cuda"):
                log.warning("Failed to load model on %s (%s), falling back to CPU", device, e)
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                try:
                    _model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
                except TypeError:
                    _model = SentenceTransformer(model_name, device="cpu")
            else:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                raise
        else:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts; returns list of vectors."""
    if not texts:
        return []
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def _is_client_closed_error(exc: BaseException) -> bool:
    msg = (getattr(exc, "message", "") or str(exc)).lower()
    if "client has been closed" in msg or "cannot send a request" in msg:
        return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    return cause is not None and _is_client_closed_error(cause)


def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    """Embed chunk texts. Retries once on 'client has been closed' (e.g. from tokenizer)."""
    for attempt in range(2):
        try:
            return embed_texts([c.text for c in chunks])
        except Exception as e:
            if _is_client_closed_error(e) and attempt == 0:
                log.warning("Embedder saw client closed; retrying batch: %s", e)
                continue
            raise
