# Phase 3: Bid Assessment Core

**Status:** Pending
**Planned Start:** 2026-06-04
**Target End:** 2026-06-18
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_3_bid_assessment.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: Phase 2 | Next: Phase 4

---

## Detailed Objective

Land the bid-assessment workflow end-to-end at the API layer: seven new tables in `rfp-service` (`bid_assessments`, `compliance_items`, `eligibility_checks`, `risks`, `capability_matches`, `bid_decisions`, `assessment_exports`); a new `BidAssessmentPipeline` in `orchestrator` running five typed agents (Compliance, Eligibility, BestFit in parallel; then Risk; then ExecSummary); REST endpoints to trigger the pipeline, stream its progress over SSE, fetch the result with all children embedded, edit individual rows, and record the human bid decision.

This is the largest single phase. It depends on Phases 1 (capability profile for BestFit/Eligibility) and 2 (snippet-aware retrieval for Compliance). Verification: an end-to-end `POST /rfps/{id}/assess` against an Akkodis-seeded RFP returns a `bid_assessments` row whose fit_score, win_probability, verdict, and exec summary read coherently and whose child rows reference real requirements, real capability rows, and real citations.

Success: `POST /rfps/{id}/assess` runs the full 5-agent pipeline against any seeded RFP and persists a structured assessment; `POST /rfps/{id}/bid-decision` records a human decision that gates the Draft stage in subsequent phases; PATCH endpoints permit human edits with optimistic-lock semantics.

---

## Deliverables Snapshot

1. Migration `migrations/versions/0013_bid_assessments.py` creating 7 assessment tables, all with `tenant_id` and FK to `rfps` where relevant.
2. New module `services/orchestrator/bid_assessment.py` defining `BidAssessmentPipeline` plus the 5 agents (Compliance, Eligibility, BestFit, Risk, ExecSummary).
3. New prompts in `services/orchestrator/prompts.py` for each agent.
4. `rfp-service` endpoints: `POST /rfps/{id}/assess`, `GET /rfps/{id}/assess?stream=true`, `GET /rfps/{id}/assessments`, `GET /rfps/{id}/assessments/latest`, `GET /rfps/{id}/assessments/{aid}`, plus PATCH endpoints on children.
5. `rfp-service` endpoints: `POST /rfps/{id}/bid-decision`, `GET /rfps/{id}/bid-decision`.
6. SSE event protocol documented in code: events `stage_started`, `agent_completed`, `agent_failed`, `pipeline_complete`.
7. Pipeline integration test using stub agents to verify orchestration + DB persistence.
8. End-to-end test against the Akkodis seeded RFPs producing real LLM-driven assessments (gated behind `ENABLE_LLM_TESTS=1`).

---

## Acceptance Gates

- [ ] Gate 1: Alembic at revision 0013; round-trip test passes.
- [ ] Gate 2: `POST /rfps/{id}/assess` against an Akkodis-seeded RFP returns 200 with `{assessment_id, status:"running"}`; SSE stream produces `pipeline_complete` event within 120s; subsequent `GET /rfps/{id}/assessments/latest` returns a fully populated assessment.
- [ ] Gate 3: All compliance/eligibility/risk/capability_match rows belong to the same assessment and the same tenant as the RFP; tenancy-leak test passes for all 7 new tables.
- [ ] Gate 4: PATCH on a child row with mismatched `If-Match: <version>` returns 409.
- [ ] Gate 5: `POST /rfps/{id}/bid-decision` records the decision; later assessments don't clobber it.
- [ ] Gate 6: Pipeline integration test with stub agents passes deterministically (no LLM calls).
- [ ] Gate 7: When one of the three parallel agents fails (simulated via stub), the pipeline persists surviving outputs, sets `status='partial'`, and ExecSummary degrades to `verdict='review'`.

---

## Scope

- In Scope:
  1. 7 assessment tables + migration.
  2. `BidAssessmentPipeline` orchestration class (`asyncio.gather` for parallel stage, sequential after).
  3. Five typed agents with Pydantic input/output schemas.
  4. Assessment CRUD endpoints (POST trigger, GET history, GET full, PATCH children).
  5. Bid decision endpoints.
  6. SSE streaming of pipeline progress.
  7. Optimistic-lock semantics (`If-Match: <bid_assessments.version>`).
  8. Win/loss boost integration in ExecSummaryAgent (reads from `analytics-service`).
  9. Integration tests (stub-agent and LLM-gated).
