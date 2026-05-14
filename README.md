# RFP Assistant — Bid Assessment Platform

AI-driven **bid assessment scorecard** for RFP opportunities, with downstream answer drafting. Branded for Akkodis by default but tenant-generic; onboard a new customer with a seed script, not a code change.

For each incoming RFP the system produces:

- A **compliance and eligibility assessment** against the tenant's structured capability profile.
- A **best-fit analysis** matching every requirement to the tenant's service lines and products.
- A **risk register** covering commercial, delivery, legal, technical, and reputational categories.
- A rolled-up **fit score**, **win probability**, and **AI verdict** (`BID` / `NO-BID` / `REVIEW`).
- A one-page **executive summary** for the bid committee.

Answer drafting (the original product capability) remains as a downstream stage on the same RFP workspace.

---

## Quick start — demo

Prerequisites: Docker, Docker Compose, an OpenAI or Anthropic API key.

```bash
# 1. Configure an LLM key
cp .env.example .env   # then edit and set OPENAI_API_KEY (preferred) or ANTHROPIC_API_KEY

# 2. Bring up the stack
docker compose up -d
sleep 30                # wait for migrations + service warm-up

# 3. Seed the base users/products and the bid-assessment demo data
docker compose exec -T content-service python /scripts/seed_demo.py
docker compose exec -T content-service python /scripts/seed_bid_assessment_demo.py
```

Then open **http://localhost:3001** and log in with one of:

| Role | Email | Password |
|---|---|---|
| **system_admin** | `admin@demo.com` | `Demo@1234` |
| **content_admin** | `content@demo.com` | `Demo@1234` |
| **end_user** | `user@demo.com` | `Demo@1234` |

What the demo seed gives you (default tenant: **Akkodis**):

- 5-dimension capability profile — 3 industries (Banking, Healthcare, Public Sector), 3 geographies, 2 certifications (ISO 27001, SOC 2), 3 service lines (Cloud Migration, Cybersecurity Advisory, Data & Analytics).
- 8 boilerplate snippets (GDPR posture, SOC 2, ISO 27001, default SLA, MFA, data residency, escalation matrix, background screening).
- 30 past proposals across the three industries with mixed outcomes — enough volume to demo analytics aggregation; the per-pattern min-N=20 gate keeps boosts at zero until you cross the threshold (set `min_n` lower on `/score-boosts` to see the gate flip active in the admin panel).
- 5 contracts.
- 3 rich demo RFPs you can run end-to-end:
  - **Meridian Trust Bank** — Cloud Migration (matches Akkodis service line).
  - **Provincial Health Authority** — Clinical data lakehouse (matches Data & Analytics).
  - **Federal Cyber Defence Agency** — Zero-trust architecture (matches Cybersecurity Advisory).

### Use cases to try in the demo

| Use case | How to drive it |
|---|---|
| **Run an assessment** | Log in as `admin@demo.com`. Open any demo RFP. The single-page workspace shows an RFP header, an empty scorecard with a "Run assessment" button, and the legacy draft section. Click Re-run; watch the progress strip stream stage events; the scorecard fills in with compliance, eligibility, best-fit, and risks plus an LLM-generated exec summary. |
| **Edit the capability profile** | Admin → Capabilities. Add a new service line; the next assessment will consider it as a match candidate. |
| **Author a snippet** | Admin → Snippets. Create a snippet with topic tags. The retrieval RRF gives it a +0.15 category boost, and compliance items that match the tags will surface it as a "Suggested corporate response" chip. |
| **Record a past-proposal outcome** | Admin → Past proposals. Set the outcome to `won` or `lost`. The analytics aggregator counts it in the per-industry win rate. |
| **Review the learning state** | Admin → Branding (scroll down). The "Learning status" card shows every aggregated pattern with its n_total, win rate, and gate state — honest about cold start. |
| **Rebrand for a different customer** | Admin → Branding. Change `primary_color` / `accent_color` / `logo_url`. The CSS vars flip live across the app; report header/footer values feed any future PDF export. |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14, port 3001)                                │
│  RFP workspace → header · scorecard · draft section              │
│  Admin → capabilities · snippets · past-proposals · contracts ·  │
│          branding · users · companies                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ JWT (carries tenant_id)
┌──────────────────────────▼──────────────────────────────────────┐
│  api-gateway (8011 → 8000 internal)                              │
│  JWT auth · rate limits · injects X-Tenant-Id / X-User-Id /      │
│  X-User-Role from the JWT on every downstream call               │
└──────────────────────────┬──────────────────────────────────────┘
        ┌──────────────────┼──────────────────┬─────────────────┐
        │                  │                  │                 │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼────────┐  ┌─────▼─────┐
