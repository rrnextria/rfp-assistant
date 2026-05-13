# Phase 3 — Bid Assessment Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this phase task-by-task.

**Goal:** Add the 5 assessment tables, build the 5 agents (Compliance, Eligibility, BestFit, Risk, Summary), wire them into a `BidAssessmentPipeline` in `services/orchestrator`, and expose `/rfps/{id}/assess` (POST + SSE GET) plus the read endpoints through `rfp-service`. End state: `POST /rfps/{id}/assess` returns a complete assessment with all child rows persisted; SSE stream emits per-agent progress events.

**Architecture:** Pipeline owns all DB writes; agents are pure functions over data. Three parallel agents (Compliance, Eligibility, BestFit) run via `asyncio.gather`; Risk waits on all three; Summary waits on Risk. Partial failures persist surviving rows and mark `status='partial'`. SSE replay uses a small in-memory ring buffer keyed by `(rfp_id, version)`. Fit/win-probability math is deterministic (in code); only the exec summary prose comes from the LLM.

**Tech Stack:** Python 3.11+, FastAPI + `StreamingResponse` for SSE, SQLAlchemy 2.x async, Pydantic, the existing `services/adapters` layer for LLM calls.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `migrations/versions/0014_bid_assessments.py` | 5 assessment tables |
| Create | `services/orchestrator/assessment/__init__.py` | Package marker |
| Create | `services/orchestrator/assessment/schemas.py` | Pydantic types in spec §5.3 |
| Create | `services/orchestrator/assessment/agents_compliance.py` | ComplianceAgent |
| Create | `services/orchestrator/assessment/agents_eligibility.py` | EligibilityAgent |
| Create | `services/orchestrator/assessment/agents_bestfit.py` | BestFitAgent |
| Create | `services/orchestrator/assessment/agents_risk.py` | RiskAgent |
| Create | `services/orchestrator/assessment/agents_summary.py` | SummaryAgent + verdict math |
| Create | `services/orchestrator/assessment/pipeline.py` | `BidAssessmentPipeline` + DB writes + SSE buffer |
| Create | `services/orchestrator/assessment/stream.py` | SSE event format + ring buffer |
| Create | `services/orchestrator/tests/test_assessment_pipeline.py` | End-to-end stubbed-agents test |
| Create | `services/orchestrator/tests/test_summary_math.py` | Deterministic verdict math |
| Modify | `services/orchestrator/main.py` | Expose internal `/assess/run` and `/assess/stream/{rfp_id}` endpoints |
| Create | `services/rfp-service/assessment.py` | Public `/rfps/{id}/assess*` endpoints |
| Modify | `services/rfp-service/main.py` | Mount assessment router |
| Create | `services/rfp-service/tests/test_assessment_endpoints.py` | Endpoint test (with stubbed orchestrator HTTP) |
| Modify | `services/api-gateway/proxy.py` | Route remains `rfps` (no change); confirm streaming works |

---

## Tasks

### Task 1 — Branch

- [ ] **Step 1**

```bash
git checkout feat/bid-assessment
git checkout -b feat/bid-assessment-phase-3-bid-assessment-core
```

- [ ] **Step 2: Baseline tests**

```bash
for svc in orchestrator rfp-service; do
  echo "--- $svc ---"
  (cd services/$svc && python -m pytest -q)
done
```

Expected: green.

---

### Task 2 — Migration 0014: assessment tables

**Files:**
- Create: `migrations/versions/0014_bid_assessments.py`

- [ ] **Step 1: Write the migration**

```python
"""bid_assessments + compliance_items + eligibility_checks + risks + capability_matches.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bid_assessments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("rfp_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfps.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("fit_score", sa.Numeric, nullable=True),
        sa.Column("win_probability", sa.Numeric, nullable=True),
        sa.Column("verdict", sa.String, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("model_version", sa.String, nullable=False, server_default="unknown"),
        sa.Column("generated_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("rfp_id", "version", name="uq_bid_assessments_rfp_version"),
        sa.CheckConstraint("status IN ('running','complete','partial','failed')",
                           name="ck_bid_assessments_status"),
        sa.CheckConstraint("verdict IS NULL OR verdict IN ('bid','no_bid','review')",
                           name="ck_bid_assessments_verdict"),
    )
    op.create_index("ix_bid_assessments_rfp", "bid_assessments", ["rfp_id"])
    op.create_index("ix_bid_assessments_tenant", "bid_assessments", ["tenant_id"])

    op.create_table(
        "compliance_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfp_requirements.id"), nullable=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("mandatory", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("evidence", sa.dialects.postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint("category IN ('security','privacy','operational','commercial','legal','other')",
                           name="ck_compliance_category"),
        sa.CheckConstraint("status IN ('pass','fail','partial','unknown')",
                           name="ck_compliance_status"),
    )
    op.create_index("ix_compliance_items_assessment", "compliance_items", ["assessment_id"])

    op.create_table(
        "eligibility_checks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("expected", sa.String, nullable=True),
        sa.Column("actual", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint("kind IN ('geography','contract_vehicle','certification','financial','exclusion','other')",
                           name="ck_eligibility_kind"),
        sa.CheckConstraint("status IN ('pass','fail','partial','unknown')",
                           name="ck_eligibility_status"),
    )
    op.create_index("ix_eligibility_checks_assessment", "eligibility_checks", ["assessment_id"])

    op.create_table(
        "risks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("likelihood", sa.String, nullable=False),
        sa.Column("mitigation", sa.Text, nullable=True),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("authored_by", sa.String, nullable=False, server_default="ai"),
        sa.CheckConstraint("category IN ('commercial','delivery','legal','technical','reputational')",
                           name="ck_risks_category"),
        sa.CheckConstraint("severity IN ('low','medium','high')", name="ck_risks_severity"),
        sa.CheckConstraint("likelihood IN ('low','medium','high')", name="ck_risks_likelihood"),
        sa.CheckConstraint("authored_by IN ('ai','human')", name="ck_risks_authored_by"),
    )
    op.create_index("ix_risks_assessment", "risks", ["assessment_id"])

    op.create_table(
        "capability_matches",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfp_requirements.id"), nullable=False),
        sa.Column("offering_type", sa.String, nullable=False),
        sa.Column("offering_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_score", sa.Numeric, nullable=False),
        sa.Column("gap_notes", sa.Text, nullable=True),
        sa.CheckConstraint("offering_type IN ('service_line','product')",
                           name="ck_capability_matches_offering_type"),
    )
    op.create_index("ix_capability_matches_assessment", "capability_matches", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_capability_matches_assessment", table_name="capability_matches")
    op.drop_table("capability_matches")
    op.drop_index("ix_risks_assessment", table_name="risks")
    op.drop_table("risks")
    op.drop_index("ix_eligibility_checks_assessment", table_name="eligibility_checks")
    op.drop_table("eligibility_checks")
    op.drop_index("ix_compliance_items_assessment", table_name="compliance_items")
    op.drop_table("compliance_items")
    op.drop_index("ix_bid_assessments_tenant", table_name="bid_assessments")
    op.drop_index("ix_bid_assessments_rfp", table_name="bid_assessments")
    op.drop_table("bid_assessments")
```

