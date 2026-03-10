"""LLMService: single entry for chat (and stream). Resolves tier, builds prompts, calls client, retries, logs."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Generator

from app.core.config import get_config
from app.llm.client_ollama import completion
from app.llm.models import LLMObservability
from app.llm.prompts import build_rag_user_content, get_system_prompt

logger = logging.getLogger(__name__)

# Retries for transient failures (e.g. Ollama still loading model)
MAX_RETRIES = 3
RETRY_DELAY_IF_CONNECTION_ERROR = 15  # seconds; give Ollama time to finish loading


def _get_llm_config():
    return get_config().llm


def _resolve_base_url_and_model(
    tier: str | None,
    use_playground: bool = False,
) -> tuple[str, str]:
    """Resolve (base_url, model) for the request. Validates strict_local when not playground."""
    c = _get_llm_config()
    if use_playground and c.playground.base_url and c.playground.model:
        return c.playground.base_url.strip(), c.playground.model.strip()
    base_url = c.base_url.strip()
    model = c.get_model_for_tier(tier or c.active_tier)
    if c.strict_local and not c.is_base_url_local():
        logger.warning("LLM base_url is not local but strict_local=True: %s", base_url)
    return base_url, model


def _build_messages(question: str, context: str) -> list[dict[str, str]]:
    """Build [system, user] messages for RAG."""
    system = get_system_prompt()
    user = build_rag_user_content(question, context, with_guardrail=True)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def chat(
    question: str,
    context_chunks: list[str],
    *,
    tier: str | None = None,
    use_playground: bool = False,
    stream: bool = False,
) -> str | Generator[str, None, None]:
    """
    RAG chat via LLMService: build messages, call Ollama with retries, return answer or stream.
    context_chunks: list of text passages (with optional citation metadata in the strings).
    Returns str (non-stream) or generator of content chunks (stream=True).
    """
    c = _get_llm_config()
    params = c.parameters
    base_url, model = _resolve_base_url_and_model(tier, use_playground)
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else "(No relevant passages found.)"
    messages = _build_messages(question, context)
    run_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()
    obs = LLMObservability(run_id=run_id, model=model, tier=tier or c.active_tier, sources_used=len(context_chunks), stream=stream)

    if not stream:
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                out = completion(
                    base_url=base_url,
                    model=model,
                    messages=messages,
                    temperature=params.temperature,
                    top_p=params.top_p,
                    max_tokens=params.max_tokens,
                    stream=False,
                )
                obs.latency_ms = (time.perf_counter() - t0) * 1000
                if isinstance(out, str):
                    obs.tokens_output = len(out.split()) * 2  # rough
                logger.info(
                    "llm_request run_id=%s model=%s tier=%s latency_ms=%.0f sources_used=%d",
                    obs.run_id, obs.model, obs.tier, obs.latency_ms, obs.sources_used,
                )
                return out if isinstance(out, str) else ""
            except Exception as e:
                last_err = e
                err_lower = str(e).lower()
                is_conn = "closed" in err_lower or "connection" in err_lower or "remotedisconnected" in err_lower or "499" in err_lower or "prematurely" in err_lower
                if is_conn and attempt < MAX_RETRIES:
                    logger.warning("llm_request attempt=%s connection error (model may be loading), waiting %ss before retry: %s", attempt + 1, RETRY_DELAY_IF_CONNECTION_ERROR, e)
                    time.sleep(RETRY_DELAY_IF_CONNECTION_ERROR)
                else:
                    logger.warning("llm_request attempt=%s error=%s", attempt + 1, e)
        logger.error("llm_request failed after %s attempts: %s", MAX_RETRIES + 1, last_err)
        return ""

    # Streaming: return generator that yields content deltas and logs at end
    def _stream_gen() -> Generator[str, None, None]:
        nonlocal obs
        try:
            stream_iter = completion(
                base_url=base_url,
                model=model,
                messages=messages,
                temperature=params.temperature,
                top_p=params.top_p,
                max_tokens=params.max_tokens,
                stream=True,
            )
            full = []
            for chunk in stream_iter:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = getattr(chunk.choices[0], "delta", None) or chunk.choices[0]
                    content = getattr(delta, "content", None) or ""
                    if content:
                        full.append(content)
                        yield content
            obs.latency_ms = (time.perf_counter() - t0) * 1000
            obs.tokens_output = len("".join(full).split()) * 2
            logger.info(
                "llm_request run_id=%s model=%s tier=%s latency_ms=%.0f sources_used=%d stream=true",
                obs.run_id, obs.model, obs.tier, obs.latency_ms, obs.sources_used,
            )
        except Exception as e:
            logger.exception("llm_request stream failed: %s", e)

    return _stream_gen()


def _chunk_text(c: Any) -> str:
    if isinstance(c, dict):
        return c.get("text", c.get("content", "")) or ""
    return getattr(c, "text", str(c))


def _chunk_to_source(c: Any) -> dict[str, Any]:
    if isinstance(c, dict):
        text = (c.get("text") or c.get("content") or "")[:500]
        return {"text": text, "document_uid": c.get("document_uid", ""), "title": c.get("title") or c.get("document_uid", "")}
    text = (getattr(c, "text", None) or str(c))[:500]
    return {"text": text, "document_uid": getattr(c, "document_uid", ""), "title": getattr(c, "title", None) or getattr(c, "document_uid", "")}


def chat_with_sources(
    question: str,
    context_chunks: list[Any],
    *,
    tier: str | None = None,
    use_playground: bool = False,
    stream: bool = False,
) -> tuple[str | Generator[str, None, None], list[dict[str, Any]]]:
    """
    RAG chat returning (answer or stream, sources). context_chunks can be dicts or objects with .text, .document_uid, .title.
    """
    texts = [_chunk_text(c) for c in context_chunks]
    result = chat(question, texts, tier=tier, use_playground=use_playground, stream=stream)
    sources = [_chunk_to_source(c) for c in context_chunks]
    return result, sources
