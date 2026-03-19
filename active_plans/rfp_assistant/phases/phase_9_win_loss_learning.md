# Phase 9: Win/Loss Learning Agent

**Status:** Pending
**Planned Start:** 2026-05-22
**Target End:** 2026-05-28
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_9_win_loss_learning.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 8 | Next: None

---

## Detailed Objective

This phase implements the Win/Loss Learning Agent from spec_additional §4: a continuous improvement loop that extracts lessons from historical RFP outcomes (win, loss, no_decision), updates the system's retrieval and generation strategies, and surfaces actionable insights via a reporting endpoint. Over time, this agent makes the system progressively better at predicting which content and solutions win deals.

The `win_loss_records` table (Phase 1 Task 5.4) stores the raw outcomes. The Win/Loss Learning Agent performs three functions: (1) lesson extraction — uses an LLM to analyze the winning/losing RFP responses and identify patterns (e.g., "answers referencing product X win in regulated industries"); (2) knowledge reinforcement — upweights chunks and products associated with winning responses in retrieval scoring; (3) insight reporting — exposes analytics on win rates by product, industry, region, and answer quality.

Domain isolation is fully preserved: each tenant's win/loss data trains only their own scoring adjustments; no cross-tenant learning occurs.

Success is defined as: after recording 5+ win/loss outcomes, the system can produce an insight report per tenant showing win rate trends, top-performing content, and gap patterns from lost deals.

---

## Deliverables Snapshot

1. `POST /rfps/{id}/outcome` endpoint — record a win/loss/no_decision outcome with optional notes.
2. `services/orchestrator/win_loss_agent.py` — `WinLossLearningAgent.analyze(tenant_id)` that processes all `win_loss_records` and extracts lessons into `win_loss_lessons(id, tenant_id, lesson TEXT, pattern JSONB, created_at)`.
3. `services/retrieval-service/scoring_adjustments.py` — applies win/loss-derived score boosts to chunk retrieval results (content that appears in winning responses scores +10%).
4. `GET /admin/insights` endpoint — returns win rate by product, industry, region; top 5 performing content chunks; gap patterns from lost deals.
5. Integration tests: seed 5 win and 5 loss records; run agent; assert lessons generated and scoring adjustments recorded.

---

## Acceptance Gates

- [ ] Gate 1: `POST /rfps/{id}/outcome` with `{outcome: "win", notes: "...", lessons_learned: "..."}` creates a `win_loss_records` row; an invalid outcome value returns HTTP 422.
- [ ] Gate 2: After running `WinLossLearningAgent.analyze(tenant_id)` against 5+ records, `win_loss_lessons` table contains at least 1 row with non-empty `lesson` and `pattern`.
- [ ] Gate 3: Chunks appearing in ≥ 3 winning responses receive a positive score adjustment (verified by comparing retrieval scores before and after running the agent).
- [ ] Gate 4: `GET /admin/insights` returns a structured report with `win_rate`, `top_content`, and `loss_gaps` fields; scoped to the requesting tenant (domain isolation verified by test).

---

## Scope

- In Scope:
  1. Win/loss outcome recording endpoint.
  2. Lesson extraction via LLM analysis of winning/losing response patterns.
  3. Retrieval score boosts for content associated with winning deals.
  4. Insight reporting endpoint with win rate trends and gap analysis.
  5. Domain isolation per tenant for all learning data.
- Out of Scope:
  1. Automated outcome detection (CRM sync) — post-MVP per spec_additional §4.
  2. Predictive win probability scoring on new RFPs (post-MVP).
  3. A/B testing framework for response strategies (post-MVP).
  4. Real-time learning (agent runs as a scheduled batch job for MVP).

---

## Interfaces & Dependencies

- Internal: Phase 1 (Task 5.4) — `win_loss_records` table. Phase 3 — retrieval scoring in `reranker.py`. Phase 4 — `AgentPipeline`, `ResponseGenerationAgent`. Phase 5 — `rfp_answers` (source of winning/losing content).
- External: No new external dependencies.
- Artifacts: `services/orchestrator/win_loss_agent.py`; `services/retrieval-service/scoring_adjustments.py`; new Alembic migration `0006_win_loss_lessons.py`; `tests/test_win_loss.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Insufficient win/loss data for meaningful learning | No lessons generated | Agent returns empty lessons gracefully; minimum 5 records required (enforced with early return + log) |
| Score boosts compound over many runs causing retrieval bias | Poor retrieval quality | Cap score adjustment at +15% per chunk; decay old adjustments after 90 days |
| LLM-generated lessons contain sensitive competitive data | Data leak risk | Lessons stored only in DB; not exposed via API except to system_admin |
| Domain isolation breach in lesson computation | Cross-tenant learning | All queries in `WinLossLearningAgent` filter by `tenant_id`; dedicated isolation test |

---

## Decision Log

- D1: Win/loss agent runs as a batch job (not real-time) — sufficient for MVP; real-time learning is post-MVP — Status: Closed — Date: 2026-03-18
- D2: Score adjustments stored in `chunk_score_adjustments(chunk_id, tenant_id, boost FLOAT, expires_at)` table; applied additively in RRF step — Status: Closed — Date: 2026-03-18
- D3: Lesson extraction uses the same model adapter as response generation — no dedicated model — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec_additional.md` — §4 Learning Domain and Portfolio Orchestration Model, §3 Win/Loss Learning Agent
- `migrations/versions/0005_portfolio_schema.py` — `win_loss_records` table
- `services/retrieval-service/reranker.py` — RRF scoring to be extended with adjustments (Phase 3)
- `services/orchestrator/pipeline.py` — `AgentPipeline` (Phase 4)

