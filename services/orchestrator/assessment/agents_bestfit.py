"""BestFitAgent — closest matching service_line or product per requirement.

Primary path uses sentence-transformer embeddings for semantic similarity.
If sentence-transformers isn't installed in this container (the orchestrator
intentionally stays lean to avoid the ~1GB PyTorch dependency), we fall
back to a simple token-overlap heuristic. The fallback is noticeably less
accurate but keeps the pipeline producing a defensible match score so the
scorecard isn't empty.
"""
from __future__ import annotations

import math
import re
from uuid import UUID

import httpx

from .schemas import CapabilityMatch


_EMBEDDER = None  # lazy + can stay None when the dep isn't installed


def _maybe_embedder():
    global _EMBEDDER
    if _EMBEDDER is False:
        return None
    if _EMBEDDER is not None:
        return _EMBEDDER
    try:
        from common.embedder import SentenceTransformerEmbedder  # type: ignore
        e = SentenceTransformerEmbedder()
        # Smoke check that the model actually loads (catches missing
        # sentence-transformers without lazy crash inside agent)
        e.embed(["warmup"])
        _EMBEDDER = e
        return _EMBEDDER
    except Exception:
        _EMBEDDER = False  # cache the failure
        return None


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenset(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower())) - {
        "the", "and", "for", "with", "shall", "must", "should", "vendor",
        "system", "required", "to", "of", "a", "an", "in", "on", "by"
    }


def _overlap(req_text: str, offering_text: str) -> float:
    a, b = _tokenset(req_text), _tokenset(offering_text)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


async def run_bestfit(
    *,
    requirements: list[dict],
    tenant_id: str,
    capability_url: str,
) -> list[CapabilityMatch]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{capability_url}/capabilities/profile",
                headers={"X-Tenant-Id": tenant_id},
            )
            resp.raise_for_status()
            profile = resp.json()
    except Exception:
        profile = {"service_lines": [], "products": []}

    service_lines = profile.get("service_lines", [])
    products = profile.get("products", [])
    if not service_lines and not products:
        return []

    sl_texts = [f"{sl['name']}: {sl.get('description') or ''}" for sl in service_lines]
    prod_texts = [f"{p['name']}: {p.get('category') or ''}" for p in products]

    embedder = _maybe_embedder()
    if embedder is not None:
        sl_embs = embedder.embed(sl_texts) if sl_texts else []
        prod_embs = embedder.embed(prod_texts) if prod_texts else []

    out: list[CapabilityMatch] = []
    for req in requirements:
        try:
            rid = UUID(req["id"])
        except Exception:
            continue
        best_score = 0.0
        best_type: str = "service_line"
        best_id: str | None = None

        if embedder is not None:
            req_emb = embedder.embed([req["text"]])[0]
            for sl, emb in zip(service_lines, sl_embs):
                s = _cosine(req_emb, emb)
                if s > best_score:
                    best_score, best_type, best_id = s, "service_line", sl["id"]
            for p, emb in zip(products, prod_embs):
                s = _cosine(req_emb, emb)
                if s > best_score:
                    best_score, best_type, best_id = s, "product", p["id"]
        else:
            # Fallback: cheap token-overlap similarity.
            for sl, txt in zip(service_lines, sl_texts):
                s = _overlap(req["text"], txt)
                if s > best_score:
                    best_score, best_type, best_id = s, "service_line", sl["id"]
            for p, txt in zip(products, prod_texts):
                s = _overlap(req["text"], txt)
                if s > best_score:
                    best_score, best_type, best_id = s, "product", p["id"]

        gap = None
        if best_score < 0.4:
            gap = "No strong offering match; consider partnership or escalate."

        out.append(CapabilityMatch(
            requirement_id=rid,
            offering_type=best_type,  # type: ignore[arg-type]
            offering_id=UUID(best_id) if best_id else None,
            match_score=float(round(best_score, 4)),
            gap_notes=gap,
        ))
    return out
