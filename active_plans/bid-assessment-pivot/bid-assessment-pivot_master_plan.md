# Master Plan — Bid Assessment Pivot

**Slug:** `bid-assessment-pivot`
**Status:** 🔄 In Progress
**Spec:** `active_plans/bid-assessment-pivot/bid-assessment-pivot_spec.md`
**Canonical Spec:** `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md`
**Last Updated:** 2026-05-13

---

## Executive Summary

Reposition the existing RFP Assistant — currently centred on retrieving permission-scoped content and drafting answers — into a **Bid Assessment** product whose primary value is an automated, AI-driven **bid/no-bid decision** for each incoming RFP. Answer drafting becomes a downstream stage gated by an explicit bid decision.

The first deployment is branded for **Akkodis**, an IT engineering & services firm. The codebase must stay generic so the same product can be re-branded and re-seeded for other customers without code changes.

Delivered across seven mergeable phases, each with its own migration set, tests, and demo affordance. Phase 0 is the only structural change to existing data; phases 1–6 are additive on top of it.

---

## Detailed Objective

### Goals

Introduce a six-stage RFP workflow — `Upload → Extract → Assess → Bid/No-Bid → Draft → Review` — where the Assess stage produces a structured artifact suitable for a bid-committee review:

- **Compliance items** — clause-by-clause pass/fail/partial/unknown against the tenant's capability profile and approved knowledge base.
- **Eligibility checks** — upfront bid-killers (geography, contract vehicle, certifications, financial thresholds, exclusions).
- **Risk register** — five-category register (commercial, delivery, legal, technical, reputational) with severity + likelihood + mitigation.
- **Capability matches** — requirement-to-offering matrix with match score and gap notes.
- **Roll-up** — fit_score, win_probability, AI verdict (`BID` / `NO-BID` / `REVIEW`), 1-page natural-language summary.
- **Human bid decision** — recorded separately from the AI verdict; gates the Draft stage in the UI.
- **Exportable branded report** — PDF + DOCX using tenant branding.

A real multi-tenant model is added (a `tenants` table with `tenant_id` on every relevant row) so branding, capability data, and assessments isolate cleanly. Tenant branding is data-driven (logo, colours, report header/footer), set per row, applied without code changes.

A new **capability profile** modelled in eight dimensions captures what a tenant can deliver: service lines, industries, geographies, certifications, contract vehicles, partnerships, rate cards, engagement sizes, and the legacy `products` table. The Bid Assessment Pipeline reads this profile to drive eligibility and best-fit analysis.

A **snippet library** of curated boilerplate corporate responses is introduced, retrieval-boosted by category and topic-tag, surfaced as evidence under compliance items and as one-click inserts during draft.

### Constraints & assumptions

- Service count stays at 11. `portfolio-service` is renamed to `capability-service` in-place; no new service is introduced.
- Synchronous, SSE-streamed pipeline execution; no background queue layer in v1.
- Single shared Postgres schema with `tenant_id` filter — per-tenant schemas deferred.
- Existing RBAC, hybrid retrieval (pgvector + tsvector + RRF k=60), win/loss scoring, and audit-log discipline are preserved.
- Onboarding a new customer must remain a config-and-seed operation, never a code change.

### Definition of success

- Akkodis seed runs end-to-end on Docker Compose: upload an RFP → see extracted requirements → run assessment → see scorecard → record bid decision → draft an answer → export a branded PDF.
- `seed_tenant.py <new-slug>` produces a working second tenant with no code changes.
- The tenancy-leak integration test passes: no row from one tenant ever appears in another tenant's queries.
- All seven phases pass `./how_to/maistro plan-verify` and code review.

---

## Quick Navigation

| Phase | Focus | Status | File |
|---|---|---|---|
| 0 | Foundation: tenants & rename | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_0_foundation.md` |
| 1 | Capability profile | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_1_capability_profile.md` |
| 2 | Knowledge-base extensions | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_2_knowledge_base.md` |
| 3 | Bid Assessment core | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_3_bid_assessment.md` |
| 4 | Frontend timeline | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_4_frontend_timeline.md` |
| 5 | Report export | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_5_report_export.md` |
| 6 | Branding & docs | 🔄 | `active_plans/bid-assessment-pivot/phases/phase_6_branding_docs.md` |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (3000)                                             │
│  RFP Workspace timeline:                                     │
│     Upload → Extract → Assess → Bid/No-Bid → Draft → Review  │
└──────────────────────────┬──────────────────────────────────┘
                           │ JWT
┌──────────────────────────▼──────────────────────────────────┐
│  api-gateway (8000)  — auth, rate-limit, proxy               │
└──────────────────────────┬──────────────────────────────────┘
        ┌──────────────────┼─────────────────────────┐
        │                  │                         │
┌───────▼───────┐  ┌───────▼───────┐  ┌──────────────▼─────────────┐
│ orchestrator  │  │  rfp-service  │  │  content-service           │
│  AnswerPipe + │  │  RFP + Assess │  │  ingest, chunk, embed,     │
│  BidAssess    │  │  CRUD, export │  │  category enum, snippets   │
└──────┬────────┘  └───────────────┘  └────────────────────────────┘
       │
  ┌────┴──────────────────────────────┐
  │                                   │
┌─▼─────────────────┐    ┌────────────▼────────────────────────┐
│ retrieval-service │    │  capability-service  (renamed)       │
│ + tenant_id +     │    │  service_lines / industries /        │
│ category boosts   │    │  geographies / certifications /      │
└───────────────────┘    │  contract_vehicles / partnerships /  │
                         │  rate_cards / engagement_sizes /     │
                         │  products                            │
                         └──────────────────────────────────────┘