│  orchestrator │  │  rfp-service  │  │ content-service│  │capability-│
│    (8001)     │  │    (8005)     │  │    (8003)      │  │ service   │
│ BidAssessment │  │ assessment    │  │ /snippets      │  │  (8010)   │
│ Pipeline      │  │ CRUD + SSE    │  │ /past-proposals│  │ 5-dim     │
│ (5 agents)    │  │ proxy. RFP    │  │ /contracts     │  │ profile + │
│ + AgentPipe-  │  │ + answers.    │  │ +ingest+chunk  │  │ embeddings│
│ line (legacy  │  │               │  │ +category-aware│  │ + /profile│
│ /ask)         │  │               │  │ retrieval RRF  │  │ rollup    │
└──────┬────────┘  └───────────────┘  └────────────────┘  └───────────┘
       │
  ┌────┴──────────────────────────────────┐
┌─▼─────────────────────┐   ┌─────────────▼─────────────────────────┐
│  retrieval-service    │   │ analytics-service (8009)              │
│       (8002)          │   │ /score-boosts — past-proposal pattern │
│ hybrid vec + tsvector │   │ aggregation gated by min-N (default   │
│ category-weighted RRF │   │ 20). Threaded into SummaryAgent as    │
│ + tenant_id filter    │   │ analytics_boost on the win-prob math. │
└───────────────────────┘   └───────────────────────────────────────┘

  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │  rbac-service    │  │   audit-service  │  │   model-router   │
  │     (8004)       │  │      (8008)      │  │      (8006)      │
  └──────────────────┘  └──────────────────┘  └──────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │  Stores                                                    │
  │  PostgreSQL + pgvector (5432)  ·  Redis (6379)             │
  └────────────────────────────────────────────────────────────┘
```

Service count: **11**.

### The 5-agent assessment pipeline

```
        ┌─────────────────────────────────────┐
        │  Pre-run check: RFP has requirements│
        └─────────────────┬───────────────────┘
                          │
       ┌──────────────────┼───────────────────┐
       │                  │                   │
┌──────▼──────┐   ┌───────▼──────┐    ┌───────▼──────┐
│ Compliance  │   │ Eligibility  │    │   BestFit    │
│  Agent      │   │   Agent      │    │   Agent      │
│ (per req,   │   │ (bid-killers │    │ (req ↔       │
│  evidence-  │   │  vs profile) │    │  offering    │
│  backed)    │   │              │    │  matrix)     │
└──────┬──────┘   └───────┬──────┘    └───────┬──────┘
       └──────────────────┼───────────────────┘
                          │
                ┌─────────▼─────────┐
                │    Risk Agent     │
                │  (5 categories)   │
                └─────────┬─────────┘
                          │
       ┌──────────────────▼──────────────────┐
       │           Summary Agent              │
       │  fit_score, win_probability, verdict │
       │  ← analytics boost (gated)           │
       └──────────────────────────────────────┘
