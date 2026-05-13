# Bid Assessment — Design Specification

**Date:** 2026-05-13
**Status:** Approved (auto-approved by user mid-session)
**Slug:** `bid-assessment`
**Author:** Ravi (with Claude assistance)
**Supersedes:** `2026-05-13-bid-assessment-pivot-design.md` (prior spec, retained in git history)

---

## 1. Summary

Reposition the existing RFP Assistant — today centred on retrieval and answer drafting — into a **Bid Assessment** product whose primary value is an automated, AI-driven **scorecard** for each incoming RFP. The scorecard surfaces compliance, eligibility, best-fit, and risk findings, plus a recommendation-only verdict (`BID` / `NO-BID` / `REVIEW`). Answer drafting remains, downstream of the scorecard in the same workspace.

The first deployment is branded for **Akkodis**, an IT engineering & services firm. The codebase stays generic; onboarding a new customer is a seed-script operation, not a code change.

### What's new (vs the codebase today)

1. **Bid-assessment scorecard** — compliance items, eligibility checks, capability matches, risk register, AI 1-page exec summary, rolled up into `fit_score`, `win_probability`, `verdict`.
2. **Tenant capability profile** — 5 dimensions: `service_lines`, `industries`, `geographies`, `certifications`, plus existing `products`.
3. **Hybrid knowledge base** — single `documents`/`chunks` table for retrieval **plus** typed entity tables (`past_proposals`, `contracts`) for structured queries.
4. **Snippet library** — curated boilerplate corporate responses with in-app CRUD, retrieval-boosted, surfaced as evidence on compliance items.
5. **Gated learning loop** — retrieval boost from won proposals (works at small N) plus `analytics-service` aggregation **gated by per-tenant min-N=20** before any learned threshold adjustment ships into the verdict.
6. **Single-page RFP workspace** — header, scorecard, draft section.
7. **First-class multi-tenancy** — reuses existing `tenants` table (migrations 0009/0010); all data carries `tenant_id`.
8. **`portfolio-service` → `capability-service` rename** — broadens scope from products to the full capability profile.

### What stays unchanged

- Hybrid pgvector + tsvector retrieval with RRF (k=60).
- RBAC enforced as SQL predicate.
- The typed-agent base in `services/orchestrator/agents.py`.
- The 11-service deployment topology.
- Win/loss boost machinery in `analytics-service` (migration 0006).

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Ship an Akkodis-branded bid-assessment workflow end-to-end on Docker Compose.
- Keep the codebase tenant-generic; onboarding a new customer is a seed-script operation.
- Preserve the existing answer-drafting flow as a downstream feature; no functional regression for seeded RFPs.
- Provide a structured, audit-friendly trail of every assessment run.

### 2.2 Non-Goals (v1)

- No formal `bid_decisions` table; no gating of the draft stage. The AI verdict is recommendation-only.
- No PDF or DOCX export.
- No tenant self-signup or in-product tenant creation.
- No per-tenant Postgres schema; single shared schema with `tenant_id` filtering.
- No background job queue; assessments are synchronous server-side, SSE-streamed to the client.
- No real-time multi-user editing on the scorecard.
- No external KB connectors (SharePoint, Confluence, Salesforce).
- No automatic snippet generation from past proposals.
- No multilingual snippets / report templates.
- No backwards-compatibility shim for `/portfolio/*` routes — one-shot rename.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  frontend (3000)                                             │
│  /rfps/{id} — single-page workspace:                         │
│    [Header]  [Scorecard]  [Draft section]                    │
│  /admin/capabilities  /admin/snippets                        │
│  /admin/past-proposals  /admin/contracts  /admin/branding    │
└──────────────────────────┬──────────────────────────────────┘
                           │ JWT (carries tenant_id)
┌──────────────────────────▼──────────────────────────────────┐
│  api-gateway (8000) — auth, tenant resolution, proxy         │
└──────────────────────────┬──────────────────────────────────┘
        ┌──────────────────┼─────────────────────────┐
        │                  │                         │