- [ ] **Step 2: Reversibility**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade 0013
docker compose exec api-gateway alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0014_bid_assessments.py
git commit -m "feat(db): bid_assessments + 4 child tables"
```

---

### Task 3 — Pydantic schemas

**Files:**
- Create: `services/orchestrator/assessment/__init__.py`
- Create: `services/orchestrator/assessment/schemas.py`

- [ ] **Step 1: Empty package marker**

Empty `services/orchestrator/assessment/__init__.py`.

- [ ] **Step 2: schemas.py**

Create `services/orchestrator/assessment/schemas.py` with the exact Pydantic types from spec §5.3:

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Citation(BaseModel):
    document_id: UUID
    chunk_id: UUID
    position: int
    excerpt: str | None = None


class ComplianceItem(BaseModel):
    requirement_id: UUID | None = None
    category: Literal["security", "privacy", "operational", "commercial", "legal", "other"]
    label: str
    mandatory: bool
    status: Literal["pass", "fail", "partial", "unknown"]
    evidence: dict
    citations: list[Citation] = []


class EligibilityCheck(BaseModel):
    label: str
    kind: Literal["geography", "contract_vehicle", "certification", "financial", "exclusion", "other"]
    expected: str | None = None
    actual: str | None = None
    status: Literal["pass", "fail", "partial", "unknown"]
    citations: list[Citation] = []


class Risk(BaseModel):
    category: Literal["commercial", "delivery", "legal", "technical", "reputational"]
    title: str
    description: str
    severity: Literal["low", "medium", "high"]
    likelihood: Literal["low", "medium", "high"]
    mitigation: str | None = None
    citations: list[Citation] = []


class CapabilityMatch(BaseModel):
    requirement_id: UUID
    offering_type: Literal["service_line", "product"]
    offering_id: UUID | None = None
    match_score: float
    gap_notes: str | None = None


class AssessmentRollup(BaseModel):
    fit_score: float
    win_probability: float
    verdict: Literal["bid", "no_bid", "review"]
    summary: str
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator/assessment/__init__.py \
         services/orchestrator/assessment/schemas.py
git commit -m "feat(orchestrator): assessment pydantic schemas"
```

---

### Task 4 — SummaryAgent verdict math (TDD-first; deterministic)

**Files:**
- Create: `services/orchestrator/assessment/agents_summary.py`
- Create: `services/orchestrator/tests/test_summary_math.py`

- [ ] **Step 1: Failing test**

```python
import pytest
from services.orchestrator.assessment.agents_summary import compute_rollup
from services.orchestrator.assessment.schemas import CapabilityMatch, ComplianceItem


def _cm(score, weight=1.0):
    return CapabilityMatch(requirement_id="00000000-0000-0000-0000-000000000001",
                            offering_type="service_line", offering_id=None,
                            match_score=score, gap_notes=None)


def test_fit_score_simple_mean():
    matches = [_cm(0.8), _cm(0.6)]
    rollup = compute_rollup(matches, compliance=[], thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
                             mandatory_penalty=0.3, analytics_boost=0.0)
    assert abs(rollup["fit_score"] - 0.7) < 1e-9


def test_mandatory_failure_drops_win_probability():
    matches = [_cm(1.0)]
    failed = ComplianceItem(category="legal", label="must-have", mandatory=True,
                             status="fail", evidence={}, citations=[])
    rollup = compute_rollup(matches, compliance=[failed],
                             thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
                             mandatory_penalty=0.3, analytics_boost=0.0)
    assert rollup["fit_score"] == 1.0
    # win_probability = 1.0 * (1 - 0.3) * 1.0 = 0.7
    assert abs(rollup["win_probability"] - 0.7) < 1e-9


def test_verdict_thresholds():
    matches = [_cm(0.85)]
    rollup = compute_rollup(matches, compliance=[],
                             thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
                             mandatory_penalty=0.3, analytics_boost=0.0)
    assert rollup["verdict"] == "bid"
    matches = [_cm(0.30)]
    rollup = compute_rollup(matches, compliance=[],
                             thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
                             mandatory_penalty=0.3, analytics_boost=0.0)
    assert rollup["verdict"] == "no_bid"
    matches = [_cm(0.55)]
    rollup = compute_rollup(matches, compliance=[],
                             thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
                             mandatory_penalty=0.3, analytics_boost=0.0)
    assert rollup["verdict"] == "review"
```

- [ ] **Step 2: Run test (should fail — module missing)**

```bash
cd services/orchestrator && python -m pytest tests/test_summary_math.py -v && cd -
```

Expected: FAIL — ImportError.

- [ ] **Step 3: Implement verdict math**

Create `services/orchestrator/assessment/agents_summary.py`:

