# Phase 5: RFP Service

**Status:** Pending
**Planned Start:** 2026-04-19
**Target End:** 2026-04-24
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_5_rfp_service.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 4 | Next: Phase 6

---

## Detailed Objective

This phase implements the RFP workspace: creating RFPs, adding questions, auto-generating answers per question via the orchestrator's `ask_pipeline` (in `draft` mode), managing answer versions, and approving final answers. It connects the `rfps`, `rfp_questions`, and `rfp_answers` tables (created in Phase 1) to the orchestrator logic (Phase 4).

The RFP service is the primary user-facing workflow for enterprise users. A user creates an RFP, uploads questions (individually or in bulk), triggers AI-assisted draft generation, reviews and edits drafts, and approves final answers. Each edit creates a new version (`rfp_answers.version` increments); only the latest approved version is returned by default.

Success is defined as: a user can create an RFP, add questions, trigger bulk answer generation, view the drafted answers with citations, edit an answer (producing a new version), and approve it — all through the REST API.

---

## Deliverables Snapshot

1. `POST /rfps`, `GET /rfps/{id}` — Create and retrieve RFP records with nested questions and answers.
2. `POST /rfps/{id}/questions` — Add questions individually or in bulk (JSON array).
3. `POST /rfps/{id}/questions/{qid}/generate` — Trigger answer generation via orchestrator (draft mode); store as `rfp_answers` version 1.
4. `PATCH /rfps/{id}/questions/{qid}/answers/{aid}` — Edit an answer (creates new version); `POST .../approve` — mark answer approved (content_admin).
5. Integration tests: full RFP lifecycle (create → questions → generate → edit → approve).

---

## Acceptance Gates

- [ ] Gate 1: `POST /rfps` creates an RFP record; `GET /rfps/{id}` returns it with nested questions and answers.
- [ ] Gate 2: `POST /rfps/{id}/questions/{qid}/generate` calls the orchestrator `ask_pipeline` in `draft` mode and stores the result as `rfp_answers` row with `version=1` and `approved=false`.
- [ ] Gate 3: Editing an answer via `PATCH` creates a new `rfp_answers` row with `version=N+1`; `GET /rfps/{id}` returns only the latest version by default.
- [ ] Gate 4: `POST .../approve` (content_admin) sets `approved=true` on the specified answer version; an `end_user` call returns HTTP 403.

---

## Scope

- In Scope:
  1. RFP CRUD: create, get (with questions + latest answers), list owned RFPs.
  2. Question management: add single or bulk questions to an RFP.
  3. Answer generation: call orchestrator `ask_pipeline(mode="draft")` per question.
  4. Answer versioning: each edit creates a new row with incremented version.
  5. Answer approval: content_admin marks a version approved.
  6. Bulk generation: generate answers for all unanswered questions in an RFP in one call.
- Out of Scope:
  1. RFP document export (PDF/DOCX export — post-MVP).
  2. Automatic RFP question parsing from uploaded documents (post-MVP).
  3. Answer scoring or quality metrics (post-MVP).
  4. Frontend RFP workspace UI (Phase 6).

---

## Interfaces & Dependencies