┌───────▼───────┐  ┌───────▼───────┐  ┌──────────────▼─────────────┐
│ orchestrator  │  │  rfp-service  │  │  content-service           │
│   (8001)      │  │    (8005)     │  │    (8003)                  │
│ AgentPipeline │  │ RFP CRUD,     │  │ ingest, chunk, embed,      │
│ BidAssessment │  │ assessment    │  │ approve. + `category` enum │
│ Pipeline NEW  │  │ CRUD NEW,     │  │ + snippet-aware chunker    │
│ (5 agents)    │  │ past-prop +   │  │ + past_proposals &         │
│               │  │ contracts CRUD│  │   contracts entity write   │
└──────┬────────┘  └───────────────┘  └────────────────────────────┘
       │
  ┌────┴──────────────────────────────┐
  │                                   │
┌─▼─────────────────┐    ┌────────────▼────────────────────────┐
│ retrieval-service │    │ capability-service ★ RENAMED         │
│     (8002)        │    │   (8010, was portfolio-service)      │
│ hybrid + RBAC +   │    │ products, service_lines, industries, │
│ tenant_id +       │    │ geographies, certifications          │
│ category-weighted │    │ + coverage matrix                    │
│ RRF (+ snippet    │    │ + capability-vs-RFP scoring          │
│  boost + win-loss │    │                                      │
│  boost)           │    │                                      │
└───────────────────┘    └──────────────────────────────────────┘

┌──────────────────────────┐  ┌──────────────────────────┐
│  model-router (8006)     │  │  rbac-service (8004)     │
└──────────────────────────┘  └──────────────────────────┘
┌──────────────────────────┐  ┌──────────────────────────┐
│  audit-service (8008)    │  │  analytics-service (8009)│
│                          │  │  aggregates win/loss     │
│                          │  │  patterns; emits boosts  │
│                          │  │  gated by min-N=20       │
└──────────────────────────┘  └──────────────────────────┘

Service count: 11 (unchanged).
```

**Key points:**
- No new services. One rename. All other changes are extensions.
- `tenant_id` is on every tenant-scoped table and passed in every cross-service call.
- The existing typed-agent base in `services/orchestrator/agents.py` is reused; `BidAssessmentPipeline` lives alongside the existing answer pipeline and shares zero mutable state.
- Migrations 0009/0010 (tenants) are already in the codebase — reused as-is.

---

## 4. Data Model

### 4.1 Already in the codebase

Reused, not modified:
- `tenants` (slug, display_name, brand JSONB, config JSONB) — migrations 0009/0010.
- `users.tenant_id` FK.
- `tenant_id` columns on existing tenant-scoped tables.
- `documents`, `chunks`, `rfps`, `requirements`, `answers`.
- Win/loss boost table (migration 0006).

### 4.2 Documents extension (`0011_documents_category.py`)

```sql
ALTER TABLE documents ADD COLUMN category VARCHAR NOT NULL DEFAULT 'general';
-- enum: general | product_doc | past_proposal | contract | boilerplate_snippet
ALTER TABLE documents ADD CONSTRAINT documents_category_check
  CHECK (category IN ('general','product_doc','past_proposal','contract','boilerplate_snippet'));
