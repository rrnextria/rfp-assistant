# Bid Assessment Pivot — Design Specification

**Date:** 2026-05-13
**Status:** Draft (awaiting user review)
**Slug:** `bid-assessment-pivot`
**Author:** Ravi (with Claude assistance)
**Maistro copy:** `active_plans/bid-assessment-pivot/bid-assessment-pivot_spec.md`

---

## 1. Summary

Reposition the existing RFP Assistant — today centred on retrieving permission-scoped content and drafting answers — into a **Bid Assessment** product whose primary value is an automated, AI-driven **bid/no-bid decision** for each incoming RFP. Answer drafting remains, but moves downstream of an explicit assessment stage.

The first deployment is branded for **Akkodis**, an IT engineering & services firm. The codebase must remain generic so the same product can be re-branded and re-seeded for other customers without code changes.

### What's new (vs current product)

1. **Bid/no-bid decision stage** before drafting, with an explicit human decision step.
2. **Structured assessment artifacts:** compliance items, eligibility checks, risk register, capability-coverage matrix, AI exec summary, rolled up into a fit score, win probability, and AI verdict.
3. **Exportable branded report** (PDF + DOCX) for bid-committee review.
4. **Tenant capability profile** — 7 dimensions modelling what a services firm can deliver (service lines, industries, geographies, certifications, contract vehicles, partnerships, rate cards, engagement sizes), plus the existing products table.
5. **Snippet library** — curated boilerplate corporate responses, retrieval-boosted and surfaced as evidence in compliance items and as one-click inserts during draft.
6. **First-class multi-tenancy** — a real `tenants` table; all data carries `tenant_id`; branding (logo, colours, report header/footer) is per tenant.
7. **Knowledge base categories** — `documents.category` enum (`product_doc`, `past_proposal`, `contract`, `boilerplate_snippet`, `general`) with category-weighted retrieval scoring.

### What stays unchanged

- Hybrid pgvector + tsvector retrieval with RRF (k=60).
- RBAC enforced as SQL predicate.
- The existing typed-agent base in `orchestrator`.
- Win/loss learning in `analytics-service` (consumed by the new ExecSummaryAgent).
- The 11-service deployment topology.

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Ship an Akkodis-branded bid-assessment workflow end-to-end on Docker Compose.
- Keep the codebase tenant-generic; onboarding a new customer is a seed-script operation, not a code change.
- Preserve the existing answer-drafting flow as a downstream stage; no functional regression for already-seeded RFPs.
- Provide a structured, audit-friendly trail of every assessment run.

### 2.2 Non-Goals (v1)

- No tenant self-signup or in-product tenant creation.
- No per-tenant Postgres schema; single shared schema with `tenant_id` filtering.
- No background job queue; assessments are synchronous, SSE-streamed.
- No real-time multi-user editing on the scorecard.
- No mobile-first UI redesign.
- No external KB integrations (SharePoint, Confluence, Salesforce). The plugin surface is *only* the snippet library in v1.
- No automatic snippet generation from past proposals.
- No multilingual snippets / report templates.

---

## 3. Architecture Overview

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
│   (8001)      │  │    (8005)     │  │    (8003)                  │
│ AnswerPipeline│  │ RFP + Assess  │  │ ingest (+ category enum)   │
│ BidAssessment │  │ CRUD,         │  │ chunk, embed, approve      │
│ Pipeline NEW  │  │ bid-decision, │  │ snippet ingestion          │
│               │  │ export NEW    │  │                            │
└──────┬────────┘  └───────────────┘  └────────────────────────────┘
       │
  ┌────┴──────────────────────────────┐
  │                                   │
┌─▼─────────────────┐    ┌────────────▼────────────────────────┐
│ retrieval-service │    │  capability-service  ★ RENAMED       │
│     (8002)        │    │     (8010, was portfolio-service)    │
│ hybrid + RBAC +   │    │ services, industries, geographies,   │
│ tenant_id +       │    │ certs, contract vehicles,            │
│ category-weighted │    │ partnerships, rate cards,            │
│ RRF (+ snippet    │    │ engagement sizes, products           │
│  boost)           │    │ + coverage matrix + gap detection    │
└───────────────────┘    └──────────────────────────────────────┘