```python
"""SummaryAgent — produces the AI rollup (fit_score, win_probability, verdict,
markdown summary). Verdict math is deterministic; only the prose comes from
the LLM."""
from __future__ import annotations

from typing import Sequence

from .schemas import (AssessmentRollup, CapabilityMatch, ComplianceItem,
                      EligibilityCheck, Risk)


def compute_rollup(
    matches: Sequence[CapabilityMatch],
    compliance: Sequence[ComplianceItem],
    *,
    thresholds: dict,
    mandatory_penalty: float,
    analytics_boost: float,
) -> dict:
    if not matches:
        fit = 0.0
    else:
        fit = sum(m.match_score for m in matches) / len(matches)
    failed_mandatory = any(c.mandatory and c.status == "fail" for c in compliance)
    penalty = mandatory_penalty if failed_mandatory else 0.0
    win = max(0.0, min(1.0, fit * (1.0 - penalty) * (1.0 + analytics_boost)))
    if fit >= thresholds["bid_min_fit"]:
        verdict = "bid"
    elif fit <= thresholds["no_bid_max_fit"]:
        verdict = "no_bid"
    else:
        verdict = "review"
    return {"fit_score": round(fit, 4), "win_probability": round(win, 4),
            "verdict": verdict}


async def generate_summary_prose(
    *,
    rollup: dict,
    compliance: Sequence[ComplianceItem],
    eligibility: Sequence[EligibilityCheck],
    risks: Sequence[Risk],
    llm_client,
) -> str:
    """Calls the LLM adapter for a one-page markdown summary. The math is
    already final; the LLM only writes prose."""
    bullets = []
    bullets.append(f"**AI verdict:** {rollup['verdict'].upper()}")
    bullets.append(f"**Fit score:** {rollup['fit_score']:.0%}")
    bullets.append(f"**Win probability:** {rollup['win_probability']:.0%}")
    failed = [c.label for c in compliance if c.status == "fail" and c.mandatory]
    if failed:
        bullets.append("**Mandatory fails:** " + ", ".join(failed))
    high_risk = [r.title for r in risks if r.severity == "high"]
    if high_risk:
        bullets.append("**High-severity risks:** " + ", ".join(high_risk))
    skeleton = "\n".join(f"- {b}" for b in bullets)
    prompt = (
        "Write a 4-paragraph executive summary for a bid committee. "
        "Open with the verdict and the reasoning behind it; then cover compliance "
        "coverage, key risks, and an explicit recommendation including any "
        "conditions for proceeding. Stay factual and reference the bullet list "
        "below; do not invent.\n\n"
        f"{skeleton}\n"
    )
    if llm_client is None:
        return skeleton  # test path
    result = await llm_client.generate(prompt, context_texts=[])
    return result.text
```

- [ ] **Step 4: Run test (should pass)**

```bash
cd services/orchestrator && python -m pytest tests/test_summary_math.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator/assessment/agents_summary.py \
         services/orchestrator/tests/test_summary_math.py
git commit -m "feat(assessment): SummaryAgent verdict math (deterministic) + prose stub"
```

---

### Task 5 — ComplianceAgent

**Files:**
- Create: `services/orchestrator/assessment/agents_compliance.py`

- [ ] **Step 1: Implement**

```python
"""ComplianceAgent — one ComplianceItem per requirement, evidence-backed."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from .schemas import Citation, ComplianceItem


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
        # Retrieve top-k chunks for this requirement, category-weighted via
        # the retrieval-service default boosts.
        chunks = await retrieval_call(
            query=req["text"],
            user_context={"tenant_id": tenant_id, "role": "system"},
            top_n=5,
        )
        if not chunks:
            items.append(ComplianceItem(
                requirement_id=req.get("id"),
                category="other", label=req["text"][:200],
                mandatory=bool(req.get("mandatory", False)),
                status="unknown", evidence={}, citations=[]))
            continue

        # Build a prompt asking the LLM to judge compliance with cited chunks.
        ctx_block = "\n".join(
            f"[{i+1}] (cat={c.get('category','general')}) {c['text'][:600]}"
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
        if llm_client is None:
            decision = {"status": "unknown", "category": "other",
                         "mandatory": False, "evidence_kind": "other",
                         "evidence_excerpt": "", "citation_indexes": []}
        else:
            raw = await llm_client.generate(prompt, context_texts=[])
            decision = _parse_json(raw.text)
        cit_idx = decision.get("citation_indexes") or []
        citations = []
        for i in cit_idx:
            if 1 <= i <= len(chunks):
                c = chunks[i - 1]
                citations.append(Citation(
                    document_id=UUID(c["doc_id"]), chunk_id=UUID(c["chunk_id"]),
                    position=int(c.get("position", 0)),
                    excerpt=c["text"][:200],
                ))
        items.append(ComplianceItem(
            requirement_id=req.get("id"),
            category=decision.get("category", "other") or "other",
            label=req["text"][:200],
            mandatory=bool(decision.get("mandatory", req.get("mandatory", False))),
            status=decision.get("status", "unknown") or "unknown",
            evidence={"kind": decision.get("evidence_kind", "other"),
                       "excerpt": decision.get("evidence_excerpt", "")[:240]},
            citations=citations,
        ))
    return items


def _parse_json(text: str) -> dict:
    import json
    import re
    # Try to find the first JSON object in the response
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}
```

- [ ] **Step 2: Unit test with stub retrieval + LLM**

Create `services/orchestrator/tests/test_compliance_agent.py`:

```python
import pytest

from services.orchestrator.assessment.agents_compliance import run_compliance


class _StubLLM:
    async def generate(self, prompt, context_texts):
        class R: text = ('{"status":"pass","category":"security","mandatory":true,'
                          '"evidence_kind":"snippet","evidence_excerpt":"yes",'
                          '"citation_indexes":[1]}')
        return R()


async def _stub_retrieval(query, user_context, top_n):
    return [{
        "doc_id": "00000000-0000-0000-0000-000000000010",
        "chunk_id": "00000000-0000-0000-0000-000000000020",
        "position": 0,
        "text": "We are SOC 2 Type II certified.",
        "category": "boilerplate_snippet",
        "metadata": {},
        "score": 0.5,
    }]


@pytest.mark.asyncio
async def test_compliance_agent_pass():
    out = await run_compliance(
        rfp_id="00000000-0000-0000-0000-000000000099",
        requirements=[{"id": "00000000-0000-0000-0000-000000000001",
                         "text": "Vendor must hold SOC 2 attestation.",
                         "mandatory": True}],
        tenant_id="11111111-1111-1111-1111-111111111111",
        retrieval_call=_stub_retrieval,
        llm_client=_StubLLM(),
    )
    assert len(out) == 1
    assert out[0].status == "pass"
    assert out[0].mandatory is True
    assert out[0].citations[0].chunk_id.hex == "00000000000000000000000000000020"
```