CREATE INDEX idx_documents_tenant_category ON documents(tenant_id, category);
```

Existing rows backfill to `general`. Per-category metadata stays in the existing `metadata JSONB`.

### 4.3 Capability profile (`0012_capability_profile.py`)

All tables carry `id UUID PK`, `tenant_id UUID NOT NULL FK`, `created_at TIMESTAMPTZ DEFAULT now()`.

| Table | Key columns | Notes |
|---|---|---|
| `service_lines` | `name, description, parent_id NULL, embedding VECTOR(384)` | Self-referential hierarchy; embedding used by BestFitAgent |
| `industries` | `name (UNIQUE per tenant)` | Flat |
| `geographies` | `name, type ENUM(country,region,city), parent_id NULL` | Self-referential |
| `certifications` | `name, issuing_body, scope, expires_at DATE NULL, evidence_doc_id UUID NULL FK→documents` | Evidence PDF link |
| `service_line_industries` | composite PK `(service_line_id, industry_id)` | M2M |
| `service_line_geographies` | composite PK `(service_line_id, geography_id)` | M2M |

The existing `products` table is retained — valid offering type for tenants that are software vendors.

### 4.4 Typed entity tables (`0013_typed_entities.py`)

```sql
past_proposals (
  id UUID PK, tenant_id UUID NOT NULL,
  document_id UUID NOT NULL FK → documents,
  client_name VARCHAR,
  industry_id UUID NULL FK → industries,
  submitted_at DATE NOT NULL,
  outcome VARCHAR NOT NULL DEFAULT 'pending'
    CHECK (outcome IN ('won','lost','withdrawn','pending')),
  outcome_reason TEXT NULL,
  value_amount NUMERIC NULL, value_currency CHAR(3) NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

contracts (
  id UUID PK, tenant_id UUID NOT NULL,
  document_id UUID NOT NULL FK → documents,
  client_name VARCHAR NOT NULL,
  effective_date DATE NOT NULL,
  expires_at DATE NULL,
  value_amount NUMERIC NULL, value_currency CHAR(3) NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_past_proposals_tenant_outcome ON past_proposals(tenant_id, outcome);
CREATE INDEX idx_contracts_tenant_expires ON contracts(tenant_id, expires_at);
```

Each row references its underlying `documents` row, so retrieval flows through the unified chunks pipeline. Typed columns enable SQL queries like "all won proposals in healthcare in the last 2 years."

### 4.5 Bid assessment (`0014_bid_assessments.py`)

```sql
bid_assessments (
  id UUID PK, tenant_id UUID NOT NULL, rfp_id UUID NOT NULL FK,
  version INT NOT NULL DEFAULT 1,
  status VARCHAR NOT NULL CHECK (status IN ('running','complete','partial','failed')),
  fit_score NUMERIC NULL,           -- 0–1
  win_probability NUMERIC NULL,     -- 0–1
  verdict VARCHAR NULL CHECK (verdict IN ('bid','no_bid','review')),
  summary TEXT NULL,                -- AI-generated 1-page exec summary
  model_version VARCHAR NOT NULL,
  generated_by UUID FK → users,
  generated_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ NULL,
  UNIQUE (rfp_id, version)
);

compliance_items (
  id UUID PK, assessment_id UUID NOT NULL FK,
  requirement_id UUID NULL FK → requirements,
  category VARCHAR CHECK (category IN ('security','privacy','operational','commercial','legal','other')),
  label VARCHAR, mandatory BOOL,
  status VARCHAR CHECK (status IN ('pass','fail','partial','unknown')),
  evidence JSONB,
  citations JSONB
);

eligibility_checks (
  id UUID PK, assessment_id UUID NOT NULL FK,
  label VARCHAR,
  kind VARCHAR CHECK (kind IN ('geography','contract_vehicle','certification','financial','exclusion','other')),
  expected VARCHAR, actual VARCHAR,
  status VARCHAR CHECK (status IN ('pass','fail','partial','unknown')),
  citations JSONB
);

risks (
  id UUID PK, assessment_id UUID NOT NULL FK,
  category VARCHAR CHECK (category IN ('commercial','delivery','legal','technical','reputational')),
  title VARCHAR, description TEXT,
  severity VARCHAR CHECK (severity IN ('low','medium','high')),
  likelihood VARCHAR CHECK (likelihood IN ('low','medium','high')),
  mitigation TEXT NULL,
  citations JSONB,
  authored_by VARCHAR DEFAULT 'ai' CHECK (authored_by IN ('ai','human'))
);

capability_matches (
  id UUID PK, assessment_id UUID NOT NULL FK,
  requirement_id UUID NOT NULL FK → requirements,
  offering_type VARCHAR CHECK (offering_type IN ('service_line','product')),
  offering_id UUID NULL,
  match_score NUMERIC,
  gap_notes TEXT NULL
);
```

`version` enables re-runs without destroying history. Optimistic-lock for child PATCHes: `If-Match: <version>`; 409 on mismatch.

**Explicitly out vs. prior spec:** no `bid_decisions` (recommendation only), no `assessment_exports` (scorecard only).

### 4.6 Migration ordering

| # | File | Adds |
|---|---|---|
| 0011 | `documents_category.py` | category column + index |
| 0012 | `capability_profile.py` | 4 new tables + 2 M2M |
| 0013 | `typed_entities.py` | `past_proposals`, `contracts` |
| 0014 | `bid_assessments.py` | 5 assessment tables |

Each is reversible; `scripts/test_workflows.py` runs `upgrade head → downgrade base → upgrade head` after every phase.

---

## 5. Bid Assessment Pipeline

### 5.1 DAG

```
        ┌────────────────────────────┐
        │  Pre-run: RFP has          │
        │  requirements rows         │
        │  (extraction done)         │
        └─────────────┬──────────────┘
                      │
        ┌─────────────┼──────────────┐
        │             │              │
┌───────▼──────┐ ┌────▼──────┐ ┌─────▼────────┐
│ Compliance   │ │Eligibility│ │  BestFit     │
│ Agent        │ │ Agent     │ │  Agent       │
└──────┬───────┘ └────┬──────┘ └─────┬────────┘
       └──────────────┼──────────────┘
                      │
            ┌─────────▼─────────┐
            │   Risk Agent      │
            └─────────┬─────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Summary Agent             │
        │  ← reads analytics boosts   │
        │    only when min-N met      │
        └─────────────────────────────┘
                      │
            ┌─────────▼──────────┐
            │bid_assessments row │
            │ + child rows       │
            └────────────────────┘
```

The first three agents run in parallel via `asyncio.gather`. Risk waits on all three. Summary waits on Risk.

### 5.2 Agent contracts

| Agent | Input | Output | Reads from |
|---|---|---|---|
| **ComplianceAgent** | `rfp_id, requirements[], tenant_id` | `ComplianceItem[]` | `retrieval-service` (approved docs, snippets, won past_proposals — category-weighted RRF) |
| **EligibilityAgent** | `rfp_id, raw_text, tenant_id` | `EligibilityCheck[]` | `capability-service` (structured profile fields) |
| **BestFitAgent** | `requirements[], tenant_id` | `CapabilityMatch[]` | `capability-service` (embeddings on `service_lines` + `products`) |
| **RiskAgent** | `raw_text, requirements[], compliance[], eligibility[], best_fit[]` | `Risk[]` across 5 categories | LLM only |
| **SummaryAgent** | All prior outputs + tenant config thresholds + analytics boosts (if min-N met) | `AssessmentRollup` | `analytics-service`; tenant config |

Each inherits the existing `TypedAgent[InputSchema, OutputSchema]` base. **Pipeline owns DB writes; agents are pure functions over data.**

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
    evidence: dict   # {kind, ref_id, excerpt}
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
    match_score: float
    gap_notes: str | None

class AssessmentRollup(BaseModel):
    fit_score: float
    win_probability: float
    verdict: Literal["bid","no_bid","review"]
    summary: str
```

### 5.4 Pipeline-level concerns

- **Execution.** Synchronous server-side `asyncio` orchestration. SSE stream emits `stage`, `agent`, `pct`, optional `error`.
- **Re-runs.** New row, `version = previous + 1`. UI shows latest by default; history dropdown for prior runs.
- **Partial failure.** Failure in any parallel agent persists surviving outputs and sets `status='partial'`. Risk runs against available data. Summary degrades to `verdict='review'` and notes the gap in `summary`. Risk/Summary failures leave `status='failed'` with surviving rows intact.
- **Idempotency.** New runs never delete prior rows; child rows are owned by their `assessment_id`.
- **Determinism for tests.** Agents take a mockable LLM client. Pipeline tests use stub agents returning canned outputs.
- **Audit.** Every agent invocation produces an `audit_logs` entry with existing redaction rules.
- **Disconnect.** SSE drop does not cancel server-side work. Reconnect via `GET /rfps/{id}/assess?stream=true` replays buffered events from a small in-memory ring buffer keyed by `(rfp_id, version)`, then resumes live.
- **Verdict math (deterministic part).** `fit_score` = weighted mean of `match_score` over capability_matches (weight = `requirement.weight` if present else 1). `win_probability = fit_score * (1 - mandatory_failure_penalty) * (1 + analytics_boost_if_gated)`. `verdict` thresholds from tenant config (defaults: `bid_min_fit=0.70`, `no_bid_max_fit=0.40`, else `review`). Summary prose from the LLM.

---

## 6. API Surface

All routes via `api-gateway` (8000); JWT carries `tenant_id`, every downstream service filters all queries on it.

### 6.1 Tenants & branding

| Method | Path | Role |
|---|---|---|
| GET | `/tenants/me` | any |
| PATCH | `/tenants/me/brand` | system_admin |

### 6.2 Capabilities

```
/capabilities/products            (existing, renamed from /portfolio/products)
/capabilities/service-lines       NEW
/capabilities/industries          NEW
/capabilities/geographies         NEW
/capabilities/certifications      NEW
```

Standard CRUD on each (`GET /…`, `POST /…`, `GET /…/{id}`, `PATCH /…/{id}`, `DELETE /…/{id}`).

Plus `GET /capabilities/profile` — rollup of all 5 dimensions.

Writes: `content_admin` or `system_admin`. Reads: any authenticated user.

### 6.3 Documents, snippets, typed entities

```
POST  /documents               body includes: category, metadata.*
GET   /documents?category=…&limit=…
```

Snippets (façade over `documents` rows with `category=boilerplate_snippet`):

| Method | Path | Role |
|---|---|---|
| POST | `/snippets` | content_admin (auto-approve), end_user (pending) |
| GET | `/snippets?topic=…&q=…` | any |
| PATCH | `/snippets/{id}` | content_admin |
| DELETE | `/snippets/{id}` | content_admin (soft-delete → `archived`) |

Typed entities:

```
POST  /past-proposals     body: {document_upload | document_id, client_name, industry_id, submitted_at, value}
PATCH /past-proposals/{id}  body: {outcome, outcome_reason, ...}
GET   /past-proposals?outcome=won&industry_id=…
POST  /contracts          body: {document_upload | document_id, client_name, effective_date, expires_at, value}
GET   /contracts?expires_before=2026-12-31
```

### 6.4 Bid assessment

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/rfps/{id}/assess` | end_user+ | Kick off pipeline; returns `{assessment_id, version, status:"running"}` |
| GET | `/rfps/{id}/assess?stream=true` | end_user+ | SSE stream; 404 if no run currently `running` |
| GET | `/rfps/{id}/assessments` | end_user+ | History |
| GET | `/rfps/{id}/assessments/latest` | end_user+ | Convenience |
| GET | `/rfps/{id}/assessments/{aid}` | end_user+ | Full assessment with child rows |
| PATCH | `/rfps/{id}/assessments/{aid}/compliance/{cid}` | content_admin+ | Requires `If-Match: <version>` |
| PATCH | `/rfps/{id}/assessments/{aid}/risks/{rid}` | end_user+ | Edit risk |
| POST | `/rfps/{id}/assessments/{aid}/risks` | end_user+ | Add human-authored risk |
| DELETE | `/rfps/{id}/assessments/{aid}/risks/{rid}` | end_user+ | Remove |

**Note:** no `bid-decision` endpoints; no `export` endpoints.

### 6.5 Conventions

- Lists: `?limit` (≤100, default 20), `?offset`, `?q`.
- Assessment-child mutations require `If-Match: <version>`; 409 on mismatch.
- Mutation responses return the persisted row.
- Error shape: `{detail, code}`.

### 6.6 Breaking changes (one-shot)

| Old | New |
|---|---|
| `PORTFOLIO_SERVICE_URL` | `CAPABILITY_SERVICE_URL` |
| `/portfolio/products` | `/capabilities/products` |

No deprecation window — single migration commit.

---

## 7. Frontend Workflow & UI

### 7.1 Workspace shape — single page

`frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` is restructured into one scrollable page with three vertically stacked sections:

```
┌─────────────────────────────────────────────────┐
│  RFP Header                                      │
│  title • client • due date • status • actions    │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Scorecard                                       │
│  ┌─────────────────────────────────────────┐    │
│  │ Verdict + fit + win prob + Re-run btn   │    │
│  └─────────────────────────────────────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────┐  │
│  │Compliance│ │Eligibility│ │ Best-Fit │ │Risk│  │
│  │  panel   │ │   panel   │ │  matrix  │ │ list│  │
│  └──────────┘ └──────────┘ └──────────┘ └────┘  │
│  Exec summary (markdown)                         │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Draft section (existing answer-drafting UI)     │
└─────────────────────────────────────────────────┘
```

No gating, no stepper. The draft section is always visible (recommendation-only).

### 7.2 Component tree

```
frontend/components/
├── rfp/
│   ├── RFPHeader.tsx
│   ├── AssessmentScorecard.tsx
│   ├── ScoreRollupHeader.tsx       (fit + win prob + AI verdict + Re-run)
│   ├── CompliancePanel.tsx
│   ├── EligibilityPanel.tsx
│   ├── BestFitMatrix.tsx           (heat map: requirement × offering)
│   ├── RiskRegister.tsx            (editable)
│   ├── ExecSummaryCard.tsx         (rendered markdown + regen)
│   ├── AssessmentHistoryMenu.tsx
│   └── DraftSection.tsx            (extracted from existing RFPWorkspace)
├── capability/
│   ├── CapabilityProfileAdmin.tsx
│   └── CapabilityDimensionTable.tsx
├── snippets/
│   └── SnippetLibraryAdmin.tsx
├── past_proposals/
│   └── PastProposalsAdmin.tsx
├── contracts/
│   └── ContractsAdmin.tsx
└── branding/
    └── BrandThemeProvider.tsx
```

`RFPWorkspace.tsx` becomes a thin orchestrator: fetches RFP + latest assessment, owns the SSE connection during a run.

### 7.3 New admin pages

| Route | Role |
|---|---|
| `/admin/capabilities` | content_admin+ |
| `/admin/snippets` | content_admin+ |
| `/admin/past-proposals` | content_admin+ |
| `/admin/contracts` | content_admin+ |
| `/admin/branding` | system_admin |

The existing `/ask` page stays as a side feature; nav demotes it below RFPs.

### 7.4 SSE consumption

```ts
// frontend/lib/useAssessmentStream.ts
function useAssessmentStream(rfpId: string, assessmentId: string | null) {
  // returns { progress, currentAgent, error, isComplete, assessment }
}
```

`AssessmentScorecard` shows an inline 5-step progress strip during the run; on `isComplete`, refetches via `GET /rfps/{id}/assessments/latest`.

### 7.5 Branding

`BrandThemeProvider` wraps the existing `ThemeProvider`, fetches `/tenants/me` once after auth, sets:

```css
:root {
  --brand-primary: <tenant.brand.primary_color>;
  --brand-accent:  <tenant.brand.accent_color>;
}
```

Logo + display name surface in `AppShell`.

---

## 8. Snippet Library Mechanics

### 8.1 Storage

Physically `documents` rows with `category=boilerplate_snippet`. Metadata: `{topic_tags: string[], version: int, approved_by: uuid|null}`.

### 8.2 Lifecycle

- **Author.** `POST /snippets {title, body, topic_tags}` → `documents` row, `status=pending_approval`, `metadata.version=1`.
- **Auto-approve.** If author has `content_admin`/`system_admin`, handler sets `status=approved` on create.
- **Versioning.** `PATCH /snippets/{id}` increments `metadata.version`, rewrites body, resets `status=pending_approval`.
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
            + winloss_boost(chunk)
```

`category_boost` and `topic_tag_boost` values come from tenant config (see §9.4).

### 8.5 Tag classification

`ExtractionAgent` emits a `tags[]` array on each requirement, classified against the **union of all snippet `topic_tags` in the current tenant** (fetched fresh per extraction run). Vocabulary is defined by the snippet library itself.

### 8.6 Surface in ComplianceAgent

```python
ComplianceItem(
    status="pass",
    evidence={"kind": "snippet", "ref_id": "<uuid>", "excerpt": "<first 240 chars>"},
    citations=[Citation(...)],
)
```

UI renders these as **"Suggested corporate response"** chips. One-click action: **Insert into draft** — pre-fills the answer textarea in the draft section.

---

## 9. Tenancy & Branding Config

### 9.1 Runtime tenant resolution

`api-gateway/auth.py` decodes the JWT, loads `users.tenant_id`, attaches it to `request.state`. Every downstream service receives `tenant_id` in the call and filters all queries on it.

```python
# common/tenancy.py  (new)
def tenant_scope(query, tenant_id, table):
    return query.where(table.c.tenant_id == tenant_id)
```

Code-review rule: any query touching a tenant-scoped table without this helper is a leak. The integration test in §11.2 catches violations.

### 9.2 Seeding model

```
scripts/
├── seed_demo.py              # refactored to invoke seed_tenant
├── seed_tenant.py            # NEW
└── seeds/
    ├── akkodis/
    │   ├── tenant.yaml
    │   ├── service_lines.yaml
    │   ├── industries.yaml
    │   ├── geographies.yaml
    │   ├── certifications.yaml
    │   ├── products.yaml
    │   ├── snippets/
    │   │   ├── gdpr.md
    │   │   ├── soc2.md
    │   │   └── sla_defaults.md
    │   ├── past_proposals/    # optional seed past proposals
    │   ├── contracts/         # optional seed contracts
    │   └── brand/
    │       └── logo.svg
    └── _example/              # template for future customers
```

`seed_tenant.py akkodis` is idempotent (uses `slug` as natural key), upserts, embeds. Onboarding: copy `_example/`, edit, commit, run.

Snippet markdown files have YAML front-matter capturing `topic_tags` and approval status.

### 9.3 Brand asset storage

Logo files on a local volume `/var/brand/<tenant-slug>/logo.svg`, served by `api-gateway` as static. Phase-2: swap to S3/Azure Blob is one adapter.

### 9.4 Effective config

```python
effective_config = deep_merge(tenants.config, users.tenant_config)
```

Default tenant `config`:

```jsonc
{
  "retrieval": {
    "category_boosts": {
      "boilerplate_snippet": 0.15,
      "past_proposal_won":   0.10,
      "past_proposal_lost":  0.02,
      "contract":            0.05,
      "product_doc":         0.00,
      "general":             0.00
    },
    "rbac_strict": true
  },
  "assessment": {
    "verdict_thresholds": { "bid_min_fit": 0.70, "no_bid_max_fit": 0.40 },
    "mandatory_failure_penalty": 0.30,
    "analytics_min_n": 20
  }
}
```

### 9.5 RBAC composes with tenancy

```sql
WHERE metadata->>'approved' = 'true'
  AND tenant_id = :current_tenant            -- isolation (cross-customer)
  AND (role-filter on metadata->>'allowed_roles')   -- authorization (within-customer)
  AND (team-filter on metadata->>'allowed_teams')
```

---

## 10. Analytics-Service Learning Loop

### 10.1 Inputs

- `past_proposals` rows with `outcome ∈ {won, lost, withdrawn}`.
- Reference RFPs (the proposals' source RFPs) and their captured requirement tags, industry, geography, value bucket.

### 10.2 Aggregation

Daily job (or on-write trigger) computes per-tenant patterns:

```
Pattern key = (tenant_id, industry_id, has_cert(soc2)?, has_cert(iso27001)?, value_bucket)
Pattern stats = (n_total, n_won, win_rate, mean_fit_at_submit)
```

A pattern emits a learned `score_boost` only when `n_total >= analytics_min_n` (default 20).

### 10.3 Output

`analytics-service` exposes `GET /score-boosts?tenant_id=…` returning a list of `(pattern_key, boost_value, n_total)`. SummaryAgent multiplies `win_probability` by `(1 + boost)` for matching patterns.

### 10.4 Admin visibility

`/admin/branding` includes a read-only "Learning status" card: which patterns are active, which are below the N gate. Honest about cold-start; nothing hidden.

---

## 11. Migration & Rollout

### 11.1 Phasing

Five mergeable phases. Each ships with its own migrations, tests, and demo affordance.

| # | Phase | New tables | Demo affordance after |
|---|---|---|---|
| 1 | Capability service rename + new dimensions | 4 + 2 M2M | Admin can edit Akkodis service lines/certs/etc.; `/portfolio/*` → `/capabilities/*` |
| 2 | KB extensions (category + typed entities + snippets) | 2 (`past_proposals`, `contracts`) | Snippets searchable; past proposals/contracts admin UIs work |
| 3 | Bid Assessment core | 5 | `POST /rfps/{id}/assess` returns a full assessment |
| 4 | Frontend single-page workspace | 0 | RFP workspace shows scorecard + draft inline |
| 5 | Analytics gated learning loop | 0 | Score-boosts honored; admin sees gate status |

Phases 1–2 are foundation; 3 is the headline; 4 is the user-facing payoff; 5 is the closing loop.

### 11.2 Testing

- **Agent unit tests.** Stub LLM client; assert each agent's output schema for canned inputs.
- **Pipeline test.** Stub all five agents; verify orchestration and DB persistence end-to-end.
- **Tenancy leak test.** Two tenants (`akkodis`, `widgetco`); seed each with an RFP; run assessments; assert no row from one ever appears in the other's queries across every service.
- **Migration test.** `scripts/test_workflows.py` adds: clean DB → `upgrade head` → `downgrade base` → `upgrade head`.
- **Frontend.** Component tests for new scorecard components + `useAssessmentStream`.
- **Manual demo.** Akkodis seed runs end-to-end on seeded RFPs and produces coherent assessments.

### 11.3 Branching

- Feature branch: `feat/bid-assessment` off `master`.
- One sub-branch per phase, merged into the long-lived branch when its demo affordance works.
- Merge to `master` only when all five phases pass end-to-end on the Akkodis seed.

### 11.4 Rollback

- Every alembic migration is reversible; `scripts/test_workflows.py` verifies.
- Code rollback = revert the merge commit.

### 11.5 Documentation outputs

- README rewrite: lead with "Bid Assessment" as the primary value prop; answer drafting becomes a downstream feature.
- `spec.md` adds a "Bid Assessment Pipeline" section + new tables.
- New `docs/onboarding-new-tenant.md`: one-page playbook.

---

## 12. Decisions Log

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Product framing | B — reposition; bid assessment is headline | User explicit; "reposition the product" |
| 2 | Decision flow | A — recommendation only, no gating | Reduces UI friction; honest about AI suggestion vs. human authority |
| 3 | Capability profile | B — 5 dimensions (service lines, industries, geographies, certifications, products) | Smallest profile that moves eligibility out of LLM guesswork without commercial layer |
| 4 | Pipeline shape | B — 5 per-area agents | Best tuning surface; partial-failure recovery |
| 5 | "Plugins" | A — snippet library | Brief language matches snippet model; lightest interpretation |
| 6 | KB structure | C — hybrid (single docs/chunks + typed entities) | Structured queries on past proposals & contracts without two retrieval pipelines |
| 7 | Learning loop | A — full loop, gated by min-N=20 per pattern | Architecture in place day-1 without faking signal on cold start |
| 8 | Output | A — scorecard only | No PDF/DOCX in v1 |
| 9 | Topology | A — rename to `capability-service` | Right name; cost of rename worth paying now |
| 10 | Runtime UX | B — SSE | Matches existing pattern; no queue infrastructure |
| 11 | Workspace UI | A — single page | Scorecard is the headline visually; no stepper |
| 12 | Snippet authoring | A — in-app CRUD | Bid desk owns content |

---

## 13. Open Questions / Phase-2 Backlog

Deferred. Each is a candidate for a future spec.

- Automatic snippet generation from past proposals.
- Snippet templating with variables (`{{customer_name}}`).
- Multilingual snippets + report templates.
- External KB plugin connectors (SharePoint, Confluence, Salesforce).
- Real-time multi-user editing on the scorecard.
- S3 / Azure Blob storage adapter for brand assets.
- Background-job queue for long-running assessments.
- Tenant self-signup + in-product tenant creation.
- Per-tenant Postgres schema migration path.
- Mobile-first UI.
- Telemetry / observability (Prometheus, OTel).
- CI/CD pipeline.
- PDF/DOCX export.
- Formal bid/no-bid decision + draft gating.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| Capability profile | The tenant's "what we can deliver": service lines, industries, geographies, certifications, products. |
| Compliance item | "Does our content show we comply with this clause?" — produced by `ComplianceAgent`, one per requirement. |
| Eligibility check | "Are we even allowed to bid?" — bid-killers (geography, certs, financial thresholds, exclusions). |
| Best-fit match | A `(requirement, offering)` pair with a similarity score and optional gap note. |
| Fit score | 0–1 rollup of capability matches weighted by requirement weight. |
| Win probability | 0–1 = `fit_score × (1 − mandatory_failure_penalty) × (1 + analytics_boost_if_gated)`. |
| Verdict | AI's recommended `BID` / `NO-BID` / `REVIEW`. Recommendation only; no gating in v1. |
| Snippet | Curated boilerplate corporate response as a `documents` row with `category=boilerplate_snippet`. |
| Tag vocabulary | Union of all snippet `topic_tags` in a tenant — defines the universe of tags requirements get classified against. |
| Min-N gate | Per-tenant per-pattern threshold (default 20) below which `analytics-service` emits no learned boost. |