- Internal: Phase 1 — `rfps`, `rfp_questions`, `rfp_answers` tables, RBAC middleware. Phase 4 — `ask_pipeline(question, mode="draft", rfp_id, user_ctx)`.
- External: No new external dependencies (all reuse Phase 1–4 stack).
- Artifacts: `services/rfp-service/routes.py`, `services/rfp-service/service.py`; updated `rfp_questions` and `rfp_answers` queries; `tests/test_rfp_service.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Bulk generation for large RFPs (100+ questions) times out | HTTP timeout | Run generation as background task; return `202 Accepted` with a status URL |
| Version conflicts if two users edit simultaneously | Data loss | Use optimistic locking: include `version` in PATCH body; reject if version mismatch |
| Orchestrator unavailable during generation | Generation fails | Return 503 with `retry_after` header; answer stays in `pending` state |

---

## Decision Log

- D1: Answer generation runs as background task for bulk operations — return 202 with polling endpoint — Status: Closed — Date: 2026-03-18
- D2: Only latest version returned by default in GET; `?all_versions=true` returns all — Status: Closed — Date: 2026-03-18
- D3: Optimistic locking on answer edits (version field in PATCH body) — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §3.7 RFPs, §6.4 Create RFP, §6.1 Ask (draft mode)
- `migrations/versions/0002_schema.py` — `rfps`, `rfp_questions`, `rfp_answers` tables
- `services/orchestrator/pipeline.py` — `ask_pipeline` (Phase 4)

### Destination Files (new files this phase creates)
- `services/rfp-service/routes.py` — RFP and question/answer endpoints
- `services/rfp-service/service.py` — Business logic layer
- `tests/test_rfp_service.py` — Full lifecycle integration tests

### Related Documentation (context only)
- `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md`
- `spec.md` — §3.7, §6

---

## Tasks

### [✅] 1 Implement RFP CRUD Endpoints
Create and retrieve RFP records with their nested questions and latest answers.

  - [✅] 1.1 Implement `POST /rfps` — accept `{customer, industry, region}`, insert `rfps` row with `created_by=current_user.id`, return `{rfp_id}`
  - [✅] 1.2 Implement `GET /rfps/{id}` — return RFP with nested `rfp_questions` each containing the latest `rfp_answers` row (highest version); enforce ownership or `system_admin` role
  - [✅] 1.3 Implement `GET /rfps` — list all RFPs owned by current user (paginated, limit 20)

### [✅] 2 Implement Question Management
Add questions to an RFP individually and in bulk.

  - [✅] 2.1 Implement `POST /rfps/{id}/questions` — accept `{question: str}` or `{questions: list[str]}`; insert one or many `rfp_questions` rows; return `{question_ids: list[str]}`
  - [✅] 2.2 Enforce RFP ownership check: only the RFP creator or `system_admin` can add questions
  - [✅] 2.3 Write `tests/test_rfp_service.py` for question creation — assert correct `rfp_id` FK and question text stored

### [✅] 3 Implement Answer Generation and Versioning
Auto-generate drafted answers and support editing with version tracking.

  - [✅] 3.1 Implement `POST /rfps/{id}/questions/{qid}/generate` — call `ask_pipeline(question=q.question, mode="draft", rfp_id=id, user_ctx=current_user)` and store result as `rfp_answers(version=1, approved=false, answer=text)`; for bulk (`POST /rfps/{id}/generate-all`), run as background task and return 202
  - [✅] 3.2 Implement `PATCH /rfps/{id}/questions/{qid}/answers/{aid}` — accept `{answer: str, version: int}` (optimistic lock); if `version` matches latest, insert new row with `version=N+1` and `approved=false`; return 409 on version mismatch
  - [✅] 3.3 Write `tests/test_rfp_service.py` generation tests — mock `ask_pipeline`; assert version increments correctly; assert 409 on stale version

### [✅] 4 Implement Answer Approval
Allow content admins to mark a specific answer version as approved.

  - [✅] 4.1 Implement `POST /rfps/{id}/questions/{qid}/answers/{aid}/approve` — requires `content_admin` or `system_admin`; sets `rfp_answers.approved=true` for the given `aid`
  - [✅] 4.2 Implement `GET /rfps/{id}/questions/{qid}/answers` with `?all_versions=true` — returns all answer versions sorted by version desc; default (no param) returns only latest
  - [✅] 4.3 Write approval tests — assert `end_user` gets 403; assert `content_admin` succeeds; assert `approved=true` in DB

### [✅] 5 Implement Questionnaire Completion with Confidence Scoring
Auto-populate questionnaire items extracted from the RFP with typed answers and confidence scores; flag low-confidence responses for human review.

  - [✅] 5.1 Implement `QuestionnaireCompletionAgent.complete(item: QuestionnaireItem, context_chunks) -> CompletedItem` — generate typed answers per `question_type`: yes/no (boolean), multiple_choice (one of `options`), numeric (float), text (string); use retrieved content as context
  - [✅] 5.2 Implement confidence scoring with model-agnostic fallback: for yes_no and multiple_choice, if model returns logprobs use max softmax probability; otherwise use retrieval-based proxy (mean cosine score of top-3 retrieved chunks × answer keyword overlap ratio); for text/numeric, confidence = mean chunk retrieval score; if confidence < 0.7, set `flagged=true`
  - [✅] 5.3 Implement `POST /rfps/{id}/questionnaire/complete` — run `QuestionnaireCompletionAgent` for all unfilled `questionnaire_items` for the RFP; return `{completed: int, flagged: int}`
  - [✅] 5.4 Write `tests/test_questionnaire.py` — seed questionnaire items; run completion; assert all items have answers; assert items with low-confidence scores are flagged

### [✅] 6 Implement Response Strategy Control Layer
Implement Minimal/Balanced/Detailed response modes and adaptive disclosure for partial compliance as described in spec_additional §8.

  - [✅] 6.1 Extend `build_user_prompt` in `services/orchestrator/prompts.py` to accept `detail_level: Literal["minimal","balanced","detailed"]`; add mode-specific instructions: minimal = concise bullet-point answer, balanced = structured paragraph with citations, detailed = full technical narrative
  - [✅] 6.2 Implement adaptive disclosure: if mean cosine similarity of retrieved chunks < 0.4 OR fewer than 2 chunks retrieved, prepend a disclosure note ("The following answer is based on partial information: …") and set `partial_compliance=true` in the response
  - [✅] 6.3 Persist `detail_level` on `rfp_answers.detail_level` and `partial_compliance BOOL` on `rfp_answers`; expose `detail_level` as a parameter on `POST /ask` and `POST /rfps/{id}/questions/{qid}/generate`
  - [✅] 6.4 Write `tests/test_response_strategy.py` — assert minimal/balanced/detailed prompts differ in instruction content; assert partial_compliance flag set when context coverage is below threshold


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