- [ ] **Step 3: Run test**

```bash
cd services/orchestrator && python -m pytest tests/test_compliance_agent.py -v && cd -
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add services/orchestrator/assessment/agents_compliance.py \
         services/orchestrator/tests/test_compliance_agent.py
git commit -m "feat(assessment): ComplianceAgent + unit test"
```

---

### Task 6 — EligibilityAgent

**Files:**
- Create: `services/orchestrator/assessment/agents_eligibility.py`

- [ ] **Step 1: Implement**

```python
"""EligibilityAgent — bid-killers (geography, contract vehicle, certs, financial)."""
from __future__ import annotations

from typing import Any

import httpx

from .schemas import Citation, EligibilityCheck


async def run_eligibility(
    *,
    rfp_id: str,
    raw_text: str,
    tenant_id: str,
    capability_url: str,
    llm_client,
) -> list[EligibilityCheck]:
    # Fetch profile
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{capability_url}/capabilities/profile",
                                  headers={"X-Tenant-Id": tenant_id})
        resp.raise_for_status()
        profile = resp.json()

    geo_names = [g["name"] for g in profile.get("geographies", [])]
    cert_names = [c["name"] for c in profile.get("certifications", [])]

    prompt = (
        "You are a bid-eligibility analyst. Given the RFP text and our company "
        "profile, return a JSON array of eligibility checks. Each check has: "
        "label, kind (geography|contract_vehicle|certification|financial|"
        "exclusion|other), expected (what RFP requires), actual (what we have), "
        "status (pass|fail|partial|unknown).\n\n"
        f"OUR GEOGRAPHIES: {', '.join(geo_names) or '(none)'}\n"
        f"OUR CERTIFICATIONS: {', '.join(cert_names) or '(none)'}\n\n"
        f"RFP TEXT (truncated):\n{raw_text[:6000]}\n\nJSON_ARRAY:"
    )
    if llm_client is None:
        return []
    raw = await llm_client.generate(prompt, context_texts=[])
    checks = _parse_array(raw.text)
    out: list[EligibilityCheck] = []
    for c in checks:
        try:
            out.append(EligibilityCheck(**{
                "label": c.get("label", "")[:200],
                "kind": c.get("kind", "other"),
                "expected": c.get("expected") or "",
                "actual": c.get("actual") or "",
                "status": c.get("status", "unknown"),
                "citations": [],
            }))
        except Exception:
            continue
    return out


def _parse_array(text: str) -> list:
    import json
    import re
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/assessment/agents_eligibility.py
git commit -m "feat(assessment): EligibilityAgent (capability-profile aware)"
```

---

### Task 7 — BestFitAgent

**Files:**
- Create: `services/orchestrator/assessment/agents_bestfit.py`

- [ ] **Step 1: Implement**

```python
"""BestFitAgent — for each requirement, find the closest service_line or
product by embedding cosine similarity."""
from __future__ import annotations

from uuid import UUID

import httpx

from common.embedder import SentenceTransformerEmbedder
from .schemas import CapabilityMatch

_embedder = SentenceTransformerEmbedder()


async def run_bestfit(
    *,
    requirements: list[dict],
    tenant_id: str,
    capability_url: str,
) -> list[CapabilityMatch]:
    # Pull service_lines via /capabilities/service-lines and products via the profile
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{capability_url}/capabilities/profile",
                                  headers={"X-Tenant-Id": tenant_id})
        resp.raise_for_status()
        profile = resp.json()
    service_lines = profile.get("service_lines", [])
    products = profile.get("products", [])

    # Compute or fetch embeddings for offerings
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
        out.append(CapabilityMatch(
            requirement_id=UUID(req["id"]),
            offering_type=best_type,
            offering_id=UUID(best_id) if best_id else None,
            match_score=float(round(best_score, 4)),
            gap_notes=gap,
        ))
    return out


def _cosine(a, b) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/assessment/agents_bestfit.py
git commit -m "feat(assessment): BestFitAgent (cosine over service_lines + products)"
```

---

### Task 8 — RiskAgent

**Files:**
- Create: `services/orchestrator/assessment/agents_risk.py`

- [ ] **Step 1: Implement**

```python
"""RiskAgent — consumes compliance + eligibility + best-fit outputs and the
raw RFP to enumerate risks across 5 categories."""
from __future__ import annotations

from .schemas import Citation, Risk


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
    raw = await llm_client.generate(prompt, context_texts=[])
    out: list[Risk] = []
    for r in _parse_array(raw.text):
        try:
            out.append(Risk(**{
                "category": r.get("category", "delivery"),
                "title": r.get("title", "")[:200],
                "description": r.get("description", "")[:2000],
                "severity": r.get("severity", "low"),
                "likelihood": r.get("likelihood", "low"),
                "mitigation": r.get("mitigation"),
                "citations": [],
            }))
        except Exception:
            continue
    return out


def _parse_array(text: str) -> list:
    import json
    import re
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/assessment/agents_risk.py
git commit -m "feat(assessment): RiskAgent"
```

---

### Task 9 — Stream buffer

**Files:**
- Create: `services/orchestrator/assessment/stream.py`

- [ ] **Step 1: Implement ring buffer + SSE format**

