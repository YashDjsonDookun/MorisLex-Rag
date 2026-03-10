"""Ollama / LM Studio client — delegates to LLMService. Backward-compatible chat() and build_rag_prompt."""

from __future__ import annotations

from app.core.config import get_config
from app.llm.prompts import build_rag_user_content, get_system_prompt
from app.llm.service import chat_with_sources


def build_rag_prompt(question: str, context_chunks: list[str], system_hint: str = "") -> list[dict]:
    """Build messages for RAG: system + user with context and question. Prefer LLMService in new code."""
    context = "\n\n---\n\n".join(context_chunks) if context_chunks else "(No relevant passages found.)"
    system = system_hint or get_system_prompt()
    user = build_rag_user_content(question, context, with_guardrail=True)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def chat(
    question: str,
    top_k: int | None = None,
    *,
    tier: str | None = None,
    use_playground: bool = False,
) -> tuple[str, list[dict]]:
    """
    RAG chat: retrieve top-k chunks, call LLMService, return (answer, sources).
    sources = list of {"text", "document_uid", "title"} for citation.
    """
    from app.core.retriever import retrieve

    config = get_config()
    k = top_k if top_k is not None else config.retrieval.top_k
    chunks = retrieve(question.strip(), top_k=k)
    answer_or_stream, sources = chat_with_sources(
        question.strip(),
        chunks,
        tier=tier,
        use_playground=use_playground,
        stream=False,
    )
    answer = answer_or_stream if isinstance(answer_or_stream, str) else "".join(answer_or_stream)
    return answer, sources


def chat_completion(
    messages: list[dict],
    *,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Legacy: call LLM with raw messages (OpenAI-compatible). Prefer chat() / LLMService for RAG.
    """
    from app.llm.client_ollama import completion

    config = get_config()
    llm = config.llm
    base_url = base_url or llm.base_url
    model = model or llm.active_model
    params = llm.parameters
    temperature = temperature if temperature is not None else params.temperature
    max_tokens = max_tokens if max_tokens is not None else params.max_tokens
    out = completion(
        base_url=base_url,
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=params.top_p,
        max_tokens=max_tokens,
        stream=False,
    )
    return (out or "").strip() if isinstance(out, str) else ""