```

The first three agents run in parallel via `asyncio.gather`; Risk waits on all three; Summary waits on Risk. Verdict math is deterministic in code; only the exec-summary prose is LLM-generated. Partial-failure handling persists surviving outputs and degrades the verdict to `review` without crashing the run.

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `api-gateway` | 8011 → 8000 | Auth, rate limits, JWT-derived `X-Tenant-Id`/`X-User-Id`/`X-User-Role` injection |
| `orchestrator` | 8001 | `/ask` answer pipeline **plus** `/assess/run` + SSE bid-assessment pipeline |
| `retrieval-service` | 8002 | Hybrid pgvector + tsvector with RRF, category boosts, RBAC SQL predicate, tenant scoping |
| `content-service` | 8003 | Document ingest + chunk + embed; `/snippets`, `/past-proposals`, `/contracts` |
| `rbac-service` | 8004 | JWT decode, role/team resolution |
| `rfp-service` | 8005 | RFP CRUD + `/rfps/{id}/assess*` public endpoints |
| `model-router` | 8006 | Tenant model selection + adapter fallback chain |
| `adapters` | 8007 | Claude / OpenAI / Gemini / Ollama / Copilot adapters |
| `audit-service` | 8008 | Structured audit logs with key redaction |
| `analytics-service` | 8009 | `/score-boosts` per-tenant pattern aggregation + `/admin/insights` |
| `capability-service` | 8010 | 5-dimension capability profile + `/capabilities/profile` rollup |
| `frontend` | 3001 → 3000 | Next.js 14 + React + Tailwind |
| `postgres` | 5432 | Postgres 16 + pgvector |
| `redis` | 6379 | Cache/queue (used by rate limiter) |

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic.
- **Frontend:** Next.js 14 (App Router), React 18, TypeScript, Tailwind.
- **Storage:** PostgreSQL 16 with pgvector + tsvector; Redis.
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384 dims). The orchestrator deliberately omits the PyTorch/sentence-transformers stack to stay lean; the BestFit agent falls back to a token-overlap heuristic when run there.
- **LLMs:** Claude, OpenAI (GPT-4o), Gemini, Ollama, Azure OpenAI / Microsoft Copilot — all swappable per tenant.

---

## Data model (key tables)

```
tenants              — id, slug, display_name, brand JSONB, config JSONB
users                — id, email, role, tenant_id, password_hash
documents            — id, tenant_id, title, status, category (general |
                       product_doc | past_proposal | contract | boilerplate_snippet)
chunks               — id, document_id, text, embedding VECTOR(384),
                       text_search TSVECTOR, metadata JSONB
rfps                 — id, tenant_id, customer, industry, region, raw_text, status
rfp_requirements     — id, tenant_id, rfp_id, text, category, scoring_criteria JSONB
                       (scoring_criteria.tags carries the snippet-vocab tag match)

— Capability profile (per-tenant) —
service_lines        — id, tenant_id, name, description, embedding VECTOR(384)
industries           — id, tenant_id, name
geographies          — id, tenant_id, name, type
certifications      — id, tenant_id, name, issuing_body, scope, expires_at, evidence_doc_id
service_line_industries / service_line_geographies — M2M
products             — id, tenant_id, name, vendor, category (legacy)

— Hybrid KB typed entities —
past_proposals       — id, tenant_id, document_id, client_name, industry_id,
                       submitted_at, outcome (won|lost|withdrawn|pending),
                       outcome_reason, value_amount, value_currency
contracts            — id, tenant_id, document_id, client_name,
                       effective_date, expires_at, value_amount, value_currency

— Bid assessment —
bid_assessments      — id, tenant_id, rfp_id, version, status, fit_score,
                       win_probability, verdict, summary, model_version,
                       generated_by, generated_at, completed_at
compliance_items     — id, assessment_id, requirement_id, category, label,
                       mandatory, status, evidence JSONB, citations JSONB
eligibility_checks   — id, assessment_id, label, kind, expected, actual,
                       status, citations JSONB
risks                — id, assessment_id, category, title, description,
                       severity, likelihood, mitigation, citations JSONB,
                       authored_by (ai|human)
capability_matches   — id, assessment_id, requirement_id, offering_type,
                       offering_id, match_score, gap_notes
```

---

## API surface

All routes go through the `api-gateway` on port 8011 with JWT auth.

### Auth

```
POST /auth/login                         → {access_token}
GET  /auth/me                            → current user (incl. tenant_id)
POST /users                              → create user (system_admin)
GET  /tenants/me                         → current tenant + brand + config
PATCH /tenants/me/brand                  → update brand JSONB (system_admin)
```

### Capability profile

```
GET    /capabilities/profile             → 5-dimension rollup
GET    /capabilities/industries
POST   /capabilities/industries          → (content_admin+)
PATCH  /capabilities/industries/{id}
DELETE /capabilities/industries/{id}
# Same shape for /capabilities/{geographies, certifications, service-lines}
```

### Knowledge base

```
POST  /documents                         → upload PDF/DOCX, body includes category
PATCH /documents/{id}/approve            → mark for retrieval (content_admin)