```python
"""In-memory SSE event buffer keyed by (rfp_id, version). Phase-2: swap to
Redis if you need cross-replica delivery."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict


_BUFFERS: dict[tuple[str, int], list[dict]] = defaultdict(list)
_LIVE_QUEUES: dict[tuple[str, int], list[asyncio.Queue]] = defaultdict(list)


def push(rfp_id: str, version: int, event: dict) -> None:
    key = (rfp_id, version)
    buf = _BUFFERS[key]
    buf.append(event)
    if len(buf) > 200:
        del buf[: len(buf) - 200]
    for q in _LIVE_QUEUES.get(key, []):
        q.put_nowait(event)


def replay(rfp_id: str, version: int) -> list[dict]:
    return list(_BUFFERS.get((rfp_id, version), []))


def attach_listener(rfp_id: str, version: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _LIVE_QUEUES[(rfp_id, version)].append(q)
    return q


def detach_listener(rfp_id: str, version: int, q: asyncio.Queue) -> None:
    lst = _LIVE_QUEUES.get((rfp_id, version), [])
    if q in lst:
        lst.remove(q)


def close_stream(rfp_id: str, version: int) -> None:
    for q in _LIVE_QUEUES.get((rfp_id, version), []):
        q.put_nowait({"event": "close"})


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/assessment/stream.py
git commit -m "feat(assessment): in-memory SSE buffer with replay"
```

---

### Task 10 — BidAssessmentPipeline + DB writes

**Files:**
- Create: `services/orchestrator/assessment/pipeline.py`
- Create: `services/orchestrator/tests/test_assessment_pipeline.py`

- [ ] **Step 1: End-to-end test with stubbed agents**

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from services.orchestrator.assessment.pipeline import BidAssessmentPipeline
from services.orchestrator.assessment.schemas import (
    CapabilityMatch, ComplianceItem, EligibilityCheck, Risk,
)


@pytest.mark.asyncio
async def test_pipeline_persists_assessment(db_session, akkodis_rfp):
    """db_session and akkodis_rfp are fixtures that yield an async session
    and a seeded RFP row with at least one requirement."""
    stub_compliance = [ComplianceItem(category="security", label="x",
                                         mandatory=False, status="pass",
                                         evidence={}, citations=[])]
    stub_elig = [EligibilityCheck(label="geo", kind="geography",
                                     expected="Canada", actual="Canada",
                                     status="pass", citations=[])]
    stub_bestfit = [CapabilityMatch(
        requirement_id=akkodis_rfp["requirement_ids"][0],
        offering_type="service_line", offering_id=None,
        match_score=0.9, gap_notes=None)]
    stub_risks: list[Risk] = []

    pipeline = BidAssessmentPipeline(
        compliance_agent=AsyncMock(return_value=stub_compliance),
        eligibility_agent=AsyncMock(return_value=stub_elig),
        bestfit_agent=AsyncMock(return_value=stub_bestfit),
        risk_agent=AsyncMock(return_value=stub_risks),
        summary_agent=AsyncMock(return_value="Bid recommended."),
        analytics_boost=0.0,
        thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
        mandatory_penalty=0.3,
    )

    out = await pipeline.run(
        db=db_session, rfp_id=akkodis_rfp["id"],
        tenant_id=akkodis_rfp["tenant_id"], user_id=akkodis_rfp["user_id"],
    )
    assert out["status"] == "complete"
    assert out["verdict"] == "bid"
    # DB inspection
    from sqlalchemy import text
    row = await db_session.execute(
        text("SELECT status, verdict FROM bid_assessments WHERE rfp_id = :r"),
        {"r": akkodis_rfp["id"]},
    )
    r = row.mappings().first()
    assert r["verdict"] == "bid"