### Destination Files (new files this phase creates)
- `migrations/versions/0006_win_loss_lessons.py` — `win_loss_lessons` and `chunk_score_adjustments` tables
- `services/orchestrator/win_loss_agent.py` — Learning agent
- `services/retrieval-service/scoring_adjustments.py` — Score boost loader
- `tests/test_win_loss.py` — Outcome recording, lesson extraction, score adjustment tests

### Related Documentation (context only)
- `active_plans/rfp_assistant/phases/phase_3_retrieval.md` — Retrieval scoring
- `active_plans/rfp_assistant/phases/phase_5_rfp_service.md` — rfp_answers source data
- `spec_additional.md` — Full Keystone spec

---

## Tasks

### [✅] 1 Implement Win/Loss Outcome Recording
Build the endpoint to record RFP outcomes and store associated metadata.

  - [✅] 1.1 Implement `POST /rfps/{id}/outcome` — accept `{outcome: Literal["win","loss","no_decision"], notes: str, lessons_learned: str}`; insert `win_loss_records` row; require authenticated user (any role)
  - [✅] 1.2 Implement `GET /rfps/{id}/outcome` — return the outcome record if it exists; return HTTP 404 if not yet recorded
  - [✅] 1.3 Write `tests/test_win_loss.py` for outcome recording — assert win/loss/no_decision all accepted; assert invalid value returns 422; assert row in DB

### [✅] 2 Implement Win/Loss Learning Agent
Extract lessons and patterns from historical outcomes using LLM analysis.

  - [✅] 2.1 Create Alembic migration `0006_win_loss_lessons.py` — add `win_loss_lessons(id, tenant_id, lesson TEXT, pattern JSONB, source_rfp_ids JSONB, created_at)` and `chunk_score_adjustments(chunk_id, tenant_id, boost FLOAT, expires_at TIMESTAMP)` tables
  - [✅] 2.2 Implement `WinLossLearningAgent.analyze(tenant_id)` — fetch all `win_loss_records` for tenant; if < 5 records return empty; call `ResponseGenerationAgent` with a lesson-extraction prompt over winning vs. losing answer pairs; parse structured lessons into `win_loss_lessons` rows
  - [✅] 2.3 Implement `WinLossLearningAgent.apply_score_boosts(tenant_id)` — for chunks that appear in winning `rfp_answers`, upsert `chunk_score_adjustments` with `boost=0.10`; cap total boost at 0.15; set `expires_at = NOW() + 90 days`
  - [✅] 2.4 Write `tests/test_win_loss.py` learning tests — seed 5 win + 5 loss records; run agent; assert `win_loss_lessons` rows created; assert boosted chunks have `chunk_score_adjustments` rows

### [✅] 3 Integrate Score Adjustments into Retrieval
Apply win/loss-derived boosts during retrieval scoring without breaking RBAC or domain isolation.

  - [✅] 3.1 Implement `load_score_adjustments(chunk_ids: list[str], tenant_id) -> dict[str, float]` in `scoring_adjustments.py` — batch-fetch non-expired `chunk_score_adjustments` rows for given chunk IDs and tenant; return `{chunk_id: boost}`
  - [✅] 3.2 Extend `reciprocal_rank_fusion` in `reranker.py` to accept an optional `score_adjustments` dict; add boost to RRF score after fusion: `final_score = rrf_score * (1 + boost)`
  - [✅] 3.3 Wire `load_score_adjustments` into the `retrieve` orchestrator: call it after dedup, before RRF; pass adjustments to `reciprocal_rank_fusion`
  - [✅] 3.4 Write `tests/test_scoring_adjustments.py` — seed adjustments for chunk A; assert chunk A ranks higher after adjustment; assert tenant B's adjustments do not affect tenant A's results

### [✅] 4 Implement Insight Reporting Endpoint
Expose win rate analytics, top content, and loss gap analysis to system_admins.

  - [✅] 4.1 Implement `GET /admin/insights` (system_admin) — return `{win_rate: float, total_rfps: int, by_product: [{product_id, win_rate}], by_industry: [{industry, win_rate}], top_content: [{chunk_id, doc_id, win_appearances}], loss_gaps: [{requirement_category, frequency}]}`
  - [✅] 4.2 Compute `loss_gaps` by joining `win_loss_records(outcome=loss)` → `rfps` → `rfp_requirements` → `questionnaire_items(flagged=true)` grouped by `requirement.category`
  - [✅] 4.3 Write `tests/test_insights.py` — seed wins and losses with known patterns; assert win_rate computed correctly; assert loss_gaps reflects flagged questionnaire items from lost RFPs; assert endpoint scoped to tenant (non-admin gets 403)

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile rfp_assistant` if checkmarks appear stale.

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] Optional deeper tasks use `- [ ] N.1.1` and never headings.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.

### Traceability

- [ ] All tasks reflect Detailed Objective and Scope.
- [ ] Task titles match what will appear in the master plan.
- [ ] No invented tasks.

### Consistency

- [ ] Section ordering follows the template.
- [ ] All metadata fields are present in the Header.
- [ ] Deliverables Snapshot, Acceptance Gates, and Scope refer to real tasks.

### References

- [ ] Source, Destination, and Related Documentation sections appear.