POST  /snippets                          → curated boilerplate
GET   /snippets?topic=&q=
PATCH /snippets/{id}                     → bumps version, requires re-approval

POST  /past-proposals                    → typed past-proposal with outcome
PATCH /past-proposals/{id}               → set outcome / outcome_reason
GET   /past-proposals?outcome=won

POST  /contracts                         → typed contract record
GET   /contracts?expires_before=
```

### Bid assessment

```
POST /rfps/{id}/assess                   → kick off pipeline, returns the row
GET  /rfps/{id}/assess?stream=true       → SSE stream (stage, pct, complete)
GET  /rfps/{id}/assessments              → version history
GET  /rfps/{id}/assessments/latest       → latest with child rows embedded
GET  /rfps/{id}/assessments/{aid}        → specific version
```

### Analytics

```
GET /score-boosts?tenant_id=...&min_n=20  → per-pattern boost with gate state
GET /admin/insights                       → legacy win-rate dashboard
```

### Drafting (legacy, downstream of assessment)

```
POST /ask                                 → retrieve → generate → cite
POST /rfps/{id}/questions                 → add questions
POST /rfps/{id}/questions/{qid}/generate  → AI draft
PATCH /rfps/{id}/questions/{qid}/answers/{aid}  → edit with optimistic lock
POST  /rfps/{id}/outcome                  → record win/loss
```

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Secret for signing JWTs — change in production |
| `OPENAI_API_KEY` | Required to power the assessment LLM (preferred default) |
| `ANTHROPIC_API_KEY` | Alternative LLM key (Claude) |
| `GOOGLE_API_KEY` | Required if using Gemini adapter |
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI / Microsoft Copilot |
| `OLLAMA_BASE_URL` | Local Ollama URL |
| `LLM_PROVIDER` | Pin a specific provider: `openai`, `anthropic`. Default order: OpenAI → Anthropic → none. |
| `CAPABILITY_SERVICE_URL` | Override capability-service URL (default `http://capability-service:8010`) |
| `ANALYTICS_SERVICE_URL` | Override analytics-service URL (default `http://analytics-service:8009`) |
| `DEFAULT_TENANT_MODEL` | Default adapter for the legacy `/ask` answer flow |

---

## Roles

| Role | Permissions |
|------|-------------|
| `end_user` | Ask questions, create RFPs, kick off assessments, edit risks, generate draft answers |
| `content_admin` | All above + upload/approve documents, manage snippets, edit past-proposals & contracts, override compliance items |
| `system_admin` | All above + manage users, tenant branding, capability profile, view insights |

---

## Re-seeding from scratch

```bash
# Reset
docker compose down -v
docker compose up -d
sleep 30

# Migrations apply automatically when the gateway starts; if needed:
PYTHONPATH=common DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/rfpassistant' \
  alembic upgrade head

# Base users + products
docker compose exec -T content-service python /scripts/seed_demo.py

# Bid-assessment demo data
docker compose exec -T content-service python /scripts/seed_bid_assessment_demo.py
```

The demo seed is idempotent — safe to re-run; it skips rows that already exist.

---

## Project layout

```
.
├── common/                 # shared pip-installable package (db, embedder, config, tenancy)
├── docs/superpowers/
│   ├── specs/              # design docs (bid-assessment spec lives here)
│   └── plans/              # phase-by-phase implementation plans
├── frontend/               # Next.js 14
│   ├── app/(app)/rfps/[id]   # single-page RFP workspace
│   ├── app/(admin)/admin/    # capabilities, snippets, past-proposals, contracts, branding
│   ├── components/rfp/       # scorecard sub-components
│   └── components/branding/  # BrandThemeProvider
├── migrations/versions/    # alembic; current head: 0014_bid_assessments
├── scripts/                # seed_demo.py, seed_bid_assessment_demo.py
└── services/               # 11 services
    ├── api-gateway/
    ├── orchestrator/
    │   └── assessment/     # 5 agents + pipeline + SSE stream
    ├── retrieval-service/
    ├── content-service/
    ├── capability-service/ # renamed from portfolio-service in this branch
    ├── rfp-service/
    ├── analytics-service/
    ├── rbac-service/
    ├── model-router/
    ├── adapters/
    └── audit-service/
```

---

## License

MIT
