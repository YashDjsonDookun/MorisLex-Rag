"""Pydantic models for LLM request/response and observability."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMObservability(BaseModel):
    """Logged fields for each LLM request (observability)."""

    run_id: str = ""
    model: str = ""
    tier: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    sources_used: int = 0
    stream: bool = False
