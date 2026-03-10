"""Thin OpenAI-compatible client for Ollama (or LM Studio). No prompt logic."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def completion(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    top_p: float = 0.9,
    max_tokens: int = 2048,
    stream: bool = False,
) -> str | Any:
    """
    Call Ollama/LM Studio OpenAI-compatible API. Returns content string (non-stream) or stream iterator.
    """
    try:
        from openai import OpenAI
        import httpx
    except ImportError:
        logger.warning("openai package not installed")
        return ""

    # Ollama serves OpenAI-compatible API at /v1/chat/completions; LM Studio often same. Ensure /v1.
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    # Explicit long read timeout so first request (model load on CPU, 1–3 min) does not get "client connection closed".
    # Scalar timeout can be applied only to connect in some versions; use httpx.Timeout to force read=600.
    timeout = httpx.Timeout(600.0, connect=60.0)
    client = OpenAI(base_url=url, api_key="ollama", timeout=timeout)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if top_p is not None and 0 < top_p <= 1:
        kwargs["top_p"] = top_p

    try:
        if not stream:
            resp = client.chat.completions.create(**kwargs)
            if resp.choices:
                return (resp.choices[0].message.content or "").strip()
            return ""
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        # Log response body for 500/502 so we can see Ollama's error (e.g. model not loaded, OOM)
        err_str = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.text if hasattr(e.response, "text") else getattr(e.response, "content", b"")
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                if body:
                    logger.error("Ollama response %s: %s", getattr(e.response, "status_code", ""), body[:500])
            except Exception:
                pass
        logger.error("Ollama request failed: %s", err_str)
        raise