┌──────────────────────────┐  ┌──────────────────────────┐
│  model-router (8006)     │  │  rbac-service (8004)     │
└──────────────────────────┘  └──────────────────────────┘
┌──────────────────────────┐  ┌──────────────────────────┐
│  audit-service (8008)    │  │  analytics-service (8009)│
│                          │  │  win/loss → score boosts │
└──────────────────────────┘  └──────────────────────────┘
```

**Key changes:**

- `portfolio-service` is **renamed to `capability-service`** (port unchanged at 8010). Its scope broadens from products to the full capability profile.
- `orchestrator` gains a `BidAssessmentPipeline` next to the existing `AgentPipeline`. Both share the typed-agent base; no shared mutable state.
- `rfp-service` grows assessment CRUD, bid-decision, and report-export endpoints.
- `content-service` gains a `category` enum and a snippet-aware chunker branch.
- `retrieval-service` learns category-weighted RRF and tenant_id filtering.
- No new services. Service count stays 11.

---

## 4. Data Model

### 4.1 Tenants & branding (new)

```sql
tenants(
  id          UUID PRIMARY KEY,
  slug        VARCHAR UNIQUE NOT NULL,
  display_name VARCHAR NOT NULL,
  brand       JSONB NOT NULL DEFAULT '{}',
  config      JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT now()
)

users.tenant_id  -- new FK; backfilled to seeded Akkodis tenant
```

`brand` keys: `logo_url`, `primary_color`, `accent_color`, `report_header`, `report_footer`.

`config` keys (tenant-wide; merged with `users.tenant_config` per-user overrides):
```jsonc
{
  "model_routing":   { "primary": "claude", "fallback_chain": ["openai","ollama"] },
  "retrieval": {
    "category_boosts": {
      "boilerplate_snippet":   0.15,
      "past_proposal_won":     0.10,
      "past_proposal_lost":    0.02,
      "contract":              0.05,
      "product_doc":           0.00,
      "general":               0.00
    },
    "rbac_strict": true
  },
  "assessment": {
    "verdict_thresholds": { "bid_min_fit": 0.70, "no_bid_max_fit": 0.40 },
    "mandatory_compliance_gate": true
  },
  "export": { "default_format": "pdf", "watermark": null }
}
```

### 4.2 Capability profile (new tables in `capability-service`)

All tables carry `tenant_id UUID NOT NULL` and `created_at`. Omitted from the table below for brevity.

| Table | Key columns |
|---|---|
| `service_lines` | `id, name, description, parent_id NULLABLE, embedding VECTOR(384)` |
| `industries` | `id, name` |
| `geographies` | `id, name, type ENUM(country,region,city), parent_id NULLABLE` |
| `certifications` | `id, name, issuing_body, scope, expires_at, evidence_doc_id NULLABLE` |
| `contract_vehicles` | `id, name, jurisdiction, expires_at` |
| `partnerships` | `id, partner_name, tier, scope` |
| `rate_cards` | `id, role, region, currency, hourly_rate NUMERIC, daily_rate NUMERIC, effective_from, effective_until` |
| `engagement_sizes` | `id, label, min_value NUMERIC, max_value NUMERIC, currency` |
| `service_line_industries` | composite PK `(service_line_id, industry_id)` |
| `service_line_geographies` | composite PK `(service_line_id, geography_id)` |

The existing `products` table is retained — it remains a valid "offering type" for tenants that are software vendors.

### 4.3 Bid Assessment (new tables in `rfp-service`)

| Table | Key columns |
|---|---|
| `bid_assessments` | `id, rfp_id, tenant_id, status ENUM(running,complete,partial,failed), fit_score NUMERIC, win_probability NUMERIC, verdict ENUM(bid,no_bid,review), summary TEXT, model_version VARCHAR, generated_by UUID, generated_at TIMESTAMPTZ, version INT` |
| `compliance_items` | `id, assessment_id, requirement_id NULLABLE, category, label, mandatory BOOL, status ENUM(pass,fail,partial,unknown), evidence JSONB, citations JSONB` |
| `eligibility_checks` | `id, assessment_id, label, kind ENUM(geography,contract_vehicle,certification,financial,exclusion,other), expected, actual, status ENUM(pass,fail,partial,unknown), citations JSONB` |
| `risks` | `id, assessment_id, category ENUM(commercial,delivery,legal,technical,reputational), title, description, severity ENUM(low,medium,high), likelihood ENUM(low,medium,high), mitigation TEXT NULLABLE, citations JSONB, authored_by ENUM(ai,human)` |
| `capability_matches` | `id, assessment_id, requirement_id, offering_type ENUM(service_line,product), offering_id NULLABLE, match_score NUMERIC, gap_notes TEXT NULLABLE` |
| `bid_decisions` | `id, rfp_id, tenant_id, decision ENUM(bid,no_bid,review), decided_by UUID, decided_at TIMESTAMPTZ, rationale TEXT, conditions JSONB` |
| `assessment_exports` | `id, assessment_id, format ENUM(pdf,docx), file_path VARCHAR, generated_at TIMESTAMPTZ, generated_by UUID` |

`bid_assessments.version` enables re-runs without destroying history. Optimistic-lock pattern: PATCH to children requires `If-Match: <version>` and returns 409 on mismatch.

### 4.4 Documents extension

```sql
ALTER TABLE documents ADD COLUMN category VARCHAR NOT NULL DEFAULT 'general';
-- enum: product_doc | past_proposal | contract | boilerplate_snippet | general
```

`metadata JSONB` conventions per category:
- `past_proposal`: `{ rfp_id, outcome: "won"|"lost", submitted_at }`
- `contract`: `{ client_id, effective_date, expires_at, value }`
- `boilerplate_snippet`: `{ topic_tags: string[], version: int, approved_by }`

### 4.5 Migration ordering

Two alembic files for the tenancy work; partial failure is recoverable without re-doing the backfill:

- `0009_tenants_table_and_backfill.py` — create `tenants`, seed Akkodis row, add nullable `tenant_id` columns to every affected table, backfill all existing rows.
- `0010_tenants_not_null_and_fks.py` — `ALTER COLUMN tenant_id SET NOT NULL`, add FKs, add indexes.

Subsequent migrations (one per phase) layer on top:
- `0011_capability_profile.py` — 7 capability tables + 2 M2M tables.
- `0012_documents_category.py` — `documents.category` column.
- `0013_bid_assessments.py` — 7 assessment tables.

Each migration is reversible; `scripts/test_workflows.py` runs `upgrade head → downgrade base → upgrade head` to catch non-reversible operations.

---

## 5. Bid Assessment Pipeline

### 5.1 Pipeline shape

```
              ┌───────────────────────┐
              │  RFP already ingested │
              │  + requirements rows  │
              └──────────┬────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼───────┐ ┌──────▼──────┐ ┌───────▼────────┐