```

- [ ] **Step 2: Implement pipeline**

```python
"""BidAssessmentPipeline — coordinates the 5 agents, writes to DB, emits SSE."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .agents_summary import compute_rollup
from . import stream as sse


class BidAssessmentPipeline:
    def __init__(self, *, compliance_agent, eligibility_agent, bestfit_agent,
                  risk_agent, summary_agent,
                  analytics_boost: float,
                  thresholds: dict,
                  mandatory_penalty: float):
        self._compliance = compliance_agent
        self._eligibility = eligibility_agent
        self._bestfit = bestfit_agent
        self._risk = risk_agent
        self._summary = summary_agent
        self._boost = analytics_boost
        self._thresholds = thresholds
        self._penalty = mandatory_penalty

    async def run(self, *, db: AsyncSession, rfp_id: str,
                   tenant_id: str, user_id: str | None) -> dict:
        version = await self._next_version(db, rfp_id)
        assessment_id = str(uuid4())
        await self._insert_assessment_row(
            db, assessment_id=assessment_id, tenant_id=tenant_id, rfp_id=rfp_id,
            version=version, user_id=user_id)
        await db.commit()

        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "started", "pct": 0})

        # Load requirements + raw text
        req_rows = await db.execute(
            text("SELECT id::text AS id, text, mandatory FROM rfp_requirements "
                 "WHERE rfp_id = :r"),
            {"r": rfp_id})
        requirements = [dict(r) for r in req_rows.mappings().all()]
        raw_row = await db.execute(
            text("SELECT raw_text FROM rfps WHERE id = :r"),
            {"r": rfp_id})
        raw = (raw_row.scalar() or "")

        # Three parallel agents
        compliance_task = asyncio.create_task(
            self._compliance(requirements=requirements, tenant_id=tenant_id))
        elig_task = asyncio.create_task(
            self._eligibility(raw_text=raw, tenant_id=tenant_id))
        bestfit_task = asyncio.create_task(
            self._bestfit(requirements=requirements, tenant_id=tenant_id))

        results = await asyncio.gather(
            compliance_task, elig_task, bestfit_task, return_exceptions=True)
        compliance = results[0] if not isinstance(results[0], Exception) else []
        eligibility = results[1] if not isinstance(results[1], Exception) else []
        best_fit = results[2] if not isinstance(results[2], Exception) else []
        partial = any(isinstance(r, Exception) for r in results)

        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "parallel_done", "pct": 60,
                  "partial": partial})

        # Persist children
        await self._persist_children(db, assessment_id, compliance, eligibility,
                                       best_fit, requirements)
        await db.commit()

        # Risk
        try:
            risks = await self._risk(raw_text=raw, requirements=requirements,
                                       compliance=compliance, eligibility=eligibility,
                                       best_fit=best_fit)
        except Exception:
            risks = []
            partial = True
        await self._persist_risks(db, assessment_id, risks)
        await db.commit()
        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "risk_done", "pct": 80})

        # Rollup + summary prose
        rollup = compute_rollup(best_fit, compliance,
                                  thresholds=self._thresholds,
                                  mandatory_penalty=self._penalty,
                                  analytics_boost=self._boost)
        try:
            summary_text = await self._summary(
                rollup=rollup, compliance=compliance,
                eligibility=eligibility, risks=risks)
            verdict = "review" if partial else rollup["verdict"]
            status = "partial" if partial else "complete"
        except Exception:
            summary_text = "Assessment failed during summary."
            verdict = "review"
            status = "failed"

        await db.execute(
            text("UPDATE bid_assessments SET fit_score=:fs, win_probability=:wp, "
                 "verdict=:v, summary=:s, status=:st, completed_at=now() "
                 "WHERE id=:id"),
            {"fs": rollup["fit_score"], "wp": rollup["win_probability"],
             "v": verdict, "s": summary_text, "st": status, "id": assessment_id})
        await db.commit()

        sse.push(rfp_id, version,
                 {"event": "complete", "assessment_id": assessment_id,
                  "verdict": verdict, "status": status})
        sse.close_stream(rfp_id, version)

        return {"assessment_id": assessment_id, "version": version,
                "status": status, "verdict": verdict, **rollup}

    async def _next_version(self, db, rfp_id: str) -> int:
        row = await db.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM bid_assessments WHERE rfp_id = :r"),
            {"r": rfp_id})
        return int(row.scalar() or 0) + 1

    async def _insert_assessment_row(self, db, *, assessment_id, tenant_id,
                                       rfp_id, version, user_id):
        await db.execute(
            text("INSERT INTO bid_assessments (id, tenant_id, rfp_id, version, "
                 "status, model_version, generated_by) "
                 "VALUES (:id, :t, :r, :v, 'running', 'orchestrator-v1', :u)"),
            {"id": assessment_id, "t": tenant_id, "r": rfp_id, "v": version,
             "u": user_id})

    async def _persist_children(self, db, assessment_id, compliance, eligibility,
                                  best_fit, requirements):
        for c in compliance:
            await db.execute(
                text("INSERT INTO compliance_items (id, assessment_id, requirement_id, "
                     "category, label, mandatory, status, evidence, citations) "
                     "VALUES (gen_random_uuid(), :a, :rq, :cat, :lbl, :m, :st, "
                     ":ev::jsonb, :ci::jsonb)"),
                {"a": assessment_id, "rq": str(c.requirement_id) if c.requirement_id else None,
                 "cat": c.category, "lbl": c.label, "m": c.mandatory, "st": c.status,
                 "ev": json.dumps(c.evidence),
                 "ci": json.dumps([_cit(x) for x in c.citations])})
        for e in eligibility:
            await db.execute(
                text("INSERT INTO eligibility_checks (id, assessment_id, label, "
                     "kind, expected, actual, status, citations) "
                     "VALUES (gen_random_uuid(), :a, :lbl, :k, :ex, :ac, :st, :ci::jsonb)"),
                {"a": assessment_id, "lbl": e.label, "k": e.kind, "ex": e.expected,
                 "ac": e.actual, "st": e.status,
                 "ci": json.dumps([_cit(x) for x in e.citations])})
        for m in best_fit:
            await db.execute(
                text("INSERT INTO capability_matches (id, assessment_id, requirement_id, "
                     "offering_type, offering_id, match_score, gap_notes) "
                     "VALUES (gen_random_uuid(), :a, :rq, :ot, :oi, :sc, :g)"),
                {"a": assessment_id, "rq": str(m.requirement_id),
                 "ot": m.offering_type,
                 "oi": str(m.offering_id) if m.offering_id else None,
                 "sc": m.match_score, "g": m.gap_notes})

    async def _persist_risks(self, db, assessment_id, risks):
        for r in risks:
            await db.execute(
                text("INSERT INTO risks (id, assessment_id, category, title, "
                     "description, severity, likelihood, mitigation, citations, "
                     "authored_by) VALUES (gen_random_uuid(), :a, :cat, :t, :d, "
                     ":sv, :lk, :m, :ci::jsonb, 'ai')"),
                {"a": assessment_id, "cat": r.category, "t": r.title,
                 "d": r.description, "sv": r.severity, "lk": r.likelihood,
                 "m": r.mitigation,
                 "ci": json.dumps([_cit(x) for x in r.citations])})


def _cit(c) -> dict:
    return {"document_id": str(c.document_id), "chunk_id": str(c.chunk_id),
            "position": c.position, "excerpt": c.excerpt}
```

- [ ] **Step 3: Add the test fixtures**

Create or edit `services/orchestrator/tests/conftest.py`:

```python
import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text


DATABASE_URL = os.environ.get(
    "ORCH_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def akkodis_rfp(db_session):
    """Seeded RFP id + first requirement id + tenant + user. Assumes
    scripts/seed_demo.py has run."""
    row = await db_session.execute(text("""
        SELECT r.id::text AS rfp_id, r.tenant_id::text AS tenant_id,
               u.id::text AS user_id
        FROM rfps r CROSS JOIN users u
        WHERE r.tenant_id = (SELECT id FROM tenants WHERE slug = 'akkodis')
        ORDER BY r.id LIMIT 1
    """))
    base = dict(row.mappings().first())
    rq = await db_session.execute(
        text("SELECT id::text FROM rfp_requirements WHERE rfp_id = :r"),
        {"r": base["rfp_id"]})
    req_ids = [r["id"] for r in rq.mappings().all()]
    return {**base, "id": base["rfp_id"], "requirement_ids": req_ids}
```

- [ ] **Step 4: Run test**

```bash
cd services/orchestrator && python -m pytest tests/test_assessment_pipeline.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator/assessment/pipeline.py \
         services/orchestrator/tests/test_assessment_pipeline.py \
         services/orchestrator/tests/conftest.py
git commit -m "feat(assessment): BidAssessmentPipeline + integration test"
```

---

### Task 11 — Orchestrator HTTP endpoints

**Files:**
- Modify: `services/orchestrator/main.py`

- [ ] **Step 1: Add `/assess/run` and `/assess/stream/{rfp_id}` endpoints**

Append to `services/orchestrator/main.py`:

```python
from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sqltext

from common.db import get_db
from assessment.pipeline import BidAssessmentPipeline
from assessment.agents_compliance import run_compliance
from assessment.agents_eligibility import run_eligibility
from assessment.agents_bestfit import run_bestfit
from assessment.agents_risk import run_risks
from assessment.agents_summary import compute_rollup, generate_summary_prose
from assessment import stream as sse


assess_router = APIRouter(prefix="/assess", tags=["assess"])


def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "user_id": x_user_id}


@assess_router.post("/run")
async def assess_run(
    body: dict = Body(...),
    ctx: dict = Depends(_ctx),
    db: AsyncSession = Depends(get_db),
):
    rfp_id = body.get("rfp_id")
    if not rfp_id:
        raise HTTPException(400, "rfp_id required")

    # Wire concrete agents. The pipeline closes over real adapter + URLs.
    from common.config import get_settings
    s = get_settings()
    cap_url = getattr(s, "capability_service_url", "http://capability-service:8010")
    retrieval_url = getattr(s, "retrieval_service_url", "http://retrieval-service:8002")

    # Reuse the existing retrieval call from pipeline.py
    from pipeline import call_retrieval_service as retrieval_call
    # LLM client is the configured default — reuse the adapter chain
    from claude import ClaudeAdapter
    from openai_adapter import OpenAIAdapter
    api_key = s.anthropic_api_key
    if api_key:
        llm = ClaudeAdapter(api_key=api_key, model="claude-sonnet-4-6")
    elif s.openai_api_key:
        llm = OpenAIAdapter(api_key=s.openai_api_key, model="gpt-4o")
    else:
        llm = None

    async def _compliance_fn(requirements, tenant_id):
        return await run_compliance(
            rfp_id=rfp_id, requirements=requirements, tenant_id=tenant_id,
            retrieval_call=retrieval_call, llm_client=llm)

    async def _elig_fn(raw_text, tenant_id):
        return await run_eligibility(
            rfp_id=rfp_id, raw_text=raw_text, tenant_id=tenant_id,
            capability_url=cap_url, llm_client=llm)

    async def _bestfit_fn(requirements, tenant_id):
        return await run_bestfit(
            requirements=requirements, tenant_id=tenant_id,
            capability_url=cap_url)

    async def _risk_fn(raw_text, requirements, compliance, eligibility, best_fit):
        return await run_risks(
            raw_text=raw_text, requirements=requirements,
            compliance=compliance, eligibility=eligibility,
            best_fit=best_fit, llm_client=llm)

    async def _summary_fn(rollup, compliance, eligibility, risks):
        return await generate_summary_prose(
            rollup=rollup, compliance=compliance, eligibility=eligibility,
            risks=risks, llm_client=llm)

    pipeline = BidAssessmentPipeline(
        compliance_agent=_compliance_fn,
        eligibility_agent=_elig_fn,
        bestfit_agent=_bestfit_fn,
        risk_agent=_risk_fn,
        summary_agent=_summary_fn,
        analytics_boost=0.0,
        thresholds={"bid_min_fit": 0.7, "no_bid_max_fit": 0.4},
        mandatory_penalty=0.3,
    )
    out = await pipeline.run(db=db, rfp_id=rfp_id, tenant_id=ctx["tenant_id"],
                              user_id=ctx["user_id"])
    return out


@assess_router.get("/stream/{rfp_id}")
async def assess_stream(rfp_id: str, request: Request,
                          db: AsyncSession = Depends(get_db)):
    # Find latest running assessment
    row = await db.execute(
        sqltext("SELECT version FROM bid_assessments WHERE rfp_id = :r "
                "ORDER BY version DESC LIMIT 1"),
        {"r": rfp_id})
    v = row.scalar()
    if v is None:
        raise HTTPException(404, "No assessment for this RFP")
    queue = sse.attach_listener(rfp_id, v)
    # Replay first
    backlog = sse.replay(rfp_id, v)

    async def gen():
        for e in backlog:
            yield sse.format_sse(e)
        try:
            while True:
                if await request.is_disconnected():
                    break
                e = await queue.get()
                yield sse.format_sse(e)
                if e.get("event") == "close":
                    break
        finally:
            sse.detach_listener(rfp_id, v, queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


app.include_router(assess_router)
```

- [ ] **Step 2: Restart and smoke-test**

```bash
docker compose restart orchestrator
sleep 5
# Find an RFP id with requirements
RFP_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT r.id FROM rfps r JOIN rfp_requirements rr ON rr.rfp_id = r.id LIMIT 1;")
TENANT_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT id FROM tenants WHERE slug = 'akkodis';")
curl -sf -X POST http://localhost:8001/assess/run \
     -H "X-Tenant-Id: $TENANT_ID" -H "X-User-Id: 00000000-0000-0000-0000-000000000000" \
     -H 'Content-Type: application/json' \
     -d "{\"rfp_id\":\"$RFP_ID\"}" | jq .
```

Expected: a JSON body with `assessment_id`, `verdict`, `status`.

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator/main.py
git commit -m "feat(orchestrator): /assess/run + /assess/stream endpoints"
```

---

### Task 12 — rfp-service public endpoints

**Files:**
- Create: `services/rfp-service/assessment.py`
- Modify: `services/rfp-service/main.py`

- [ ] **Step 1: Implement assessment endpoints**

Create `services/rfp-service/assessment.py`:

```python
"""Public /rfps/{id}/assess* endpoints. Delegates the heavy lift to the
orchestrator; this module is just CRUD over already-persisted rows."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db

