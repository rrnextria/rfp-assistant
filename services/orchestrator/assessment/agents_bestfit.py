"""BestFitAgent — closest matching service_line or product per requirement."""
from __future__ import annotations

import math
from uuid import UUID

import httpx

from common.embedder import SentenceTransformerEmbedder
from .schemas import CapabilityMatch

_embedder = SentenceTransformerEmbedder()


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


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

    sl_texts = [f"{sl['name']}: {sl.get('description') or ''}" for sl in service_lines]
    prod_texts = [f"{p['name']}: {p.get('category') or ''}" for p in products]
    sl_embs = _embedder.embed(sl_texts) if sl_texts else []
    prod_embs = _embedder.embed(prod_texts) if prod_texts else []

    out: list[CapabilityMatch] = []
    for req in requirements:
        req_emb = _embedder.embed([req["text"]])[0]
        best_score = 0.0
        best_type = "service_line"
        best_id: str | None = None
        for sl, emb in zip(service_lines, sl_embs):
            s = _cosine(req_emb, emb)
            if s > best_score:
                best_score, best_type, best_id = s, "service_line", sl["id"]
        for p, emb in zip(products, prod_embs):
            s = _cosine(req_emb, emb)
            if s > best_score:
                best_score, best_type, best_id = s, "product", p["id"]
        gap = None
        if best_score < 0.5:
            gap = "No offering above similarity 0.5; consider partnership or escalate."
        try:
            rid = UUID(req["id"])
        except Exception:
            continue
        out.append(CapabilityMatch(
            requirement_id=rid,
            offering_type=best_type,  # type: ignore[arg-type]
            offering_id=UUID(best_id) if best_id else None,
            match_score=float(round(best_score, 4)),
            gap_notes=gap,
        ))
    return out
