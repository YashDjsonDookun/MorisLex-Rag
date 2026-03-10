"""
Retrieval service: dedicated pod for search and RAG chat.
Reads from shared Chroma; no pipeline load. Run: python -m app.services.retrieval_service
Uses LLMService; supports model_tier (paywall-ready), streaming, observability logging.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.retriever import retrieve
from app.llm.service import chat_with_sources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="MORISLEX-RAG Retrieval", lifespan=lifespan)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5
    model_tier: str | None = None  # primary | fallback | comparison (paywall-ready)
    use_playground: bool = False
    stream: bool = False


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/retrieve")
def retrieve_endpoint(req: RetrieveRequest):
    """Retrieval test: query -> top-k chunks (no LLM)."""
    chunks = retrieve(req.query.strip(), top_k=req.top_k)
    return {"chunks": [c.model_dump() for c in chunks]}


def _get_model_tier_from_request(request: Request, body: ChatRequest) -> str | None:
    """Model tier: body.model_tier or X-Model-Tier header."""
    if body.model_tier and body.model_tier.strip():
        return body.model_tier.strip().lower()
    h = request.headers.get("X-Model-Tier", "").strip().lower()
    if h in ("primary", "fallback", "comparison"):
        return h
    return None


def _get_api_key_from_request(request: Request) -> str | None:
    """X-API-Key header (for future paywall; v1 no-op validation)."""
    return request.headers.get("X-API-Key", "").strip() or None


@app.post("/chat")
def chat_endpoint(req: ChatRequest, request: Request):
    """RAG chat: question -> answer + sources. Optional model_tier, stream; X-Model-Tier, X-API-Key (paywall-ready)."""
    try:
        _ = _get_api_key_from_request(request)  # v1: no-op; later validate and restrict model_tier by plan
        question = req.question.strip()
        tier = _get_model_tier_from_request(request, req)
        chunks = retrieve(question, top_k=req.top_k)
        answer_or_stream, sources = chat_with_sources(
            question,
            chunks,
            tier=tier,
            use_playground=req.use_playground,
            stream=req.stream,
        )

        if not req.stream:
            answer = answer_or_stream if isinstance(answer_or_stream, str) else "".join(answer_or_stream)
            return {"answer": answer, "sources": sources}

        # Streaming: return SSE or plain text stream
        def generate():
            if isinstance(answer_or_stream, str):
                yield answer_or_stream
                return
            for chunk in answer_or_stream:
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        logger.exception("Chat request failed")
        from fastapi.responses import JSONResponse
        hint = (
            "Check retrieval and Ollama logs: kubectl logs -n morislex-rag -l component=retrieval --tail=50; "
            "kubectl logs -n morislex-rag -l component=ollama --tail=50. "
            "If Ollama shows 'signal: killed' or 'Load failed', the pod likely ran out of memory (OOM)—increase memory in k8s/base/ollama-deployment.yaml and redeploy."
        )
        return JSONResponse(
            status_code=500,
            content={
                "answer": "",
                "sources": [],
                "error": str(e),
                "hint": hint,
            },
        )


def main():
    import uvicorn
    # Long timeout so Ollama model load + first token don't drop the connection.
    # Single worker: workers=2 can crash at startup in K8s (fork + sentence-transformers/Chroma not fork-safe in some envs).
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8082,
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    main()