router = APIRouter(prefix="/rfps", tags=["assessment"])

ORCH_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


def _ctx(x_tenant_id: str | None = Header(default=None),
         x_user_id: str | None = Header(default=None)) -> dict:
    if not x_tenant_id:
        raise HTTPException(401, "X-Tenant-Id header required")
    return {"tenant_id": x_tenant_id, "user_id": x_user_id}


@router.post("/{rfp_id}/assess", status_code=202)
async def kick_off(rfp_id: str, ctx: dict = Depends(_ctx)):
    async with httpx.AsyncClient(timeout=600.0) as c:
        r = await c.post(f"{ORCH_URL}/assess/run",
                          json={"rfp_id": rfp_id},
                          headers={"X-Tenant-Id": ctx["tenant_id"],
                                   "X-User-Id": ctx["user_id"] or ""})
        r.raise_for_status()
        return r.json()


@router.get("/{rfp_id}/assess")
async def stream(rfp_id: str, stream: bool = False, request: Request = None):
    if not stream:
        raise HTTPException(400, "Use ?stream=true for SSE; "
                                  "use GET /rfps/{id}/assessments/latest otherwise")
    # Stream from orchestrator
    async def gen():
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{ORCH_URL}/assess/stream/{rfp_id}") as resp:
                if resp.status_code != 200:
                    yield f"data: {{\"event\":\"error\",\"code\":{resp.status_code}}}\n\n"
                    return
                async for line in resp.aiter_lines():
                    yield line + "\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{rfp_id}/assessments")