│ Compliance    │ │ Eligibility │ │  BestFit       │
│ Agent         │ │ Agent       │ │  Agent         │
│ (per req.)    │ │ (bid-killers│ │ (req ↔ offering│
│               │ │  upfront)   │ │  matrix)       │
└──────┬────────┘ └──────┬──────┘ └───────┬────────┘
       │                 │                │
       └─────────────────┼────────────────┘
                         │
              ┌──────────▼─────────┐
              │   Risk Agent       │
              │ (consumes outputs  │
              │  above + raw RFP)  │
              └──────────┬─────────┘
                         │
              ┌──────────▼──────────────────┐
              │   ExecSummary Agent          │
              │ (rolls up: fit_score,        │
              │  win_probability, verdict,   │
              │  1-page summary)             │
              │  ← reads win/loss boosts     │
              └──────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │ bid_assessments row │
              │ + child rows        │
              └─────────────────────┘
```

The first three agents are independent and run in parallel via `asyncio.gather`. Risk waits on all three. ExecSummary waits on Risk.

### 5.2 Agent specs

Each agent inherits the existing `TypedAgent[InputSchema, OutputSchema]` base. The pipeline owns DB writes; agents are pure functions over data.

| Agent | Input | Output | Reads from |
|---|---|---|---|
| **ComplianceAgent** | `rfp_id, requirements[], tenant_id` | `ComplianceItem[]` | `retrieval-service` (approved docs, snippets, past won proposals — category-weighted) |
| **EligibilityAgent** | `rfp_id, raw_text, tenant_id` | `EligibilityCheck[]` (geography, contract vehicle, certifications, financial thresholds, exclusions) | `capability-service` |
| **BestFitAgent** | `requirements[], tenant_id` | `CapabilityMatch[]` | `capability-service` (embeddings on `service_lines` + `products`) |
| **RiskAgent** | `raw_text, requirements[], compliance[], eligibility[], best_fit[]` | `Risk[]` across the 5 categories | LLM only |
| **ExecSummaryAgent** | All prior outputs + `analytics.score_boosts` for tenant + tenant `assessment.verdict_thresholds` | `{ summary, fit_score, win_probability, verdict }` | `analytics-service`; tenant config; LLM |

### 5.3 Pydantic schemas (canonical)

```python
class Citation(BaseModel):
    document_id: UUID
    chunk_id: UUID
    position: int
    excerpt: str | None

