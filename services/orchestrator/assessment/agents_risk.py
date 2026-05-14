"""RiskAgent — consumes upstream agent outputs and enumerates risks."""
from __future__ import annotations

import json
import re

from .schemas import Risk


def _parse_array(text: str) -> list:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


async def run_risks(
    *,
    raw_text: str,
    requirements: list[dict],
    compliance: list,
    eligibility: list,
    best_fit: list,
    llm_client,
) -> list[Risk]:
    failed = [c for c in compliance if getattr(c, "status", None) == "fail"]
    elig_fail = [e for e in eligibility if getattr(e, "status", None) == "fail"]
    gaps = [m for m in best_fit if getattr(m, "match_score", 1.0) < 0.5]

    summary = (
        f"Compliance failures: {len(failed)}; eligibility failures: {len(elig_fail)}; "
        f"capability gaps: {len(gaps)}."
    )
    prompt = (
        "You are a bid risk analyst. Given the RFP excerpt and the assessment "
        "summary below, return a JSON array of risks. Each item has: category "
        "(commercial|delivery|legal|technical|reputational), title, description, "
        "severity (low|medium|high), likelihood (low|medium|high), mitigation.\n\n"
        f"SUMMARY: {summary}\n\nRFP EXCERPT:\n{raw_text[:4000]}\n\nJSON_ARRAY:"
    )
    if llm_client is None:
        return []
    try:
        raw = await llm_client.generate(prompt, [])
        items = _parse_array(getattr(raw, "text", "") or "")
    except Exception:
        items = []
    out: list[Risk] = []
    for r in items:
        try:
            out.append(Risk(
                category=r.get("category") or "delivery",
                title=(r.get("title") or "")[:200],
                description=(r.get("description") or "")[:2000],
                severity=r.get("severity") or "low",
                likelihood=r.get("likelihood") or "low",
                mitigation=r.get("mitigation"),
                citations=[],
            ))
        except Exception:
            continue
    return out
