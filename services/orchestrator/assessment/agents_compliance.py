"""ComplianceAgent — one ComplianceItem per requirement, evidence-backed."""
from __future__ import annotations

import json
import re
from uuid import UUID

from .schemas import Citation, ComplianceItem


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


async def run_compliance(
    *,
    rfp_id: str,
    requirements: list[dict],
    tenant_id: str,
    retrieval_call,
    llm_client,
) -> list[ComplianceItem]:
    items: list[ComplianceItem] = []
    for req in requirements:
        try:
            chunks = await retrieval_call(
                question=req["text"],
                user_context={"tenant_id": tenant_id, "role": "system",
                              "user_id": "", "teams": []},
                top_n=5,
            )
        except Exception:
            chunks = []
        if not chunks:
            items.append(ComplianceItem(
                requirement_id=req.get("id"),
                category="other", label=req["text"][:200],
                mandatory=bool(req.get("mandatory", False)),
                status="unknown", evidence={}, citations=[]))
            continue

        ctx_block = "\n".join(
            f"[{i+1}] (cat={c.get('category','general')}) {c.get('text','')[:600]}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            "You are a bid-compliance reviewer. Given the requirement and the "
            "context blocks below, return JSON with keys: status (pass|fail|"
            "partial|unknown), category (security|privacy|operational|commercial|"
            "legal|other), mandatory (true|false), evidence_kind (snippet|"
            "past_proposal|product|service_line|certification|other), "
            "evidence_excerpt (first 200 chars of the cited block), "
            "citation_indexes (array of 1-based indexes used).\n\n"
            f"REQUIREMENT: {req['text']}\n\nCONTEXT:\n{ctx_block}\n\nJSON:"
        )
        decision: dict = {}
        if llm_client is not None:
            try:
                raw = await llm_client.generate(prompt, [])
                decision = _parse_json(getattr(raw, "text", "") or "")
            except Exception:
                decision = {}

        cit_idx = decision.get("citation_indexes") or []
        citations = []
        for i in cit_idx:
            if isinstance(i, int) and 1 <= i <= len(chunks):
                c = chunks[i - 1]
                try:
                    citations.append(Citation(
                        document_id=UUID(c["doc_id"]),
                        chunk_id=UUID(c["chunk_id"]),
                        position=int(c.get("position", 0)),
                        excerpt=(c.get("text") or "")[:200],
                    ))
                except Exception:
                    pass
        items.append(ComplianceItem(
            requirement_id=req.get("id"),
            category=decision.get("category") or "other",
            label=req["text"][:200],
            mandatory=bool(decision.get("mandatory", req.get("mandatory", False))),
            status=decision.get("status") or "unknown",
            evidence={"kind": decision.get("evidence_kind", "other"),
                       "excerpt": (decision.get("evidence_excerpt") or "")[:240]},
            citations=citations,
        ))
    return items