class ComplianceItem(BaseModel):
    requirement_id: UUID | None
    category: Literal["security","privacy","operational","commercial","legal","other"]
    label: str
    mandatory: bool
    status: Literal["pass","fail","partial","unknown"]
    evidence: dict   # { kind: "certification|snippet|past_proposal|product|service_line",
                     #   ref_id: UUID, excerpt: str }
    citations: list[Citation]

class EligibilityCheck(BaseModel):
    label: str
    kind: Literal["geography","contract_vehicle","certification","financial","exclusion","other"]
    expected: str
    actual: str
    status: Literal["pass","fail","partial","unknown"]
    citations: list[Citation]

class Risk(BaseModel):
    category: Literal["commercial","delivery","legal","technical","reputational"]
    title: str
    description: str
    severity: Literal["low","medium","high"]
    likelihood: Literal["low","medium","high"]
    mitigation: str | None
    citations: list[Citation]

class CapabilityMatch(BaseModel):
    requirement_id: UUID
    offering_type: Literal["service_line","product"]
    offering_id: UUID | None
    match_score: float          # 0–1
    gap_notes: str | None
```

### 5.4 Pipeline-level concerns

- **Execution model.** Synchronous, server-streamed (SSE). Reuses the existing `/ask?stream=true` pattern. No queue layer in v1.
- **Idempotency / re-runs.** A new run creates a new `bid_assessments` row with `version = previous + 1`. UI shows latest by default with a history dropdown.
- **Partial failure.** A failure in any of the three parallel agents persists the surviving outputs and sets `bid_assessments.status = "partial"`; Risk then runs against whatever data is available; ExecSummary degrades to `verdict = review` and notes the gap in `summary`. A failure in Risk or ExecSummary itself leaves the partial assessment in `status = "failed"` with surviving rows intact — re-run replaces, never deletes.
- **Determinism for tests.** Each agent accepts a mockable LLM client (existing pattern in `services/orchestrator/adapters/`). Pipeline tests use stub agents returning canned outputs.
- **Audit.** Every agent invocation produces an `audit_logs` entry with the existing redaction rules.
- **Verdict ownership.** AI sets `bid_assessments.verdict`; human decision lives in a separate `bid_decisions` row and is what gates the Draft stage. The scorecard always shows both.

---

## 6. API Surface

All endpoints accessed via `api-gateway` (8000), inherit JWT auth + per-route role checks.

### 6.1 Tenants & branding

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/tenants/me` | any | Current tenant (id, slug, display_name, brand) |
| PATCH | `/tenants/me/brand` | system_admin | Update `brand JSONB` |

### 6.2 Capability profile (proxied to `capability-service`)

Standard CRUD on 8 resources:

```
/capabilities/service-lines
/capabilities/industries
/capabilities/geographies
/capabilities/certifications
/capabilities/contract-vehicles
/capabilities/partnerships
/capabilities/rate-cards
/capabilities/engagement-sizes
```

Each supports `GET /…`, `POST /…`, `GET /…/{id}`, `PATCH /…/{id}`, `DELETE /…/{id}`.

