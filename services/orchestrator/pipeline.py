from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.logging import get_logger

try:
    from prompts import build_system_prompt, build_user_prompt
except ImportError:
    from prompts import build_system_prompt, build_user_prompt  # type: ignore[no-redef]

logger = get_logger("orchestrator.pipeline")

# Ensure adapters package is importable.
# In Docker the adapters are copied to /app/adapters; locally they sit in services/adapters.
for _adapters_path in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters"),  # Docker
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "adapters"),  # local dev
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "adapters"),
]:
    if os.path.isdir(_adapters_path):
        sys.path.insert(0, os.path.abspath(_adapters_path))
        break


@dataclass
class Citation:
    chunk_id: str
    doc_id: str
    snippet: str


@dataclass
class AskResponse:
    answer: str
    citations: list[Citation]
    confidence: float = 0.0
    model: str = ""


async def call_retrieval_service(
    question: str,
    user_context: dict,
    filters: dict | None = None,
    score_adjustments: dict | None = None,
    top_n: int = 12,
) -> list[dict]:
    """Call the retrieval-service /retrieve endpoint."""
    settings = get_settings()
    retrieval_url = getattr(settings, "retrieval_service_url", "http://retrieval-service:8002")

    payload = {
        "query": question,
        "user_context": user_context,
        "filters": filters or {},
        "top_n": top_n,
        "score_adjustments": score_adjustments or {},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{retrieval_url}/retrieve", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("chunks", [])
    except Exception as exc:
        logger.error(f"Retrieval service error: {exc}")
        return []


def assemble_citations(chunks: list[dict]) -> list[Citation]:
    return [
        Citation(
            chunk_id=c["chunk_id"],
            doc_id=c["doc_id"],
            snippet=c["text"][:200],
        )
        for c in chunks
    ]


def compute_confidence(chunks: list[dict]) -> float:
    """Compute confidence as mean RRF score (normalized to 0-1)."""
    if not chunks:
        return 0.0
    scores = [float(c.get("score", 0)) for c in chunks]
    # RRF scores are small positive values; normalize by max possible ~1/60
    max_rrf = 1.0 / 60
    normalized = [min(s / max_rrf, 1.0) for s in scores]
    return sum(normalized) / len(normalized)


async def ask_pipeline(
    question: str,
    mode: str,
    detail_level: str,
    user_context: dict,
    db: AsyncSession,
    rfp_id: str | None = None,
    score_adjustments: dict | None = None,
) -> AskResponse:
    """Full ask pipeline: retrieve -> prompt -> generate -> citations -> audit."""
    # 1. Retrieve context
    chunks = await call_retrieval_service(
        question=question,
        user_context=user_context,
        score_adjustments=score_adjustments,
    )

    # 2. Check adaptive disclosure
    partial_compliance = False
    if len(chunks) < 2:
        partial_compliance = True
    else:
        mean_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
        # RRF score normalization: low score means low similarity
        if mean_score < (1.0 / 60) * 0.4:  # 40% of max_rrf
            partial_compliance = True

    # 3. Build prompt
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(question, chunks, mode=mode, detail_level=detail_level)

    if partial_compliance:
        user_prompt = (
            "NOTE: The following answer is based on partial information from the knowledge base. "
            "Some aspects may not be fully covered.\n\n" + user_prompt
        )

    # 4. Get model adapter
    settings = get_settings()
    provider = settings.default_tenant_model

    from base import AdapterError
    from claude import ClaudeAdapter
    from gemini import GeminiAdapter
    from ollama import OllamaAdapter
    from openai_adapter import OpenAIAdapter

    if provider == "claude" and settings.anthropic_api_key:
        adapter = ClaudeAdapter(api_key=settings.anthropic_api_key)
    elif provider == "gemini" and settings.google_api_key:
        adapter = GeminiAdapter(api_key=settings.google_api_key)
    elif provider in ("openai", "copilot") and settings.openai_api_key:
        adapter = OpenAIAdapter(api_key=settings.openai_api_key)
    elif provider in ("azure_openai", "copilot") and settings.azure_openai_api_key:
        adapter = OpenAIAdapter(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            deployment=settings.azure_openai_deployment,
        )
    else:
        adapter = OllamaAdapter(base_url=settings.ollama_base_url)

    # 5. Generate
    try:
        context_texts = [c["text"] for c in chunks]
        result = await adapter.generate(user_prompt, context_texts)
        answer_text = result.text
        model_name = result.model
    except AdapterError as exc:
        logger.error(f"Model generation failed: {exc}")
        answer_text = "Unable to generate a response at this time. Please try again."
        model_name = "error"

    # 6. Assemble citations and confidence
    citations = assemble_citations(chunks)
    confidence = compute_confidence(chunks)

    return AskResponse(
        answer=answer_text,
        citations=citations,
        confidence=confidence,
        model=model_name,
    )
