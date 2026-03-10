"""Strict legal RAG prompts: answer only from context; no hallucination; no internet."""

from __future__ import annotations

# System prompt: legal research assistant, context-only, cite sources, say "I do not know" when unsure.
RAG_SYSTEM_PROMPT = """You are a legal research assistant for Mauritius law.

Rules:
- Answer only using the provided context below. Do not use external knowledge.
- Cite sources when possible (refer to the document or section from the context).
- If the context does not contain enough information to answer, say "I do not know" or "The provided documents do not contain this information."
- Do not attempt to access the internet or add information from outside the provided context.
- Keep answers concise and grounded in the context."""

# Guardrail appended to user message so the model stays within context.
RAG_USER_GUARDRAIL = "\n\nUse only the context above. Do not add information from outside this context."


def build_rag_user_content(question: str, context: str, with_guardrail: bool = True) -> str:
    """Build user message: context + question + optional guardrail."""
    parts = [f"Context:\n{context}", f"Question: {question}"]
    if with_guardrail:
        parts.append(RAG_USER_GUARDRAIL)
    return "\n\n".join(parts)


def get_system_prompt() -> str:
    """Return the strict legal RAG system prompt."""
    return RAG_SYSTEM_PROMPT