Plus rollup:

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/capabilities/profile` | any | Single payload bundling all 8 dimensions |

Writes: `content_admin` or `system_admin`. Reads: any authenticated user.

### 6.3 Documents extension

```
POST  /documents          body adds: category, plus metadata.* per category
GET   /documents?category=past_proposal&outcome=won&limit=20
```

Plus snippet façade:

| Method | Path | Role |
|---|---|---|
| POST | `/snippets` | content_admin |
| GET | `/snippets?topic=gdpr&q=…` | any |
| PATCH | `/snippets/{id}` | content_admin |
| DELETE | `/snippets/{id}` | content_admin |

Snippets authored by `content_admin`/`system_admin` auto-approve; snippets authored by `end_user` require explicit approval via `PATCH /documents/{id}/approve`.

### 6.4 Bid Assessment

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/rfps/{id}/assess` | end_user+ | Kick off pipeline; returns `{assessment_id, status:"running"}` |
| GET | `/rfps/{id}/assess?stream=true` | end_user+ | SSE stream (`stage`, `agent`, `pct`, `error?`). Returns 404 if no assessment is currently `status=running` for this RFP. |
| GET | `/rfps/{id}/assessments` | end_user+ | History list |
| GET | `/rfps/{id}/assessments/latest` | end_user+ | Convenience |
| GET | `/rfps/{id}/assessments/{aid}` | end_user+ | Full assessment with all children embedded |
| PATCH | `/rfps/{id}/assessments/{aid}/compliance/{cid}` | content_admin+ | Override compliance status/evidence |
| PATCH | `/rfps/{id}/assessments/{aid}/risks/{rid}` | end_user+ | Edit risk |
| POST | `/rfps/{id}/assessments/{aid}/risks` | end_user+ | Add human-authored risk |
| DELETE | `/rfps/{id}/assessments/{aid}/risks/{rid}` | end_user+ | Remove |

### 6.5 Bid decision

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/rfps/{id}/bid-decision` | end_user+ | `{decision, rationale, conditions[]}` |
| GET | `/rfps/{id}/bid-decision` | end_user+ | Latest decision |

`decision=bid` unlocks the Draft stage in the UI timeline (gate in `rfp-service`, not endpoint-level 403).

### 6.6 Report export

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/rfps/{id}/assessments/{aid}/export` | end_user+ | `{format: "pdf"\|"docx"}` → `{export_id, url, expires_at}` |
| GET | `/rfps/{id}/assessments/{aid}/exports` | end_user+ | List prior exports |

Files live on a local volume `/var/exports` in v1; Phase-2 swap to S3/Azure Blob.

### 6.7 Conventions

- List endpoints: `?limit` (≤100), `?offset`, `?q`.
- Mutations on assessment children require `If-Match: <bid_assessments.version>`; 409 on mismatch.
- Write responses return the persisted row.
- Error shape stays `{detail, code}`.

### 6.8 Renamed env vars

- `PORTFOLIO_SERVICE_URL` → `CAPABILITY_SERVICE_URL`. Public API unchanged.

---

## 7. Frontend Workflow & UI

### 7.1 RFP Workspace timeline

Reshape `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` from a Q&A page into a stage container driven by a left-rail stepper. Six stages:

| Stage | Active when… | Locked until… |
|---|---|---|
| Upload | RFP row exists | — |
| Extract | requirements exist | upload complete |
| Assess | a `bid_assessments` row exists | requirements exist |
| Decision | latest assessment `status=complete` | assessment finished |
| Draft | `bid_decisions.decision=bid` exists | decision recorded |
| Review | at least one answer in `pending_approval` | — |

Locked stages render greyed-out with "Complete <previous> to unlock"; nothing is hidden.

### 7.2 Component tree

```
frontend/components/
├── rfp/
│   ├── RFPTimeline.tsx
│   ├── AssessmentScorecard.tsx
│   ├── ScoreRollupHeader.tsx       # fit + win prob + AI verdict + human decision
│   ├── ComplianceGrid.tsx
│   ├── EligibilityPanel.tsx
│   ├── RiskRegister.tsx            # editable
│   ├── CoverageMatrix.tsx          # heat-map req × offerings
│   ├── ExecSummaryCard.tsx         # rendered markdown + regen
│   ├── BidDecisionForm.tsx
│   ├── AssessmentExportDialog.tsx
│   ├── AssessmentHistoryMenu.tsx
│   ├── DraftStage.tsx              # EXTRACTED from existing RFPWorkspace
│   └── ReviewStage.tsx             # EXTRACTED from existing RFPWorkspace
├── capability/
│   ├── CapabilityProfileAdmin.tsx
│   └── CapabilityDimensionTable.tsx
├── snippets/
│   └── SnippetLibraryAdmin.tsx
└── branding/
    └── BrandThemeProvider.tsx
```

