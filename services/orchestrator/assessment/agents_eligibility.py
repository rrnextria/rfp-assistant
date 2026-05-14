"""EligibilityAgent — bid-killers (geography, contract vehicle, certs, financial)."""
from __future__ import annotations

import json
import re

import httpx

from .schemas import EligibilityCheck


def _parse_array(text: str) -> list:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


async def run_eligibility(
    *,
    rfp_id: str,
    raw_text: str,
    tenant_id: str,
    capability_url: str,
    llm_client,
) -> list[EligibilityCheck]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{capability_url}/capabilities/profile",
                headers={"X-Tenant-Id": tenant_id},
            )
            resp.raise_for_status()
            profile = resp.json()
    except Exception:
        profile = {"geographies": [], "certifications": []}

    geo_names = [g["name"] for g in profile.get("geographies", [])]
    cert_names = [c["name"] for c in profile.get("certifications", [])]

    prompt = (
        "You are a bid-eligibility analyst. Given the RFP text and our company "
        "profile, return a JSON array of eligibility checks. Each check has: "
        "label, kind (geography|contract_vehicle|certification|financial|"
        "exclusion|other), expected (what the RFP requires), actual (what we "
        "have), status (pass|fail|partial|unknown).\n\n"
        f"OUR GEOGRAPHIES: {', '.join(geo_names) or '(none)'}\n"
        f"OUR CERTIFICATIONS: {', '.join(cert_names) or '(none)'}\n\n"
        f"RFP TEXT (truncated):\n{raw_text[:6000]}\n\nJSON_ARRAY:"
    )
    if llm_client is None:
        return []
    try:
        raw = await llm_client.generate(prompt, [])
        items = _parse_array(getattr(raw, "text", "") or "")
    except Exception:
        items = []
    out: list[EligibilityCheck] = []
    for c in items:
        try:
            out.append(EligibilityCheck(
                label=(c.get("label") or "")[:200],
                kind=c.get("kind") or "other",
                expected=(c.get("expected") or "")[:500],
                actual=(c.get("actual") or "")[:500],
                status=c.get("status") or "unknown",
                citations=[],
            ))
        except Exception:
            continue
    return out
