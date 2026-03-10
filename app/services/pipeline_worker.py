"""
Pipeline worker: FastAPI service that runs the full RAG pipeline (ingest -> chunk -> embed -> index).
Runs in a separate pod so the UI pod stays light and does not crash under load.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

# Ensure app logs are visible (e.g. kubectl logs)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Max lines to keep in verbose log (avoid unbounded growth)
_MAX_LOG_LINES = 3000

# State shared with pipeline callback
_run_state = {
    "running": False,
    "phase": "",
    "current": 0,
    "total": 0,
    "message": "",
    "last_summary": None,
    "error": None,
    "log_lines": [],  # Verbose console for UI
}


def _progress_callback(phase: str, current: int, total: int, message: str | None) -> None:
    _run_state["phase"] = phase
    _run_state["current"] = current
    _run_state["total"] = total
    _run_state["message"] = message or ""
    # Append one verbose line for the console
    total_str = str(total) if total else "?"
    msg = message or ""
    line = f"[{phase}] {current}/{total_str} — {msg}".strip()
    if line:
        _run_state["log_lines"].append(line)
        if len(_run_state["log_lines"]) > _MAX_LOG_LINES:
            _run_state["log_lines"] = _run_state["log_lines"][-_MAX_LOG_LINES:]


def _run_pipeline(data_directory: str, full_rebuild: bool) -> None:
    _run_state["log_lines"] = []
    try:
        _run_state["log_lines"].append(f">> Starting pipeline — data_directory={data_directory} full_rebuild={full_rebuild}")
        log.info("Pipeline run starting: data_directory=%s full_rebuild=%s", data_directory, full_rebuild)
        from app.core.pipeline import run_pipeline
        summary = run_pipeline(
            data_directory=data_directory,
            full_rebuild=full_rebuild,
            on_progress=_progress_callback,
        )
        _run_state["last_summary"] = summary
        _run_state["error"] = None
        done_msg = f">> Done. documents_loaded={summary.get('documents_loaded')} chunks_created={summary.get('chunks_created')} indexed={summary.get('indexed')} errors={len(summary.get('errors', []))}"
        if summary.get("chunking_seconds") is not None or summary.get("embedding_seconds") is not None:
            ch = summary.get("chunking_seconds")
            em = summary.get("embedding_seconds")
            done_msg += f" | chunking={ch}s embedding={em}s"
        _run_state["log_lines"].append(done_msg)
        log.info("Pipeline run finished: documents_loaded=%s chunks_created=%s indexed=%s errors=%s",
                 summary.get("documents_loaded"), summary.get("chunks_created"), summary.get("indexed"), summary.get("errors"))
    except Exception as e:
        _run_state["log_lines"].append(f">> FAILED: {e}")
        log.exception("Pipeline run failed")
        _run_state["error"] = str(e)
        _run_state["last_summary"] = {
            "documents_loaded": 0,
            "chunks_created": 0,
            "indexed": 0,
            "errors": [str(e)],
            "failed_at_phase": _run_state.get("phase", ""),
            "failed_at": f"{_run_state.get('current', 0)}/{_run_state.get('total', 0)}",
        }
    finally:
        _run_state["running"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_state["running"] = False
    _run_state["error"] = None
    yield
    # shutdown if needed
    pass


app = FastAPI(title="MORISLEX-RAG Pipeline Worker", lifespan=lifespan)


def _root_response():
    return {
        "service": "morislex-rag-pipeline",
        "endpoints": {
            "health": "GET /health or GET /api/health",
            "preflight": "GET /preflight?path=/data or GET /api/preflight?path=/data",
            "check_path": "GET /check-path?path=/data or GET /api/check-path?path=/data",
            "status": "GET /status or GET /api/status",
            "run_pipeline": "POST /run-pipeline or POST /api/run-pipeline",
        },
    }


@app.get("/")
def root():
    """Identify this service and list endpoints (so you can confirm you're hitting the pipeline, not the UI)."""
    return _root_response()


class RunPipelineRequest(BaseModel):
    data_directory: str
    full_rebuild: bool = True


@app.post("/run-pipeline")
def run_pipeline_endpoint(req: RunPipelineRequest):
    """Start the pipeline in the background. Returns immediately."""
    if _run_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running.")
    _run_state["running"] = True
    _run_state["error"] = None
    _run_state["last_summary"] = None
    _run_state["log_lines"] = []
    _run_state["phase"] = "starting"
    _run_state["current"] = 0
    _run_state["total"] = 0
    _run_state["message"] = ""
    thread = threading.Thread(
        target=_run_pipeline,
        kwargs={"data_directory": req.data_directory, "full_rebuild": req.full_rebuild},
        daemon=True,
    )
    thread.start()
    return {"status": "started", "message": "Pipeline running in background."}


@app.get("/status")
def status():
    """Current run state for UI polling (includes verbose log_lines for console)."""
    return {
        "running": _run_state["running"],
        "phase": _run_state["phase"],
        "current": _run_state["current"],
        "total": _run_state["total"],
        "message": _run_state["message"],
        "last_summary": _run_state["last_summary"],
        "error": _run_state["error"],
        "log_lines": list(_run_state.get("log_lines", [])),
    }


def _check_path_impl(path: str = ""):
    from app.core.ingest import check_data_directory
    return check_data_directory(path or None)


def _preflight_impl(path: str = "", max_files: int = 100, preview_chars: int = 400):
    from app.core.ingest import preflight
    return preflight(path or None, max_files=max_files, preview_chars=preview_chars)


@app.get("/preflight")
def preflight_endpoint(path: str = "", max_files: int = 100, preview_chars: int = 400):
    """Discovery: file list, sizes, previews for the given data path. For UI 'Validate & show files'."""
    return _preflight_impl(path, max_files=max_files, preview_chars=preview_chars)


@app.get("/check-path")
@app.get("/checkpath")  # alias in case of path normalization
def check_path(path: str = ""):
    """Diagnostic: what does the worker see at this path? Use when you get 0 documents."""
    return _check_path_impl(path)


@app.get("/health")
def health():
    """Liveness/readiness."""
    return {"ok": True}


# /api/* duplicates in case something in front only forwards /health or /api
@app.get("/api")
def api_root():
    return _root_response()


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.get("/api/check-path")
@app.get("/api/checkpath")
def api_check_path(path: str = ""):
    return _check_path_impl(path)


@app.get("/api/preflight")
def api_preflight(path: str = "", max_files: int = 100, preview_chars: int = 400):
    return _preflight_impl(path, max_files=max_files, preview_chars=preview_chars)


@app.get("/api/status")
def api_status():
    return {
        "running": _run_state["running"],
        "phase": _run_state["phase"],
        "current": _run_state["current"],
        "total": _run_state["total"],
        "message": _run_state["message"],
        "last_summary": _run_state["last_summary"],
        "error": _run_state["error"],
        "log_lines": list(_run_state.get("log_lines", [])),
    }


@app.post("/api/run-pipeline")
def api_run_pipeline_endpoint(req: RunPipelineRequest):
    if _run_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running.")
    _run_state["running"] = True
    _run_state["error"] = None
    _run_state["last_summary"] = None
    _run_state["log_lines"] = []
    _run_state["phase"] = "starting"
    _run_state["current"] = 0
    _run_state["total"] = 0
    _run_state["message"] = ""
    thread = threading.Thread(
        target=_run_pipeline,
        kwargs={"data_directory": req.data_directory, "full_rebuild": req.full_rebuild},
        daemon=True,
    )
    thread.start()
    return {"status": "started", "message": "Pipeline running in background."}


@app.exception_handler(404)
async def not_found_handler(request: Request, _exc):
    """If you see this body, you are hitting the pipeline worker; the path was wrong."""
    return JSONResponse(
        status_code=404,
        content={
            "service": "morislex-rag-pipeline",
            "detail": "Not Found",
            "path_tried": str(request.url.path),
            "try_these": [
                "GET /",
                "GET /api",
                "GET /health",
                "GET /api/health",
                "GET /check-path?path=/data",
                "GET /api/check-path?path=/data",
                "GET /status",
            ],
        },
    )


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