The existing `RFPWorkspace.tsx` becomes a thin orchestrator: fetch RFP + latest assessment + decision, route to the right stage component, own the SSE connection during assess.

### 7.3 New admin pages

| Route | Role |
|---|---|
| `/(admin)/admin/capabilities` | content_admin+ |
| `/(admin)/admin/snippets` | content_admin+ |
| `/(admin)/admin/branding` | system_admin |

### 7.4 SSE consumption

```ts
// frontend/lib/useAssessmentStream.ts
function useAssessmentStream(rfpId: string, assessmentId: string | null) {
  // returns { progress, currentAgent, error, isComplete, assessment }
}
```

`AssessmentScorecard` shows an inline 5-step progress strip; on `isComplete`, refetches via `GET /rfps/{id}/assessments/latest`.

### 7.5 Branding

`BrandThemeProvider` wraps the existing `ThemeProvider`, fetches `/tenants/me` once after auth, sets:

```css
:root {
  --brand-primary: <tenant.brand.primary_color>;
  --brand-accent:  <tenant.brand.accent_color>;
}
```

Logo + display name surface in `AppShell` and report header/footer.

---

## 8. Snippet Library Mechanics

### 8.1 Storage

Physically `documents` rows with `category=boilerplate_snippet`. Metadata: `{ topic_tags: string[], version: int, approved_by }`.

### 8.2 Lifecycle

- **Author.** `POST /snippets {title, body, topic_tags}` → `documents` row, `status=pending_approval`, `metadata.version=1`.
- **Auto-approve.** If author has `content_admin`/`system_admin`, the handler also sets `status=approved` on create.
- **Versioning.** `PATCH /snippets/{id}` increments `metadata.version`, rewrites body, resets `status=pending_approval` (re-approval required when text changes).
- **Soft delete.** `DELETE` sets `status=archived`.

### 8.3 Chunking

```python
# content-service/chunker.py
if document.category == "boilerplate_snippet":
    return [Chunk(text=document.body, position=0, metadata={...})]
```

One chunk per snippet, no overlap, no splitting.

### 8.4 Retrieval — category-weighted RRF

```
final_score = rrf_score(vector_rank, keyword_rank)
            + category_boost[chunk.document.category]
            + topic_tag_boost(chunk, query)
            + winloss_boost(chunk)        # already present
```

`category_boost` and tag-boost values are tenant-config knobs (see §4.1).

### 8.5 Tag classification

`ExtractionAgent` is extended to emit a `tags[]` array on each requirement, classified against the **union of all snippet `topic_tags` in the current tenant** (fetched fresh on each extraction run). The vocabulary is *defined by the snippet library itself* — adding snippets expands the vocabulary, removing them shrinks it.

### 8.6 Surface in ComplianceAgent

```python
ComplianceItem(
    status="pass",
    evidence={
        "kind": "snippet",
        "ref_id": "<snippet uuid>",
        "excerpt": "<first 240 chars>"
    },
    citations=[Citation(...)]
)
```

UI renders these as **"Suggested corporate response"** chips, distinct from "Evidence from <doc>" chips. One-click action: **Insert into draft** — pre-fills the answer textarea in the Draft stage.

---

## 9. Tenancy & Branding Config

### 9.1 Tenant resolution at runtime

`api-gateway/auth.py` decodes the JWT, loads `users.tenant_id`, attaches it to `request.state`. Every downstream service receives `tenant_id` in the call and filters all queries on it.

```python
# common/tenancy.py  (new)
def tenant_scope(query, tenant_id, table):
    return query.where(table.c.tenant_id == tenant_id)
```

Code-review rule: any query touching a tenant-scoped table without this helper is a leak. The integration test in §10.2 catches violations.

### 9.2 Seeding model