- Out of Scope:
  1. Frontend rendering (Phase 4).
  2. PDF/DOCX export (Phase 5).
  3. Branding application to exports (Phase 6).
  4. Background queue migration — pipeline stays synchronous.
  5. Re-running individual agents — re-run produces a brand-new assessment.
  6. Cross-RFP assessment trends — single-RFP scope only.

---

## Interfaces & Dependencies

- Internal: `services/orchestrator/agents.py` (existing typed-agent base), `services/orchestrator/pipeline.py` (existing AnswerPipeline as reference shape), `services/orchestrator/prompts.py`, `services/retrieval-service` (capability-aware + snippet-aware retrieval from Phase 2), `services/capability-service` (Phase 1 profile reads), `services/analytics-service` (existing win/loss boosts), `common/tenancy.py`.
- External: `httpx` (existing inter-service calls), `pydantic`, `sqlalchemy`, `psycopg`. Whatever LLM adapter the tenant's model-router resolves at request time (no new adapter).
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Pipeline exceeds 120s for large RFPs | SSE timeout, user retries | Bound per-agent token usage; ExtractionAgent already caps requirement count; document phase-2 queue migration; SSE includes periodic heartbeat events. |
| Parallel agent failure cascades into ExecSummary | All-or-nothing assessment failures | `asyncio.gather(return_exceptions=True)`; pipeline persists surviving outputs; ExecSummary degrades to `verdict='review'`. |
| Agent prompts hallucinate citations | Audit trail compromised | All Citation objects validated against actual chunk IDs before persistence; mismatches drop the citation and add a warning to `audit_logs`. |
| Re-runs cause version drift in optimistic-lock PATCH | Confusing 409s for users | UI shows the version in the scorecard header; PATCH error responses include the current server version for client refresh. |
| Capability data not yet seeded for a tenant when assessment runs | BestFit/Eligibility return empty | Pipeline pre-flight checks the tenant's capability profile is non-empty for at least service_lines + certifications; returns 422 if not, with a clear error pointing to the admin UI. |
| Snippet vocabulary changes mid-extraction | Tag mismatches | Extraction freezes the vocabulary at the start of the run; reassessing an RFP refreshes both extraction and assessment. |

---

## Decision Log

- D1: Pipeline is synchronous + SSE; no queue layer in v1 — Status: Closed — Date: 2026-05-13
- D2: First three agents (Compliance, Eligibility, BestFit) run via `asyncio.gather(return_exceptions=True)` — Status: Closed — Date: 2026-05-13
- D3: Risk waits on all three; ExecSummary waits on Risk — Status: Closed — Date: 2026-05-13
- D4: AI verdict and human bid decision live in separate tables — Status: Closed — Date: 2026-05-13
- D5: Optimistic-lock via `If-Match: <bid_assessments.version>` on child PATCH — Status: Closed — Date: 2026-05-13
- D6: Re-runs create new assessments; old rows are kept as history — Status: Closed — Date: 2026-05-13
- D7: Citations validated against real chunk IDs at persistence time — Status: Closed — Date: 2026-05-13
- D8: Pipeline pre-flight 422 if capability profile is insufficient — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `services/orchestrator/agents.py` — existing typed-agent base
- `services/orchestrator/pipeline.py` — existing AnswerPipeline (reference)
- `services/orchestrator/prompts.py` — existing prompt collection
- `services/orchestrator/main.py` — gains assessment endpoints (or proxies to rfp-service)
- `services/retrieval-service/retrieve.py` — Phase 2 category-weighted retrieval
- `services/analytics-service/main.py` — existing win/loss boosts
- `services/rfp-service/main.py` — gains assessment + bid-decision routes
- `services/rfp-service/rfp_crud.py` — existing RFP CRUD; PATCH version pattern reused
- `services/api-gateway/proxy.py` — adds proxy routes for new endpoints