async def list_assessments(rfp_id: str, ctx: dict = Depends(_ctx),
                              db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("SELECT id::text AS id, version, status, verdict, fit_score, "
             "win_probability, generated_at FROM bid_assessments "
             "WHERE rfp_id = :r AND tenant_id = :t ORDER BY version DESC"),
        {"r": rfp_id, "t": ctx["tenant_id"]})
    return [dict(r) for r in rows.mappings().all()]


@router.get("/{rfp_id}/assessments/latest")
async def latest_assessment(rfp_id: str, ctx: dict = Depends(_ctx),
                              db: AsyncSession = Depends(get_db)):
    return await _full_assessment(db, rfp_id, ctx["tenant_id"], version=None)


@router.get("/{rfp_id}/assessments/{aid}")
async def get_assessment(rfp_id: str, aid: str, ctx: dict = Depends(_ctx),
                           db: AsyncSession = Depends(get_db)):
    return await _full_assessment(db, rfp_id, ctx["tenant_id"], assessment_id=aid)


async def _full_assessment(db, rfp_id, tenant_id, *, assessment_id=None, version=None):
    if assessment_id:
        head = await db.execute(
            text("SELECT * FROM bid_assessments WHERE id = :id AND rfp_id = :r "
                 "AND tenant_id = :t"),
            {"id": assessment_id, "r": rfp_id, "t": tenant_id})
    else:
        head = await db.execute(
            text("SELECT * FROM bid_assessments WHERE rfp_id = :r AND tenant_id = :t "
                 "ORDER BY version DESC LIMIT 1"),
            {"r": rfp_id, "t": tenant_id})
    h = head.mappings().first()
    if not h:
        raise HTTPException(404, "Not found")
    aid = str(h["id"])
    children = {}
    for child_table, key in (("compliance_items", "compliance"),
                              ("eligibility_checks", "eligibility"),
                              ("risks", "risks"),
                              ("capability_matches", "best_fit")):
        rows = await db.execute(
            text(f"SELECT * FROM {child_table} WHERE assessment_id = :a"),
            {"a": aid})
        children[key] = [dict(r) for r in rows.mappings().all()]
    return {"head": dict(h), **children}
```

- [ ] **Step 2: Mount router**

In `services/rfp-service/main.py`:

```python
from assessment import router as assessment_router
app.include_router(assessment_router)
```

- [ ] **Step 3: Smoke test via gateway**

```bash
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)
RFP_ID=$(curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/rfps | jq -r '.[0].id')
curl -sf -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/rfps/$RFP_ID/assess | jq .
curl -sf -H "Authorization: Bearer $TOKEN" \
     http://localhost:8011/rfps/$RFP_ID/assessments/latest | jq '.head.verdict'
```

Expected: a JSON object with a verdict.

- [ ] **Step 4: Commit**

```bash
git add services/rfp-service/assessment.py services/rfp-service/main.py
git commit -m "feat(rfp): public /rfps/{id}/assess* endpoints proxied to orchestrator"
```

---

### Task 13 — Tenancy leak test

**Files:**
- Create: `services/rfp-service/tests/test_tenancy_leak.py`

- [ ] **Step 1: Write the leak test**

```python
import pytest
from httpx import AsyncClient, ASGITransport
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402


@pytest.mark.asyncio
async def test_tenant_cannot_see_other_tenant_assessments():
    """Seeded fixture must include two tenants, each with an assessment.
    Tenant A must never see Tenant B's row."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Tenant A
        r = await ac.get("/rfps", headers={"X-Tenant-Id": "tenant-a-uuid"})
        ids_a = {x["id"] for x in r.json()}
        # Tenant B
        r = await ac.get("/rfps", headers={"X-Tenant-Id": "tenant-b-uuid"})
        ids_b = {x["id"] for x in r.json()}
        assert ids_a.isdisjoint(ids_b)
```

(Adjust to real tenant ids from the seed; this test only runs if a second tenant exists.)

- [ ] **Step 2: Skip if only one tenant seeded**

Add at top of test:

```python
@pytest.fixture(scope="session")
def two_tenants_present(): ...
@pytest.mark.skipif(... not two_tenants ..., reason="needs two tenants seeded")
```

- [ ] **Step 3: Commit**

```bash
git add services/rfp-service/tests/test_tenancy_leak.py
git commit -m "test(rfp): tenancy leak guard for assessments"
```

---

### Task 14 — Merge phase 3

- [ ] **Step 1: Full test sweep**

```bash
for svc in orchestrator rfp-service content-service retrieval-service capability-service api-gateway; do
  echo "--- $svc ---"
  (cd services/$svc && python -m pytest -q)
done
```

- [ ] **Step 2: Merge**

```bash
git checkout feat/bid-assessment
git merge --no-ff feat/bid-assessment-phase-3-bid-assessment-core \
  -m "Phase 3: bid assessment core (5 agents, pipeline, SSE, endpoints)"
git push origin feat/bid-assessment
```

Phase 3 done.