```
scripts/
├── seed_demo.py              # refactored to invoke seed_tenant
├── seed_tenant.py            # NEW — generic tenant bootstrap
└── seeds/
    ├── akkodis/
    │   ├── tenant.yaml
    │   ├── service_lines.yaml
    │   ├── industries.yaml
    │   ├── geographies.yaml
    │   ├── certifications.yaml
    │   ├── contract_vehicles.yaml
    │   ├── partnerships.yaml
    │   ├── rate_cards.yaml
    │   ├── engagement_sizes.yaml
    │   ├── snippets/
    │   │   ├── gdpr.md
    │   │   ├── soc2.md
    │   │   └── sla_defaults.md
    │   └── brand/
    │       └── logo.svg
    └── _example/             # template for future customers
```

`seed_tenant.py akkodis` is idempotent (uses `slug` as natural key), upserts, embeds. Onboarding a new customer: copy `_example/`, edit, commit, run.

Snippet markdown files have YAML front-matter capturing `topic_tags` and approval status.

### 9.3 Brand asset storage

Logo files on a local volume `/var/brand/<tenant-slug>/logo.svg`, served by `api-gateway` as static. Phase-2 swap to S3/Azure Blob is one adapter.

### 9.4 Effective config resolution

```
effective_config = deep_merge(tenants.config, users.tenant_config)
```

`users.tenant_config` overrides at the leaf level. Tenant-wide defaults are in `tenants.config`; per-user overrides remain a knob (e.g., a power user with a model preference).

### 9.5 RBAC interplay

Tenancy doesn't replace RBAC. The retrieval predicate composes both:

```sql
WHERE metadata->>'approved' = 'true'
  AND tenant_id = :current_tenant            -- isolation (cross-customer)
  AND (role-filter on metadata->>'allowed_roles')   -- authorization (within-customer)
  AND (team-filter on metadata->>'allowed_teams')
```

---

## 10. Migration / Rollout

### 10.1 Phasing

Seven mergeable phases. Each ships with its own migrations, tests, and demo affordance.

| # | Phase | New tables | Demo affordance after |
|---|---|---|---|
| 1 | Foundation: tenants & rename | 1 (`tenants`) | Existing flows work; `capability-service` healthy |
| 2 | Capability profile | 9 | Admin can edit Akkodis service lines/certs/etc. |
| 3 | Knowledge-base extensions | 0 | Snippets searchable; requirements tag-classified |
| 4 | Bid Assessment core | 7 | `POST /rfps/{id}/assess` returns a full assessment |
| 5 | Frontend timeline | 0 | RFP workspace shows scorecard end-to-end |
| 6 | Report export | 0 | "Export PDF" produces a branded report |
| 7 | Branding & docs | 0 | New customer onboarded by copy + run |

Phase 1 is the only structural change. Phases 2–7 are additive.

### 10.2 Testing

- **Agent unit tests.** Stub LLM client; assert each agent's output schema for a canned input.
- **Pipeline test.** Stub all five agents; verify orchestration and DB persistence end-to-end.
- **Tenancy leak test.** Two tenants (`akkodis`, `widgetco`); seed each with an RFP; run assessments; assert no row from one ever appears in the other's queries across every service.
- **Migration test.** `scripts/test_workflows.py` adds: clean DB → `upgrade head` → `downgrade base` → `upgrade head`.
- **Frontend.** Component tests for new scorecard components + `useAssessmentStream` using existing setup.
- **Manual demo.** Akkodis seed runs end-to-end on the 3 seeded RFPs and produces coherent assessments.

### 10.3 Branching

- Long-lived branch: `feat/bid-assessment-pivot` off `master`.
- One sub-branch per phase, merged into the long-lived branch when its demo affordance works.
- Merge to `master` only when all seven phases pass end-to-end on the Akkodis seed.

### 10.4 Rollback

- Every alembic migration is reversible; `scripts/test_workflows.py` verifies.
- Code rollback = revert the merge commit.
- Phase-1 data rollback is benign (drop `tenants` cascades cleanly).

### 10.5 Documentation outputs

- README rewrite: lead with "Bid Assessment" as the primary value prop; answer drafting becomes a downstream feature.
- `spec.md` adds a "Bid Assessment Pipeline" section + new tables.
- New `docs/onboarding-new-tenant.md`: one-page playbook.

---

## 11. Decisions Log