### Destination Files
- `migrations/versions/0013_bid_assessments.py`
- `services/orchestrator/bid_assessment.py` — pipeline + 5 agents
- `services/orchestrator/bid_assessment_schemas.py` — Pydantic schemas
- `services/orchestrator/bid_assessment_prompts.py` — assessment prompts
- `services/rfp-service/assessment_crud.py` — DB operations for assessment tables
- `tests/integration/test_bid_assessment_pipeline.py` — stub-agent tests
- `tests/integration/test_bid_assessment_e2e.py` — LLM-gated end-to-end

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §4.3, §5, §6.4–6.5

---

## Tasks

### [ ] 1 Create bid assessment migration
Author migration 0013 creating 7 assessment tables.

  - [ ] 1.1 `bid_assessments(id, rfp_id, tenant_id, status ENUM(running,complete,partial,failed), fit_score NUMERIC, win_probability NUMERIC, verdict ENUM(bid,no_bid,review), summary TEXT, model_version VARCHAR, generated_by UUID, generated_at TIMESTAMPTZ, version INT)`
  - [ ] 1.2 `compliance_items(id, assessment_id, requirement_id NULLABLE, category, label, mandatory BOOL, status ENUM, evidence JSONB, citations JSONB)`
  - [ ] 1.3 `eligibility_checks(id, assessment_id, label, kind ENUM, expected, actual, status ENUM, citations JSONB)`
  - [ ] 1.4 `risks(id, assessment_id, category ENUM, title, description, severity ENUM, likelihood ENUM, mitigation TEXT NULLABLE, citations JSONB, authored_by ENUM(ai,human))`
  - [ ] 1.5 `capability_matches(id, assessment_id, requirement_id, offering_type ENUM, offering_id NULLABLE, match_score NUMERIC, gap_notes TEXT NULLABLE)`
  - [ ] 1.6 `bid_decisions(id, rfp_id, tenant_id, decision ENUM, decided_by UUID, decided_at TIMESTAMPTZ, rationale TEXT, conditions JSONB)`
  - [ ] 1.7 `assessment_exports(id, assessment_id, format ENUM, file_path VARCHAR, generated_at TIMESTAMPTZ, generated_by UUID)`
  - [ ] 1.8 Indexes on `(rfp_id, generated_at)` and `(assessment_id)` where relevant
  - [ ] 1.9 Working `downgrade()` dropping all 7 tables

### [ ] 2 Define Pydantic schemas
Canonical schemas for all agent inputs/outputs.

  - [ ] 2.1 `Citation`, `ComplianceItem`, `EligibilityCheck`, `Risk`, `CapabilityMatch` in `bid_assessment_schemas.py`
  - [ ] 2.2 `ComplianceAgentInput/Output`, `EligibilityAgentInput/Output`, `BestFitAgentInput/Output`, `RiskAgentInput/Output`, `ExecSummaryAgentInput/Output`
  - [ ] 2.3 Unit tests asserting schema validation rejects malformed input

### [ ] 3 Implement the 5 agents
Each agent subclasses the existing typed-agent base. Pure functions over data; the pipeline owns DB writes.

  - [ ] 3.1 `ComplianceAgent` — for each requirement, retrieve evidence (calls retrieval-service with tenant_id + category boosts + tag boost), produce a ComplianceItem; mark status by evidence strength
  - [ ] 3.2 `EligibilityAgent` — fetches tenant capability profile rollup, classifies bid-killers (geography / contract vehicle / certs / financial / exclusions), produces EligibilityCheck rows
  - [ ] 3.3 `BestFitAgent` — embeds each requirement, matches against service_lines + products embeddings (top-k cosine), produces CapabilityMatch rows with gap_notes when no offering matches
  - [ ] 3.4 `RiskAgent` — given the three parallel outputs + raw RFP text, prompts the LLM to produce a Risk list across 5 categories
  - [ ] 3.5 `ExecSummaryAgent` — reads all prior outputs + analytics score_boosts + tenant verdict_thresholds, produces `{summary, fit_score, win_probability, verdict}`
  - [ ] 3.6 Per-agent prompts in `bid_assessment_prompts.py`
  - [ ] 3.7 Unit tests per agent with stub LLM client