(rbac, audit, analytics, model-router unchanged)
```

Full architecture and data model live in the spec referenced above; this section gives the navigation-level overview.

---

## Current State

- **Services:** 11 services on Docker Compose (`api-gateway`, `orchestrator`, `retrieval-service`, `content-service`, `rbac-service`, `rfp-service`, `model-router`, `adapters`, `audit-service`, `analytics-service`, `portfolio-service`).
- **Pipeline:** `orchestrator` runs `AgentPipeline` with `IngestionAgent → ExtractionAgent → GenerationAgent → QuestionnaireAgent` for answer drafting; no bid-assessment workflow.
- **Tenancy:** `users.tenant_config JSONB` exists but no `tenants` table — capability data cannot be keyed to a tenant.
- **Capability data:** `products` table is product-centric (vendor, category, features); no model for services/certifications/geographies/etc.
- **Documents:** `documents` table has `status` and `metadata JSONB` but no category enum; all docs participate in retrieval the same way (subject to RBAC).
- **Snippets:** No corporate boilerplate library; every answer must be RAG-generated.
- **Frontend:** `RFPWorkspace.tsx` is a Q&A page jumping straight to answer drafting; no notion of stages.
- **Branding:** Hard-coded display strings; no per-tenant brand.
- **Migrations:** Alembic at revision 0008 (`companies`).

---

## Desired State

- **Services:** 11 services. `portfolio-service` renamed to `capability-service` (port unchanged at 8010), scope broadened to host the full capability profile.
- **Pipeline:** Existing `AgentPipeline` retained for drafting; new `BidAssessmentPipeline` runs `ComplianceAgent + EligibilityAgent + BestFitAgent` in parallel, then `RiskAgent`, then `ExecSummaryAgent`.
- **Tenancy:** `tenants` table exists; every relevant row carries `tenant_id`; queries filter by it; `common/tenancy.py` helper enforces the discipline.
- **Capability data:** 7 capability tables + 2 M2M tables alongside the existing `products` table; embeddings on `service_lines`.
- **Documents:** `documents.category` enum + per-category metadata JSONB convention. Snippets are special documents with their own façade endpoints.
- **Snippets:** Curated boilerplate library, retrieval-boosted by category and topic tag, surfaced as evidence in compliance items.
- **Frontend:** Six-stage timeline in the RFP workspace, with locked/unlocked states driven by server data. New admin pages for capabilities, snippets, and branding.
- **Branding:** Per-tenant `brand JSONB` (logo, colours, report header/footer) applied via CSS variables and Jinja2 export templates.
- **Migrations:** Alembic at revision 0013 with the new tables; `upgrade head → downgrade base → upgrade head` exercised in CI.

---

## Global Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Tenancy leak — a query forgets to filter by `tenant_id` | Customer data crosses tenants — security/compliance breach | `common/tenancy.py` helper + integration test creating two tenants and asserting no cross-tenant rows ever surface |
| `portfolio-service` → `capability-service` rename misses a caller / env var | Service-to-service calls fail silently or with cryptic errors | Single sweep across `docker-compose.yml`, `Dockerfile`s, all `os.environ.get`/`getenv` references, README, and tests in Phase 0; integration smoke test after rename |
| Phase 0 backfill migration is unrecoverable | Stuck migration state on a real deployment | Split into two alembic files (0009 nullable+backfill, 0010 NOT NULL+FK); test `downgrade base → upgrade head` end-to-end |
| Assessment pipeline takes too long synchronously | Users wait minutes for a single RFP assessment; SSE timeouts | Bounded scope (only requirements + capability profile + small KB); document Phase-2 queue migration path; budget per-agent token usage |
| Snippet library bloats retrieval and crowds out generic chunks | Generic RAG quality degrades | Category boost is a tenant-config knob; tenancy-leak test also asserts retrieval rank stability across runs |
| RFPWorkspace refactor (extraction of Draft/Review stages) drops existing behaviour | Existing answer-drafting flow regresses | Phase 4 ships only after the timeline frame is in place; existing components are moved, not rewritten; existing Q&A tests rerun |
| Akkodis seed grows tightly coupled to code, breaking the "generic" promise | Future tenant onboarding requires code changes | Phase 6 explicitly tests onboarding a fixture `widgetco` tenant via `seed_tenant.py` only |

---

## Global Acceptance Gates

- [ ] Gate 1: `./how_to/maistro plan-verify` returns zero errors on master + all phase files.
- [ ] Gate 2: All seven phases pass Codex code review with zero blockers.
- [ ] Gate 3: `docker compose up -d --build` produces a healthy stack with the renamed `capability-service`.
- [ ] Gate 4: `seed_tenant.py akkodis` is idempotent (re-running produces zero changes).
- [ ] Gate 5: Tenancy-leak integration test passes (two-tenant fixture, zero cross-tenant rows).
- [ ] Gate 6: Migration round-trip test passes (`upgrade head → downgrade base → upgrade head` is clean).
- [ ] Gate 7: End-to-end demo: upload an RFP → run assessment → record decision → draft an answer → export branded PDF — all from the Akkodis-branded UI.
- [ ] Gate 8: `seed_tenant.py widgetco` (using `seeds/_example/`) produces a working second tenant without any code changes.

---

## Dependency Gates

- [ ] Dependency 1: Phase 0 merged (tenancy + rename) before any other phase begins.
- [ ] Dependency 2: Phase 1 merged (capability tables) before Phase 3 (BestFit/Eligibility agents need them).
- [ ] Dependency 3: Phase 2 merged (snippet library + category boost) before Phase 3 (ComplianceAgent needs snippet retrieval).
- [ ] Dependency 4: Phase 3 merged (assessment pipeline + endpoints) before Phase 4 (frontend consumes them).
- [ ] Dependency 5: Phase 4 merged (timeline frame) before Phase 5 (export dialog lives inside the scorecard).
- [ ] Dependency 6: Phase 5 merged (export templates) before Phase 6 (branding admin tests the export pipeline).

---

## Phases Overview

### Phase 0: Foundation — Tenants & Service Rename — `active_plans/bid-assessment-pivot/phases/phase_0_foundation.md`
#### Tasks
### [ ] 1 Create tenants table and backfill migration
  - [ ] 1.1 Sweep `migrations/versions/` to enumerate every table that should be tenant-scoped
  - [ ] 1.2 Write `0009_tenants_table_and_backfill.py` creating `tenants(id, slug UNIQUE, display_name, brand JSONB, config JSONB, created_at)`
  - [ ] 1.3 Insert the seed Akkodis tenant row in the same migration (UUID stable via deterministic seed)
  - [ ] 1.4 Add nullable `tenant_id UUID` columns to: `users`, `documents`, `products`, `rfps`, `rfp_questions`, `rfp_answers`, `audit_logs`, `win_loss_records`, `companies`, `analytics_events` (plus any others found in 1.1)
  - [ ] 1.5 Backfill all existing rows in each of those tables to the Akkodis tenant
  - [ ] 1.6 Run `alembic upgrade head` against the existing seeded database and verify no rows are left NULL
### [ ] 2 Lock down tenant_id with NOT NULL, FK, and indexes
  - [ ] 2.1 Write `0010_tenants_not_null_and_fks.py` opening with an explicit `SELECT COUNT(*) WHERE tenant_id IS NULL` check that raises on any non-zero count
  - [ ] 2.2 `ALTER COLUMN tenant_id SET NOT NULL` on every column added in 1.4
  - [ ] 2.3 Add FK from each `tenant_id` to `tenants.id`
  - [ ] 2.4 Create indexes on `(tenant_id)` on hot tables (`documents`, `rfps`, `audit_logs`, `chunks`)
  - [ ] 2.5 Provide a working `downgrade()` that drops FKs, drops indexes, sets columns NULLable, drops the `tenants` table
### [ ] 3 Add common/tenancy.py helper
  - [ ] 3.1 Implement `tenant_scope` in `common/tenancy.py`
  - [ ] 3.2 Add a docstring documenting the effective-config merge order (`tenants.config` ← `users.tenant_config`)
  - [ ] 3.3 Add a unit test in `common/tests/test_tenancy.py` covering the helper
### [ ] 4 Rename portfolio-service to capability-service
  - [ ] 4.1 `git mv services/portfolio-service services/capability-service`
  - [ ] 4.2 Update `services/capability-service/pyproject.toml` `name` field
  - [ ] 4.3 Update `services/capability-service/Dockerfile` (no path changes, just sanity-check)
  - [ ] 4.4 In `docker-compose.yml`, rename the service block, update `dockerfile:` path, rename env var to `CAPABILITY_SERVICE_URL`
  - [ ] 4.5 In every caller (grep `PORTFOLIO_SERVICE_URL` and `portfolio-service` across `services/` and `scripts/`), rename env var and service name
  - [ ] 4.6 Update `services/api-gateway/main.py` proxy route prefix from `/portfolio` to `/capabilities` (matches Phase-1 spec)
  - [ ] 4.7 Sweep `README.md`, `spec.md`, and any docs under `docs/` for `portfolio-service` references
  - [ ] 4.8 Run `docker compose build capability-service` to confirm the rename builds clean
  - [ ] 4.9 Run `docker compose up -d` and verify all 11 services report healthy
### [ ] 5 Implement seed_tenant.py and refactor seed_demo
  - [ ] 5.1 Create `scripts/seed_tenant.py` accepting a slug, reading `scripts/seeds/<slug>/tenant.yaml`, upserting the `tenants` row
  - [ ] 5.2 Create `scripts/seeds/akkodis/tenant.yaml` with slug, display_name, brand defaults (primary_color, accent_color placeholders), empty config
  - [ ] 5.3 Refactor `scripts/seed_demo.py` to call `seed_tenant("akkodis")` before any existing seed work
  - [ ] 5.4 Existing seed inserts (users, products, documents, RFPs) gain `tenant_id` references to the Akkodis tenant
  - [ ] 5.5 Verify idempotency — run the seed twice, confirm no duplicates
### [ ] 6 Attach tenant_id to request state at the gateway
  - [ ] 6.1 In `auth.py`, after JWT decode, load `users.tenant_id` via the existing async session
  - [ ] 6.2 Attach `tenant_id` to `request.state`
  - [ ] 6.3 In `services/api-gateway/proxy.py` (or main.py), forward `tenant_id` to downstream services as an `X-Tenant-Id` header
  - [ ] 6.4 Add a unit test verifying the header is propagated
### [ ] 7 Add tenancy-leak integration test
  - [ ] 7.1 Add `tests/integration/test_tenancy_leak.py` with a fixture that creates `akkodis` and `widgetco` tenants
  - [ ] 7.2 Seed one user and one document per tenant
  - [ ] 7.3 Assert `GET /documents` as a `widgetco` user returns zero `akkodis` rows
  - [ ] 7.4 Assert `GET /users` (admin) is correctly scoped
  - [ ] 7.5 Wire the test into `scripts/test_workflows.py`
### [ ] 8 Add migration round-trip test
  - [ ] 8.1 Extend `scripts/test_workflows.py` with a `test_migration_roundtrip` step
  - [ ] 8.2 Use a disposable database (`rfpassistant_test_migrate` or similar)
  - [ ] 8.3 Run the three steps and assert non-zero exit on any failure

### Phase 1: Capability Profile — `active_plans/bid-assessment-pivot/phases/phase_1_capability_profile.md`
#### Tasks
### [ ] 1 Create capability profile migration
  - [ ] 1.1 Write `service_lines(id, tenant_id, name, description, parent_id NULLABLE, embedding VECTOR(384), created_at)`
  - [ ] 1.2 Write `industries(id, tenant_id, name, created_at)`
  - [ ] 1.3 Write `geographies(id, tenant_id, name, type ENUM, parent_id NULLABLE, created_at)`
  - [ ] 1.4 Write `certifications(id, tenant_id, name, issuing_body, scope, expires_at, evidence_doc_id NULLABLE, created_at)`
  - [ ] 1.5 Write `contract_vehicles(id, tenant_id, name, jurisdiction, expires_at, created_at)`
  - [ ] 1.6 Write `partnerships(id, tenant_id, partner_name, tier, scope, created_at)`
  - [ ] 1.7 Write `rate_cards(id, tenant_id, role, region, currency, hourly_rate, daily_rate, effective_from, effective_until, created_at)`
  - [ ] 1.8 Write `engagement_sizes(id, tenant_id, label, min_value, max_value, currency, created_at)`
  - [ ] 1.9 Write `service_line_industries(service_line_id, industry_id)` and `service_line_geographies(service_line_id, geography_id)` with composite PKs
  - [ ] 1.10 Provide a working `downgrade()` that drops everything in reverse order
### [ ] 2 Implement capability-service CRUD endpoints
  - [ ] 2.1 Implement `service_lines.py`: GET list, POST, GET one, PATCH, DELETE; hierarchy cycle check on POST/PATCH
  - [ ] 2.2 Implement `industries.py`, `geographies.py`, `certifications.py` with the same shape
  - [ ] 2.3 Implement `contract_vehicles.py`, `partnerships.py`, `rate_cards.py`, `engagement_sizes.py`
  - [ ] 2.4 Implement `profile.py` rollup returning `{service_lines, industries, geographies, certifications, contract_vehicles, partnerships, rate_cards, engagement_sizes}` for the request's tenant
  - [ ] 2.5 Wire all routes into `main.py` with role checks (`content_admin`+ for writes, any for reads)
  - [ ] 2.6 Every query uses `common/tenancy.py:tenant_scope()`
### [ ] 3 Add synchronous embedding for service_lines
  - [ ] 3.1 Create `services/capability-service/embeddings.py` exporting `embed_service_line(text) -> list[float]`
  - [ ] 3.2 Reuse the singleton embedder pattern from `content-service`
  - [ ] 3.3 In `service_lines.py` POST/PATCH handlers, invoke `embed_service_line(description)` and persist
  - [ ] 3.4 Add a unit test asserting non-null `embedding` after create
### [ ] 4 Expand Akkodis YAML seed for capability profile
  - [ ] 4.1 `service_lines.yaml`: Cloud, Cybersecurity, Data & AI, App Dev, IT Staffing, Advisory, Managed Services (with descriptions)
  - [ ] 4.2 `industries.yaml`: Financial Services, Healthcare, Public Sector, Manufacturing, Energy, Retail, Telecom
  - [ ] 4.3 `geographies.yaml`: country/region rows for FR, DE, UK, US, CA, IT, ES (with EMEA and AMER parents)
  - [ ] 4.4 `certifications.yaml`: ISO 27001, SOC 2 Type II, GDPR, HIPAA-ready, with realistic dates
  - [ ] 4.5 `contract_vehicles.yaml`: at least one EU framework, one US schedule
  - [ ] 4.6 `partnerships.yaml`: AWS Premier, Microsoft Gold, ServiceNow Elite (placeholder tiers)
  - [ ] 4.7 `rate_cards.yaml`: 3–5 roles per region with hourly/daily rates
  - [ ] 4.8 `engagement_sizes.yaml`: Small (<$500k), Medium ($500k–$2M), Large ($2M–$10M), Mega (>$10M)
  - [ ] 4.9 Extend `seed_tenant.py` to load all 8 dimensions in dependency order
### [ ] 5 Build capability admin page (frontend)
  - [ ] 5.1 Create `frontend/components/capability/CapabilityDimensionTable.tsx` — generic over a dimension's columns
  - [ ] 5.2 Create `frontend/components/capability/CapabilityProfileAdmin.tsx` — tab bar + active tab content
  - [ ] 5.3 Create `frontend/app/(admin)/admin/capabilities/page.tsx` mounting the component
  - [ ] 5.4 Hook into `/capabilities/profile` for initial load (single fetch, 8 tabs from one payload)
  - [ ] 5.5 Wire add/edit/delete flows through `frontend/lib/api.ts`
  - [ ] 5.6 Add the page to the admin nav in `frontend/components/AppShell.tsx`
### [ ] 6 Extend tenancy-leak test
  - [ ] 6.1 In `tests/integration/test_tenancy_leak.py`, seed `widgetco` with one row in each capability dimension
  - [ ] 6.2 Assert that a `widgetco` user's `GET /capabilities/profile` excludes all Akkodis rows
  - [ ] 6.3 Assert similar isolation on direct dimension endpoints

### Phase 2: Knowledge-Base Extensions — `active_plans/bid-assessment-pivot/phases/phase_2_knowledge_base.md`
#### Tasks
### [ ] 1 Add documents.category migration
  - [ ] 1.1 Write `0012_documents_category.py`
  - [ ] 1.2 `ALTER TABLE documents ADD COLUMN category VARCHAR NOT NULL DEFAULT 'general'`
  - [ ] 1.3 No backfill needed for existing rows — default applies; verify all rows have a value
  - [ ] 1.4 Add an index on `(tenant_id, category)`
  - [ ] 1.5 Provide a working `downgrade()` dropping the column and index
### [ ] 2 Implement snippet façade endpoints
  - [ ] 2.1 `POST /snippets` — body `{title, body, topic_tags[]}`; creates document with category + metadata
  - [ ] 2.2 Auto-approve when caller has `content_admin`/`system_admin` role
  - [ ] 2.3 `GET /snippets?topic=...&q=...` — filter by topic_tag intersection + free-text on body
  - [ ] 2.4 `PATCH /snippets/{id}` — increment `metadata.version`, rewrite body, reset to `pending_approval`
  - [ ] 2.5 `DELETE /snippets/{id}` — soft-delete (status='archived')
  - [ ] 2.6 Body length validation: reject >256 tokens (MiniLM max) with 422
  - [ ] 2.7 Wire routes through `api-gateway` proxy
### [ ] 3 Add chunker branch for snippets
  - [ ] 3.1 Add the conditional branch in `chunk_document()`
  - [ ] 3.2 Single-chunk: `position=0`, full body, no overlap
  - [ ] 3.3 Unit test: a snippet with multi-paragraph body produces exactly one chunk
### [ ] 4 Implement category-weighted RRF in retrieval
  - [ ] 4.1 Read `tenants.config.retrieval.category_boosts` once per request
  - [ ] 4.2 After RRF fusion, add `category_boost[chunk.document.category]` to each result
  - [ ] 4.3 If `chunk.document.category == 'boilerplate_snippet'` AND any of its `topic_tags` intersects the query's classified tags, add +0.10
  - [ ] 4.4 Add tenant_id filter to all retrieval queries (calls `common/tenancy.py:tenant_scope`)
  - [ ] 4.5 Unit test: a snippet with matching tag outranks a generic chunk with similar text
### [ ] 5 Add tag classification to ExtractionAgent
  - [ ] 5.1 In `services/orchestrator/agents.py:ExtractionAgent`, fetch the tenant's snippet topic_tags via `content-service`
  - [ ] 5.2 Update the extraction prompt in `prompts.py` to instruct the LLM to assign 0+ tags per requirement from the provided vocabulary
  - [ ] 5.3 Update the Pydantic `Requirement` schema to include `tags: list[str]`
  - [ ] 5.4 Persist `tags` in `rfp_requirements.tags TEXT[]` (add a migration column inline with 0012 or as 0012b)
  - [ ] 5.5 Integration test: extract an RFP that mentions GDPR; assert the matching requirement has `["gdpr"]` in its tags
### [ ] 6 Build snippet admin page (frontend)
  - [ ] 6.1 Create `frontend/components/snippets/SnippetLibraryAdmin.tsx` with a search box, tag filter, and list
  - [ ] 6.2 Modal for create/edit with title, body (multi-line), tags (chip input)
  - [ ] 6.3 Archive action with confirmation
  - [ ] 6.4 Create `frontend/app/(admin)/admin/snippets/page.tsx` mounting the component
  - [ ] 6.5 Wire `frontend/lib/api.ts` snippet functions
  - [ ] 6.6 Add the page to admin nav in `AppShell.tsx`
### [ ] 7 Seed Akkodis snippets
  - [ ] 7.1 `scripts/seeds/akkodis/snippets/gdpr.md` — GDPR statement, tags `[gdpr, data_residency, privacy]`
  - [ ] 7.2 `scripts/seeds/akkodis/snippets/soc2.md` — SOC 2 attestation, tags `[soc2, security, compliance]`
  - [ ] 7.3 `scripts/seeds/akkodis/snippets/sla_defaults.md` — SLA defaults, tags `[sla, availability, support]`
  - [ ] 7.4 Extend `seed_tenant.py` to glob `snippets/*.md`, parse front-matter, call `POST /snippets`
  - [ ] 7.5 Verify seed is idempotent — re-running doesn't duplicate

### Phase 3: Bid Assessment Core — `active_plans/bid-assessment-pivot/phases/phase_3_bid_assessment.md`
#### Tasks
### [ ] 1 Create bid assessment migration
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
  - [ ] 2.1 `Citation`, `ComplianceItem`, `EligibilityCheck`, `Risk`, `CapabilityMatch` in `bid_assessment_schemas.py`
  - [ ] 2.2 `ComplianceAgentInput/Output`, `EligibilityAgentInput/Output`, `BestFitAgentInput/Output`, `RiskAgentInput/Output`, `ExecSummaryAgentInput/Output`
  - [ ] 2.3 Unit tests asserting schema validation rejects malformed input
### [ ] 3 Implement the 5 agents
  - [ ] 3.1 `ComplianceAgent` — for each requirement, retrieve evidence (calls retrieval-service with tenant_id + category boosts + tag boost), produce a ComplianceItem; mark status by evidence strength
  - [ ] 3.2 `EligibilityAgent` — fetches tenant capability profile rollup, classifies bid-killers (geography / contract vehicle / certs / financial / exclusions), produces EligibilityCheck rows
  - [ ] 3.3 `BestFitAgent` — embeds each requirement, matches against service_lines + products embeddings (top-k cosine), produces CapabilityMatch rows with gap_notes when no offering matches
  - [ ] 3.4 `RiskAgent` — given the three parallel outputs + raw RFP text, prompts the LLM to produce a Risk list across 5 categories
  - [ ] 3.5 `ExecSummaryAgent` — reads all prior outputs + analytics score_boosts + tenant verdict_thresholds, produces `{summary, fit_score, win_probability, verdict}`
  - [ ] 3.6 Per-agent prompts in `bid_assessment_prompts.py`
  - [ ] 3.7 Unit tests per agent with stub LLM client
### [ ] 4 Build BidAssessmentPipeline orchestrator class
  - [ ] 4.1 `BidAssessmentPipeline.run(rfp_id, tenant_id, user_id)` async generator yielding SSE events
  - [ ] 4.2 Pre-flight: ensure capability profile has at least service_lines + certifications; 422 if not
  - [ ] 4.3 Insert a fresh `bid_assessments` row with `status='running'`, `version=previous+1`
  - [ ] 4.4 Parallel stage: `asyncio.gather(compliance, eligibility, bestfit, return_exceptions=True)`; persist surviving outputs; set `status='partial'` if any failed
  - [ ] 4.5 Sequential: Risk receives all (possibly partial) outputs; ExecSummary receives all
  - [ ] 4.6 Validate citations against real chunk IDs before persisting; drop invalid citations and add `audit_logs` warning
  - [ ] 4.7 On final completion, update `bid_assessments.status='complete'` (or `partial`/`failed`)
  - [ ] 4.8 Emit SSE events at each transition
### [ ] 5 Implement assessment endpoints in rfp-service
  - [ ] 5.1 `POST /rfps/{id}/assess` — kicks off the pipeline (background task), returns 200 with `{assessment_id, status:"running"}`
  - [ ] 5.2 `GET /rfps/{id}/assess?stream=true` — SSE; 404 if no `status=running` row exists for the RFP
  - [ ] 5.3 `GET /rfps/{id}/assessments` — list with pagination
  - [ ] 5.4 `GET /rfps/{id}/assessments/latest` — convenience
  - [ ] 5.5 `GET /rfps/{id}/assessments/{aid}` — full assessment with embedded children
  - [ ] 5.6 `PATCH /rfps/{id}/assessments/{aid}/compliance/{cid}` — content_admin+; requires `If-Match`
  - [ ] 5.7 `PATCH /rfps/{id}/assessments/{aid}/risks/{rid}`, `POST` to add, `DELETE` to remove — end_user+; requires `If-Match`
  - [ ] 5.8 All routes scoped by `common/tenancy.py:tenant_scope`
### [ ] 6 Implement bid decision endpoints
  - [ ] 6.1 `POST /rfps/{id}/bid-decision` — body `{decision, rationale, conditions[]}`; persists row
  - [ ] 6.2 `GET /rfps/{id}/bid-decision` — returns latest
  - [ ] 6.3 No version constraint on multiple decisions — each POST creates a new row; latest wins for gate purposes
### [ ] 7 Wire api-gateway proxies
  - [ ] 7.1 Add route prefixes `/rfps/{id}/assess*`, `/rfps/{id}/assessments*`, `/rfps/{id}/bid-decision` proxied to `rfp-service`
  - [ ] 7.2 SSE proxy uses streaming response (no buffering)
  - [ ] 7.3 Role checks enforced at gateway (matches role table in spec §6.4)
### [ ] 8 Pipeline integration tests (stub agents)
  - [ ] 8.1 `test_bid_assessment_pipeline.py`: stub all 5 agents to return canned outputs
  - [ ] 8.2 Assert pipeline persists correct rows in correct order
  - [ ] 8.3 Test parallel failure case (one of the three raises)
  - [ ] 8.4 Test sequential failure case (Risk raises)
  - [ ] 8.5 Test optimistic-lock 409 on child PATCH with stale version
### [ ] 9 End-to-end LLM-gated test
  - [ ] 9.1 `test_bid_assessment_e2e.py`: seed Akkodis tenant + one RFP; trigger assessment; assert resulting assessment has non-empty children
  - [ ] 9.2 Sanity-check: fit_score and win_probability are in [0, 1]
  - [ ] 9.3 Sanity-check: verdict is one of `bid`, `no_bid`, `review`
  - [ ] 9.4 Sanity-check: every citation references a real chunk_id

### Phase 4: Frontend Timeline & Scorecard — `active_plans/bid-assessment-pivot/phases/phase_4_frontend_timeline.md`
#### Tasks
### [ ] 1 Extract Draft and Review stages from RFPWorkspace
  - [ ] 1.1 Read current `RFPWorkspace.tsx`; identify Q&A vs approval responsibilities
  - [ ] 1.2 Create `frontend/components/rfp/DraftStage.tsx` containing the AnswerPane / ChatBox / CitationsPanel / ModeSelector composition
  - [ ] 1.3 Create `frontend/components/rfp/ReviewStage.tsx` containing the approval flow
  - [ ] 1.4 Rerun existing Q&A tests against the new mount point; fix paths/imports until green
  - [ ] 1.5 Ensure no behavioural change visible to a logged-in user mid-flow
### [ ] 2 Reshape RFPWorkspace as stage container
  - [ ] 2.1 Fetch on mount: `/rfps/{id}`, `/rfps/{id}/assessments/latest`, `/rfps/{id}/bid-decision`
  - [ ] 2.2 Compute timeline state from the fetched data
  - [ ] 2.3 Render `<RFPTimeline />` left rail + active stage component right pane
  - [ ] 2.4 Manage the SSE connection lifecycle when the user is on the Assess stage
  - [ ] 2.5 Pass refresh callbacks downstream so stages can request a state re-fetch
### [ ] 3 Build RFPTimeline component
  - [ ] 3.1 Six stage labels with status indicators (`✓ done`, `◉ active`, `○ unlocked`, `─ locked`)
  - [ ] 3.2 Locked stages render greyed-out with "Complete <previous> to unlock" tooltip
  - [ ] 3.3 Active stage highlighted; clicking switches active stage if allowed
  - [ ] 3.4 Accessible: ARIA labels per step; tab-navigable
### [ ] 4 Build AssessmentScorecard and sub-components
  - [ ] 4.1 `AssessmentScorecard.tsx` — owns the SSE connection via `useAssessmentStream`
  - [ ] 4.2 `ScoreRollupHeader.tsx` — shows fit_score, win_probability, AI verdict, human decision (when present)
  - [ ] 4.3 `ComplianceGrid.tsx` — sortable grid: requirement | status | evidence | citations | "edit" (content_admin+)
  - [ ] 4.4 `EligibilityPanel.tsx` — big visual pass/fail per check at top of scorecard
  - [ ] 4.5 `RiskRegister.tsx` — editable table; add / edit / delete with confirmation
  - [ ] 4.6 `CoverageMatrix.tsx` — heat-map (requirements rows × offerings columns), virtualised past 50×20
  - [ ] 4.7 `ExecSummaryCard.tsx` — rendered markdown of summary; "regenerate" button (calls `POST /rfps/{id}/assess` for new version)
  - [ ] 4.8 `AssessmentHistoryMenu.tsx` — dropdown listing past versions, selecting one loads it
### [ ] 5 Build BidDecisionForm
  - [ ] 5.1 Verdict radio: `BID`, `NO-BID`, `REVIEW`
  - [ ] 5.2 Rationale textarea (required)
  - [ ] 5.3 Conditions list (dynamic add/remove)
  - [ ] 5.4 Submit calls `POST /rfps/{id}/bid-decision`; on success, triggers RFPWorkspace state refresh (which unlocks Draft)
### [ ] 6 Implement useAssessmentStream hook
  - [ ] 6.1 `frontend/lib/useAssessmentStream.ts` opens `EventSource` on `/rfps/{rfpId}/assess?stream=true`
  - [ ] 6.2 Maintains state `{progress, currentAgent, error, isComplete, assessment}`
  - [ ] 6.3 On `pipeline_complete`, fetches `/rfps/{id}/assessments/latest` for authoritative state
  - [ ] 6.4 Auto-reconnect once on transient error; surface persistent error to caller
  - [ ] 6.5 Closes on unmount; cleans up the EventSource
  - [ ] 6.6 Unit test using a mock EventSource
### [ ] 7 Add API client functions
  - [ ] 7.1 `startAssessment(rfpId)`, `getAssessment(rfpId, assessmentId)`, `getLatestAssessment(rfpId)`, `listAssessments(rfpId)`
  - [ ] 7.2 `patchComplianceItem`, `patchRisk`, `addRisk`, `deleteRisk` — with `If-Match` header support
  - [ ] 7.3 `postBidDecision(rfpId, body)`, `getBidDecision(rfpId)`
  - [ ] 7.4 Snippet client functions (if not already added in Phase 2)
  - [ ] 7.5 All functions reuse the existing fetch helper with JWT injection
### [ ] 8 Component tests
  - [ ] 8.1 `useAssessmentStream` — mock EventSource, exercise progress/error/complete paths
  - [ ] 8.2 `RFPTimeline` — render fixture states (all-locked, mid-flow, all-done)
  - [ ] 8.3 `ComplianceGrid` — empty / partial / full fixture data
  - [ ] 8.4 `BidDecisionForm` — submit validation, error path, success path
  - [ ] 8.5 `RiskRegister` — add/edit/delete with optimistic-lock 409 handling

### Phase 5: Report Export — `active_plans/bid-assessment-pivot/phases/phase_5_report_export.md`
#### Tasks
### [ ] 1 Add export-renderer dependencies
  - [ ] 1.1 Add `weasyprint`, `python-docx-template`, `pillow`, `jinja2` to `services/rfp-service/pyproject.toml`
  - [ ] 1.2 Update `services/rfp-service/Dockerfile` with required system packages (`libcairo2`, `libpango1.0-0`, `libgdk-pixbuf-2.0-0`)
  - [ ] 1.3 `docker compose build rfp-service` and verify the image is healthy
  - [ ] 1.4 Document the system-dep impact in `README.md` (size note)
### [ ] 2 Implement StorageBackend abstraction
  - [ ] 2.1 Define `StorageBackend` Protocol in `services/rfp-service/exports/storage.py`: `put(tenant_slug, filename, content) -> file_path`, `get(file_path) -> bytes`, `exists(file_path) -> bool`
  - [ ] 2.2 Implement `LocalFilesystemBackend(root='/var/exports')`
  - [ ] 2.3 Add `services/rfp-service/exports/__init__.py` exporting a default-configured backend
  - [ ] 2.4 Unit test the backend with a tmp directory
### [ ] 3 Implement signed URL token
  - [ ] 3.1 `services/rfp-service/exports/signed_url.py` exposing `sign(file_path, expires_at) -> token` and `verify(token) -> file_path | None`
  - [ ] 3.2 Key derived from `JWT_SECRET` via HKDF (or simple `hashlib` HMAC for v1)
  - [ ] 3.3 Default TTL 1h; configurable per request
  - [ ] 3.4 Unit tests for sign/verify and expiry handling
### [ ] 4 Build Jinja2 templates
  - [ ] 4.1 `templates/report.html.j2` — header (logo + display_name + report_header), score rollup, eligibility (visual pass/fail), compliance grid, capability coverage, risks table, exec summary, footer (report_footer + page numbers)
  - [ ] 4.2 `templates/report.docx.j2` — same content using docx-template tags
  - [ ] 4.3 CSS for the HTML template using tenant brand colours via injected `--brand-primary` and `--brand-accent`
  - [ ] 4.4 Validate Jinja2 vars compile without errors against a fixture context
### [ ] 5 Implement render module
  - [ ] 5.1 `services/rfp-service/exports/render.py` exposes `render_pdf(assessment_id, tenant_brand) -> bytes` and `render_docx(assessment_id, tenant_brand) -> bytes`
  - [ ] 5.2 Fetch assessment + children + tenant brand + offering names (for coverage matrix)
  - [ ] 5.3 Render templates; return bytes
  - [ ] 5.4 Logo URL: if remote, download once; if local path, embed directly
  - [ ] 5.5 Fallback to text-only header when logo missing
### [ ] 6 Implement export endpoints
  - [ ] 6.1 `POST /rfps/{id}/assessments/{aid}/export` — body `{format:"pdf"|"docx"}`; render, store, persist `assessment_exports` row, return `{export_id, url, expires_at}`
  - [ ] 6.2 `GET /rfps/{id}/assessments/{aid}/exports` — list past exports for this assessment
  - [ ] 6.3 `GET /exports/download/{token}` — verify token, stream file from storage, set Content-Disposition
  - [ ] 6.4 All operations scoped by `common/tenancy.py:tenant_scope`
  - [ ] 6.5 api-gateway proxies the three routes
### [ ] 7 Add Docker volume for exports
  - [ ] 7.1 In `docker-compose.yml`, define a named volume `rfp_exports`
  - [ ] 7.2 Mount it at `/var/exports` in the `rfp-service` block
  - [ ] 7.3 Verify post-restart the file is still available
### [ ] 8 Build AssessmentExportDialog (frontend)
  - [ ] 8.1 `frontend/components/rfp/AssessmentExportDialog.tsx` — modal dialog
  - [ ] 8.2 Format radio: PDF / DOCX (default PDF, from `tenant.config.export.default_format`)
  - [ ] 8.3 Preview: tenant display_name, logo thumbnail, primary colour swatch
  - [ ] 8.4 "Generate" button: calls export endpoint, shows progress, on success opens download URL in new tab
  - [ ] 8.5 Triggered from `AssessmentScorecard` header
  - [ ] 8.6 List recent exports inline with download links
### [ ] 9 Integration test + sample artifact
  - [ ] 9.1 `tests/integration/test_exports.py` seeds an assessment fixture, calls the export endpoint, writes the resulting PDF to a temp file, asserts non-zero size and PDF magic bytes
  - [ ] 9.2 Same for DOCX (ZIP magic bytes + `[Content_Types].xml` present)
  - [ ] 9.3 Tenancy isolation: a `widgetco` user gets 404 on Akkodis's export
  - [ ] 9.4 Manual sanity check: render the seed Akkodis assessment, eyeball the PDF

### Phase 6: Branding & Documentation — `active_plans/bid-assessment-pivot/phases/phase_6_branding_docs.md`
#### Tasks
### [ ] 1 Implement /tenants/me endpoints
  - [ ] 1.1 Add `GET /tenants/me` to `api-gateway/main.py` returning `{id, slug, display_name, brand}` for the request's tenant
  - [ ] 1.2 Add `PATCH /tenants/me/brand` accepting partial `brand JSONB` updates
  - [ ] 1.3 Logo upload route: `POST /tenants/me/brand/logo` accepting SVG/PNG ≤2 MB; sanitise SVG; resize PNG to ≤200x200; store at `/var/brand/<slug>/logo.<ext>`
  - [ ] 1.4 Static-serve `/brand/<slug>/...` (or proxy) so the frontend can `<img src="/brand/akkodis/logo.svg" />`
  - [ ] 1.5 Role check enforced at gateway
  - [ ] 1.6 Unit tests for happy path + role gate + invalid logo rejection
### [ ] 2 Build BrandThemeProvider
  - [ ] 2.1 `frontend/components/branding/BrandThemeProvider.tsx` — fetches `/tenants/me` on mount; sets `--brand-primary`, `--brand-accent` on `:root`; exposes `{logoUrl, displayName}` via React context
  - [ ] 2.2 Mount in `frontend/app/layout.tsx` between auth and ThemeProvider
  - [ ] 2.3 Update `frontend/components/AppShell.tsx` to render logo + display_name from context
  - [ ] 2.4 Update document `<title>` to include the tenant display_name
### [ ] 3 Convert hard-coded colours to CSS vars
  - [ ] 3.1 Grep `frontend/` for hex colours and Tailwind class hard-codes
  - [ ] 3.2 Replace canonical brand uses with CSS-var equivalents
  - [ ] 3.3 Document the convention in a short comment in `globals.css`
### [ ] 4 Build branding admin page
  - [ ] 4.1 `frontend/components/branding/BrandingAdmin.tsx` — form with logo upload, two colour pickers, header text, footer text
  - [ ] 4.2 `frontend/app/(admin)/admin/branding/page.tsx` mounting the component
  - [ ] 4.3 Submit calls `PATCH /tenants/me/brand` (and `POST .../logo` separately if a new file is selected)
  - [ ] 4.4 Show a "Refresh to see changes" toast on success
  - [ ] 4.5 Role-gate the page in middleware or layout
  - [ ] 4.6 Add the page to admin nav in `AppShell.tsx`
### [ ] 5 Create seeds/_example/ template
  - [ ] 5.1 Mirror `seeds/akkodis/` directory structure with placeholder content (TODOs, minimal valid rows)
  - [ ] 5.2 Include a `README.md` explaining each file's purpose
  - [ ] 5.3 Verify `seed_tenant.py _example` (or similar) produces a valid tenant — used as a smoke test
### [ ] 6 Create seeds/widgetco/ validation fixture
  - [ ] 6.1 Copy `seeds/_example/` to `seeds/widgetco/`
  - [ ] 6.2 Edit slug, display_name, brand (different primary/accent colours, distinct logo)
  - [ ] 6.3 Add minimal seed data: 2 service lines, 1 industry, 1 certification, 1 snippet
  - [ ] 6.4 Verify `seed_tenant.py widgetco` runs idempotently
### [ ] 7 Add second-tenant smoke test
  - [ ] 7.1 `tests/integration/test_second_tenant_smoke.py`: spin up a clean DB, run migrations, seed Akkodis + widgetco
  - [ ] 7.2 Create one user in widgetco, fetch JWT, call `/tenants/me`, assert widgetco branding
  - [ ] 7.3 Assert no Akkodis rows surface in any widgetco list
  - [ ] 7.4 Wire into `scripts/test_workflows.py`
### [ ] 8 Rewrite README
  - [ ] 8.1 Rewrite the top of `README.md` to lead with "Bid Assessment" as the primary value prop
  - [ ] 8.2 Demote answer drafting to a downstream feature in the overview
  - [ ] 8.3 Update the architecture diagram with the renamed `capability-service` and new pipeline
  - [ ] 8.4 Update the services table
  - [ ] 8.5 Add an "Onboarding a New Tenant" section linking to `docs/onboarding-new-tenant.md`
  - [ ] 8.6 Verify the README's commands run against a fresh checkout
### [ ] 9 Update spec.md
  - [ ] 9.1 Add a new top-level section to `spec.md` summarising the pipeline + agents
  - [ ] 9.2 Add the 7 assessment tables + 7 capability tables to the Data Model section
  - [ ] 9.3 Add the new endpoints to the API Overview section
  - [ ] 9.4 Link to the canonical design doc
### [ ] 10 Write onboarding playbook
  - [ ] 10.1 `docs/onboarding-new-tenant.md` covering: copy `seeds/_example/` → edit → run `seed_tenant.py` → log in → verify brand → seed real capability data via admin UI
  - [ ] 10.2 Include screenshots of the branding admin page
  - [ ] 10.3 Cross-link from README

---

## Decision Log

- D1: Multi-tenant capable; Akkodis is the first profile — Status: Closed — Date: 2026-05-13
- D2: Single-timeline pre-stage workflow (Upload → Extract → Assess → Bid/No-Bid → Draft → Review) — Status: Closed — Date: 2026-05-13
- D3: Scorecard + exportable PDF/DOCX + AI exec summary as primary assessment output — Status: Closed — Date: 2026-05-13
- D4: Full 7-dimension capability profile incl. rate cards / partnerships / engagement sizes — Status: Closed — Date: 2026-05-13
- D5: v1 plugin system = snippet/template library; rule-based + LLM-tool plugins deferred — Status: Closed — Date: 2026-05-13
- D6: One `documents` table with `category` enum (vs separate first-class entities for past_proposals / contracts) — Status: Closed — Date: 2026-05-13
- D7: Rename `portfolio-service` → `capability-service`; no new service introduced — Status: Closed — Date: 2026-05-13
- D8: Add `tenants` table (real multi-tenancy) — Status: Closed — Date: 2026-05-13
- D9: Eligibility checks and compliance items stay separate (separate tables, separate agents) — Status: Closed — Date: 2026-05-13
- D10: 5-agent pipeline (Compliance / Eligibility / BestFit / Risk / ExecSummary) — Status: Closed — Date: 2026-05-13
- D11: AI verdict and human `bid_decisions` are separate rows; UI shows both — Status: Closed — Date: 2026-05-13
- D12: Capability writes require `content_admin` (not `system_admin`-only) — Status: Closed — Date: 2026-05-13
- D13: SSE for assessment progress (matches existing `/ask?stream=true`) — Status: Closed — Date: 2026-05-13
- D14: Extract `DraftStage.tsx` + `ReviewStage.tsx` as part of the RFPWorkspace reshape — Status: Closed — Date: 2026-05-13
- D15: Snippets auto-approve when authored by `content_admin`/`system_admin` — Status: Closed — Date: 2026-05-13
- D16: Single shared Postgres schema with `tenant_id` filter (per-tenant schemas deferred) — Status: Closed — Date: 2026-05-13
- D17: Keep both `tenants.config` and `users.tenant_config` layers — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this plan's accuracy.

### Source Files (existing code/docs being modified)
- `services/portfolio-service/main.py` — will be renamed/refactored to `capability-service`
- `services/orchestrator/agents.py` — existing typed-agent base; new agents subclass it
- `services/orchestrator/pipeline.py` — existing `AgentPipeline`; new `BidAssessmentPipeline` lives alongside
- `services/orchestrator/prompts.py` — existing prompt templates; new prompts for assessment agents
- `services/content-service/chunker.py` — gains a snippet branch
- `services/retrieval-service/retrieve.py` — gains tenant_id filter and category-weighted RRF
- `services/rfp-service/main.py` — gains assessment CRUD, bid-decision, export endpoints
- `services/api-gateway/auth.py` — gains tenant_id attachment to request state
- `services/api-gateway/main.py` — gains new proxy routes
- `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` — reshaped into a stage container
- `frontend/components/ThemeProvider.tsx` — wrapped by new BrandThemeProvider
- `frontend/app/layout.tsx` — adds BrandThemeProvider
- `frontend/lib/api.ts` — adds new client functions
- `migrations/versions/0008_companies.py` — current alembic head
- `docker-compose.yml` — service rename, env var rename, exports volume
- `README.md` — primary value-prop rewrite
- `spec.md` — adds Bid Assessment Pipeline section
- `scripts/seed_demo.py` — refactored to invoke seed_tenant
- `common/common/db.py` — existing Base/engine; gains tenant scope helper consumer

### Destination Files (new files this plan creates)
- `common/tenancy.py` — `tenant_scope()` helper
- `services/capability-service/` — directory (renamed)
- `services/orchestrator/bid_assessment.py` — new `BidAssessmentPipeline` and 5 agents (or split as the phase plan dictates)
- `services/rfp-service/exports/` — Jinja2 templates + render module
- `frontend/components/rfp/` — new components (RFPTimeline, AssessmentScorecard, etc.)
- `frontend/components/capability/` — capability admin components
- `frontend/components/snippets/SnippetLibraryAdmin.tsx`
- `frontend/components/branding/BrandThemeProvider.tsx`
- `frontend/lib/useAssessmentStream.ts` — SSE hook
- `frontend/app/(admin)/admin/capabilities/page.tsx`
- `frontend/app/(admin)/admin/snippets/page.tsx`
- `frontend/app/(admin)/admin/branding/page.tsx`
- `migrations/versions/0009_tenants_table_and_backfill.py`
- `migrations/versions/0010_tenants_not_null_and_fks.py`
- `migrations/versions/0011_capability_profile.py`
- `migrations/versions/0012_documents_category.py`
- `migrations/versions/0013_bid_assessments.py`
- `scripts/seed_tenant.py` — generic tenant bootstrap
- `scripts/seeds/akkodis/` — Akkodis seed data tree
- `scripts/seeds/_example/` — onboarding template
- `docs/onboarding-new-tenant.md` — one-page playbook

### Related Documentation (context only)
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` — canonical design spec
- `active_plans/bid-assessment-pivot/bid-assessment-pivot_spec.md` — Maistro copy
- `how_to/templates/master_plan_template.md` — plan structure rules
- `how_to/templates/phase_plan_template.md` — phase plan rules
- `how_to/guides/orchestrator.md` — orchestrator usage
- `how_to/guides/plan_review.md` — plan review loop
- `how_to/guides/code_review.md` — code review loop
- `CLAUDE.md` — project conventions

---

## Reviewer Checklist

Reviewers MUST verify all of the following:

### Structure & Numbering

- [ ] Required sections appear in the correct order.
- [ ] All mirrored tasks use correct patterns (`### [ ] N`, `  - [ ] N.1`).
- [ ] No `1.1.1` items appear in the master plan.

### Traceability

- [ ] Every task in the master appears in the corresponding phase file.
- [ ] No task exists in the master that is not in a phase file.
- [ ] Global Acceptance Gates map to real tasks or phases.

### Consistency

- [ ] Phase titles and file paths match actual files.
- [ ] No invented content appears in Phases Overview.
- [ ] Grammar, wording, and semantics of tasks match the corresponding phase files.

### References

- [ ] Source Files, Destination Files, and Related Documentation sections are present and formatted correctly.