Decisions taken during the brainstorming dialogue, in order. Recorded here so the rationale survives the conversation.

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Single-tenant or multi-tenant? | Multi-tenant; Akkodis is the first profile | Must stay generic/re-brandable |
| 2 | Workflow shape | Single-timeline pre-stage (`Upload → Extract → Assess → Bid/No-Bid → Draft → Review`) | Surfaces bid-assessment value prop without breaking existing screens |
| 3 | Assessment output | Scorecard + exportable PDF/DOCX + AI exec summary | Matches how real bid committees consume |
| 4 | Capability profile breadth | Full 7-dimension profile incl. rate cards / partnerships / engagement sizes | Eligibility checks need real data; commercial dims belong in v1 |
| 5 | Plugin system | Snippet/template library for v1; rule-based + LLM-tool plugins later | "Plugins" in brief is most plausibly canned responses |
| 6 | KB modelling | One `documents` table with `category` enum | Fastest; upgrade path to richer entities is mechanical |
| 7 | Integration approach | Approach 2: rename `portfolio-service` → `capability-service`; no new service | Cleanest conceptual fit; rename cost worth paying now |
| 8 | Tenants table | Proceed (required for genuine multi-tenancy) | Without it, "generic" claim is hollow |
| 9 | Eligibility vs Compliance | Split (separate tables, separate agents) | Different retrieval surfaces and UX |
| 10 | Agent count | 5 (Compliance, Eligibility, BestFit, Risk, ExecSummary) | Each has distinct prompt & data dependencies |
| 11 | Verdict ownership | AI sets `verdict`; human override in `bid_decisions`; both shown | Bid committees expect human accountability |
| 12 | Capability writes | `content_admin` (not `system_admin`) | Bid desk lead curates, not platform admin |
| 13 | Assessment progress | SSE (matches `/ask?stream=true`) | Matches existing pattern; no new infra |
| 14 | RFPWorkspace refactor | Extract `DraftStage.tsx` + `ReviewStage.tsx` | Workspace can't host 6 stages cleanly otherwise |
| 15 | Snippet approval | Auto-approve for `content_admin`/`system_admin` authors | Matches role trust elsewhere |
| 16 | Schema topology | Single shared schema, `tenant_id` filter | Cheaper to operate; per-tenant schema deferred |
| 17 | Per-user vs per-tenant config | Keep both layers (`tenants.config` + `users.tenant_config`) | User override is rare but useful |

---

## 12. Open Questions / Phase-2 Backlog

Items deliberately deferred. Each is a candidate for its own future spec.

- Automatic snippet generation from past proposals (research project).
- Snippet templating with variables (`{{customer_name}}`).
- Multilingual snippets + report templates.
- External KB plugin connectors (SharePoint, Confluence, Salesforce).
- Real-time multi-user editing on the scorecard.
- S3 / Azure Blob storage adapter for brand assets and exports.
- Background-job queue for long-running assessments.
- Tenant self-signup + in-product tenant creation.
- Per-tenant Postgres schema migration path.
- Mobile-first UI.
- Telemetry / observability (Prometheus, OTel).
- CI/CD pipeline.

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Capability profile | The tenant's "what we can deliver" — service lines, industries, geographies, certifications, contract vehicles, partnerships, rate cards, engagement sizes, plus the legacy `products` table. |
| Compliance item | "Does the RFP say we comply with this clause?" — produced by `ComplianceAgent`, one per requirement. |
| Eligibility check | "Are we even allowed to bid?" — bid-killers (geography, contract vehicle, certs, financial thresholds, exclusions). |
| Best-fit match | A `(requirement, offering)` pair with a similarity score and optional gap note. |
| Fit score | 0–1 rollup of capability matches + compliance status. |
| Win probability | 0–1 rollup of fit score + win/loss boosts from `analytics-service`. |
| Verdict | AI's recommended `BID` / `NO-BID` / `REVIEW` decision. |
| Bid decision | Human-recorded decision, persisted in `bid_decisions`. Gates the Draft stage. |
| Snippet | Curated boilerplate corporate response stored as a `documents` row with `category=boilerplate_snippet`. |
| Tag vocabulary | The union of all snippet `topic_tags` in a tenant — defines the universe of tags that requirements get classified against. |