### [ ] 4 Build BidAssessmentPipeline orchestrator class
Coordinates parallel + sequential stages, persists rows, emits SSE events.

  - [ ] 4.1 `BidAssessmentPipeline.run(rfp_id, tenant_id, user_id)` async generator yielding SSE events
  - [ ] 4.2 Pre-flight: ensure capability profile has at least service_lines + certifications; 422 if not
  - [ ] 4.3 Insert a fresh `bid_assessments` row with `status='running'`, `version=previous+1`
  - [ ] 4.4 Parallel stage: `asyncio.gather(compliance, eligibility, bestfit, return_exceptions=True)`; persist surviving outputs; set `status='partial'` if any failed
  - [ ] 4.5 Sequential: Risk receives all (possibly partial) outputs; ExecSummary receives all
  - [ ] 4.6 Validate citations against real chunk IDs before persisting; drop invalid citations and add `audit_logs` warning
  - [ ] 4.7 On final completion, update `bid_assessments.status='complete'` (or `partial`/`failed`)
  - [ ] 4.8 Emit SSE events at each transition

### [ ] 5 Implement assessment endpoints in rfp-service
REST surface for triggering, streaming, listing, fetching, and editing assessments.

  - [ ] 5.1 `POST /rfps/{id}/assess` — kicks off the pipeline (background task), returns 200 with `{assessment_id, status:"running"}`
  - [ ] 5.2 `GET /rfps/{id}/assess?stream=true` — SSE; 404 if no `status=running` row exists for the RFP
  - [ ] 5.3 `GET /rfps/{id}/assessments` — list with pagination
  - [ ] 5.4 `GET /rfps/{id}/assessments/latest` — convenience
  - [ ] 5.5 `GET /rfps/{id}/assessments/{aid}` — full assessment with embedded children
  - [ ] 5.6 `PATCH /rfps/{id}/assessments/{aid}/compliance/{cid}` — content_admin+; requires `If-Match`
  - [ ] 5.7 `PATCH /rfps/{id}/assessments/{aid}/risks/{rid}`, `POST` to add, `DELETE` to remove — end_user+; requires `If-Match`
  - [ ] 5.8 All routes scoped by `common/tenancy.py:tenant_scope`

### [ ] 6 Implement bid decision endpoints
Record human decision separately from AI verdict.

  - [ ] 6.1 `POST /rfps/{id}/bid-decision` — body `{decision, rationale, conditions[]}`; persists row
  - [ ] 6.2 `GET /rfps/{id}/bid-decision` — returns latest
  - [ ] 6.3 No version constraint on multiple decisions — each POST creates a new row; latest wins for gate purposes

### [ ] 7 Wire api-gateway proxies
Proxy the new routes through `api-gateway`.

  - [ ] 7.1 Add route prefixes `/rfps/{id}/assess*`, `/rfps/{id}/assessments*`, `/rfps/{id}/bid-decision` proxied to `rfp-service`
  - [ ] 7.2 SSE proxy uses streaming response (no buffering)
  - [ ] 7.3 Role checks enforced at gateway (matches role table in spec §6.4)

### [ ] 8 Pipeline integration tests (stub agents)
Deterministic orchestration tests with stub LLM responses.

  - [ ] 8.1 `test_bid_assessment_pipeline.py`: stub all 5 agents to return canned outputs
  - [ ] 8.2 Assert pipeline persists correct rows in correct order
  - [ ] 8.3 Test parallel failure case (one of the three raises)
  - [ ] 8.4 Test sequential failure case (Risk raises)
  - [ ] 8.5 Test optimistic-lock 409 on child PATCH with stale version

### [ ] 9 End-to-end LLM-gated test
Real LLM call against the Akkodis seed; gated behind `ENABLE_LLM_TESTS=1`.

  - [ ] 9.1 `test_bid_assessment_e2e.py`: seed Akkodis tenant + one RFP; trigger assessment; assert resulting assessment has non-empty children
  - [ ] 9.2 Sanity-check: fit_score and win_probability are in [0, 1]
  - [ ] 9.3 Sanity-check: verdict is one of `bid`, `no_bid`, `review`
  - [ ] 9.4 Sanity-check: every citation references a real chunk_id

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile <slug>` if checkmarks appear stale.

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
