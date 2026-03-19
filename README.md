# RFP Assistant (Keystone)

A model-agnostic RFP assistant that retrieves permission-scoped enterprise content and generates compliant, citation-backed answers. Supports Claude, Gemini, Ollama, and Microsoft Teams Copilot through a unified adapter layer.

## Architectural Overview

RFP Assistant is a multi-service system built around a request pipeline that enforces RBAC at the database layer before any content reaches the model. The high-level flow is:

1. A user submits a question (via the web UI, REST API, or Teams) to the **API Gateway**, which validates the JWT and enforces rate limits.
2. The **Orchestrator** receives the authenticated request and runs the `POST /ask` pipeline: retrieve → rank → generate → assemble.
3. The **Retrieval Service** executes a hybrid vector + full-text search against Postgres (pgvector + tsvector), fused with Reciprocal Rank Fusion. RBAC predicates are applied as SQL `WHERE` clauses — filtered content never leaves the database.
4. The **Model Router** selects the configured adapter (Claude, Gemini, or Ollama) for the tenant and calls it with a structured prompt. A fallback chain is configured per tenant.
5. The **Response Assembler** wraps the model output with citations, a confidence score, and (when applicable) a partial-compliance notice.
6. Every call is logged to `audit_logs` via the **Audit Service** as a background task, with sensitive keys redacted.

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                             │
│         Next.js 14 UI (3000)   ·   Teams Copilot Adapter (8009) │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS / JWT
┌──────────────────────────▼──────────────────────────────────────┐
│  API Gateway (8000)                                             │
│  JWT auth · rate limiting · user management · RBAC middleware   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼───────┐  ┌───────▼───────┐  ┌───────▼───────┐
│  Orchestrator │  │  RFP Service  │  │Content Service│
│    (8001)     │  │    (8005)     │  │    (8003)     │
│ /ask pipeline │  │ CRUD, answers │  │ ingest, chunk │
│ multi-agent   │  │ versioning    │  │ embed, approve│
└──────┬────────┘  └───────────────┘  └───────────────┘
       │
  ┌────┴─────────────────────────────────┐
  │                                      │
┌─▼──────────────────┐   ┌──────────────▼──────────────┐
│  Retrieval Service │   │       Model Router           │
│      (8002)        │   │          (8006)              │
│ hybrid vector+FTS  │   │ tenant config, adapter select│
│ RRF reranking      │   │ primary + fallback chain     │
│ RBAC SQL predicate │   └──────────────┬───────────────┘
└────────────────────┘                  │
                            ┌───────────┼───────────┐
                      ┌─────▼──┐  ┌────▼───┐  ┌────▼────┐
                      │ Claude │  │Gemini  │  │ Ollama  │
                      └────────┘  └────────┘  └─────────┘

  ┌─────────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │  RBAC Service   │   │  Audit Service   │   │Analytics Service │
  │    (8004)       │   │    (8008)        │   │    (8009)        │
  │ JWT decode,     │   │ structured logs, │   │ win/loss,        │
  │ role/team res.  │   │ key redaction    │   │ insights API     │
  └─────────────────┘   └──────────────────┘   └──────────────────┘

  ┌────────────────────────────────────────────────────────────────┐
  │  Portfolio Service (8010)                                      │
  │  product embeddings · coverage matrix · gap detection          │
  └────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────┐
  │  Stores                                                        │
  │  PostgreSQL + pgvector (5432)  ·  Redis (6379)                 │
  └────────────────────────────────────────────────────────────────┘
```

### Technical Overview for Developers

#### Language & Framework
All backend services are Python 3.12 with FastAPI and SQLAlchemy 2.x async. The frontend is Next.js 14 (App Router) with TypeScript and Tailwind CSS.

#### Shared Package (`common/`)
The `common/` directory is a pip-installable package with:
- `common.config` — `BaseSettings` subclass shared by all services
- `common.db` — async engine + session factory (`create_async_engine`, `async_sessionmaker`)
- `common.embedder` — `EmbedderInterface` ABC; concrete `SentenceTransformerEmbedder` (`all-MiniLM-L6-v2`, 384 dims)
- `common.logging` — structured JSON logger

All services copy the `common/` directory into their Docker image and `pip install /common` at build time.

#### Embedding Model
`sentence-transformers/all-MiniLM-L6-v2` (384-dimension vectors). Used in content-service (chunk embedding), retrieval-service (query embedding), and portfolio-service (product embedding). PyTorch is installed CPU-only to avoid the 6 GB CUDA download.

#### Retrieval Pipeline (retrieval-service)
1. `vector_search` — cosine similarity via `<=>` operator on `chunks.embedding VECTOR(384)`
2. `keyword_search` — `plainto_tsquery` on `chunks.text_search TSVECTOR`
3. `reciprocal_rank_fusion` — RRF (k=60) merges the two ranked lists
4. `rbac_filter` — all queries include `WHERE metadata->>'approved' = 'true' AND (role filter)`

#### RBAC Enforcement
Permissions are checked in two places:
- **FastAPI dependency** (`require_role`) — HTTP 403 for wrong role
- **SQL predicate** — `chunks.metadata JSONB` contains `allowed_roles` and `allowed_teams`; the retrieval query filters on these columns so the model never sees non-permitted content

#### Agent Pipeline (orchestrator)
`AgentPipeline` runs typed agents sequentially. Each agent defines `InputSchema` and `OutputSchema` (Pydantic models). The pipeline passes validated output from one agent as input to the next:

```
IngestionAgent → ExtractionAgent → GenerationAgent → QuestionnaireAgent
```

#### Adaptive Disclosure
If `mean_score < 0.4` or fewer than 2 chunks are retrieved, the response assembler prepends a partial-compliance notice and sets `partial_compliance: true` on the answer.

#### Optimistic Locking (rfp-service)
`rfp_answers.version` is an integer. `PATCH /rfps/{id}/questions/{qid}/answers/{aid}` requires the client to send the current version; the update uses `WHERE id = :aid AND version = :v`. If the row was modified concurrently, 0 rows are updated and the endpoint returns `409 Conflict`.

#### Multi-Tenant Model Routing
Each user row has a `tenant_config JSONB` column. The model-router reads `primary_model` and `fallback_chain` from this config. If the primary adapter raises an error, the router tries each fallback in order.

#### Win/Loss Learning
When a win/loss outcome is recorded for an RFP, `WinLossLearningAgent` writes `score_boosts JSONB` to `win_loss_records`. The retrieval service reads these boosts and applies them to final RRF scores (`+0.10` for win-associated chunks, `-0.05` for loss-associated).

#### Docker Build
Each service has its own Dockerfile. The build context is always the repo root so each Dockerfile can `COPY common /common`. Dependencies are installed via `scripts/install_deps.py` which reads `pyproject.toml` with `tomllib` — this avoids editable-install issues with `hatchling`.

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `api-gateway` | 8000 | Auth, rate limiting, user management |
| `orchestrator` | 8001 | `POST /ask` pipeline, streaming SSE |
| `retrieval-service` | 8002 | Hybrid retrieval, RBAC filtering |
| `content-service` | 8003 | Document ingestion, chunking, embedding |
| `rbac-service` | 8004 | JWT decode, role/team resolution |
| `rfp-service` | 8005 | RFP CRUD, answer versioning, questionnaire |
| `model-router` | 8006 | Tenant config, adapter selection, fallback |
| `audit-service` | 8008 | Structured audit log writes |
| `analytics-service` | 8009 | Win/loss learning, insight reporting |
| `portfolio-service` | 8010 | Product catalog, coverage matrix, recommendations |
| `copilot-adapter` | 8009 | Teams Bot Framework webhook |
| `frontend` | 3000 | Next.js 14 chat + RFP workspace UI |

## Features

- **Hybrid retrieval** — pgvector cosine similarity + PostgreSQL full-text search fused with Reciprocal Rank Fusion (k=60)
- **RBAC as SQL predicate** — permission filtering happens in the database; the model never receives non-permitted content
- **Model-agnostic** — swap between Claude, Gemini, and Ollama per tenant via config; primary + fallback chain
- **Multi-agent pipeline** — `AgentPipeline` with typed input/output schemas: ingestion → extraction → generation → questionnaire completion
- **RFP workspace** — create RFPs, bulk-generate draft answers, version control with optimistic locking, content-admin approval
- **Questionnaire completion** — typed answers (yes/no, multiple choice, numeric, text) with confidence scoring; flags items below 0.7 for human review
- **Adaptive disclosure** — prepends partial-compliance notice when retrieved context is thin (`mean_score < 0.4` or `< 2 chunks`)
- **Response strategy** — minimal / balanced / detailed detail levels per request
- **Portfolio orchestration** — product knowledge embeddings, requirement coverage matrix, solution recommendation with gap detection
- **Win/loss learning** — score boosts applied to chunks from winning RFPs; insights dashboard for admins
- **Teams Copilot adapter** — Bot Framework webhook with MSAL identity resolution and Adaptive Card responses
- **Audit logging** — every `/ask` call produces an `audit_logs` row with sensitive-key redaction

## Quick Start

**Prerequisites:** Docker, Docker Compose

```bash
# 1. Clone and configure
git clone https://github.com/rrnextria/rfp-assistant.git
cd rfp-assistant
cp .env.example .env
# Edit .env — set JWT_SECRET, ANTHROPIC_API_KEY or GOOGLE_API_KEY

# 2. Start all services
docker compose up -d

# 3. Run migrations
docker compose exec api-gateway alembic upgrade head

# 4. Seed demo data (optional)
docker compose exec api-gateway python /app/../scripts/seed_demo.py

# 5. Open the UI
open http://localhost:3000
```

## Demo Accounts

Run `scripts/seed_demo.py` after migrations to create a demo organisation with the following accounts:

| Role | Email | Password |
|------|-------|----------|
| `system_admin` | admin@demo.com | `Demo@1234` |
| `content_admin` | content@demo.com | `Demo@1234` |
| `end_user` | user@demo.com | `Demo@1234` |

The seed script also creates:

**Teams:** Engineering · Sales · Pre-Sales

**Products (Nextria IT portfolio):**

| Product | Category |
|---------|----------|
| Cloud Storage Suite | Cloud Infrastructure |
| SecureEdge Platform | Cybersecurity / EDR / ZTNA |
| CloudID | Identity & Access Management |
| DevFlow Platform | DevOps & CI/CD |
| AI Insights Engine | Analytics & AI |

**Documents (29 searchable chunks across 8 documents):**
- Cloud Storage Suite — Product Brief
- Cloud Storage Suite — Compliance & Certifications Sheet
- SecureEdge Platform — Sales Data Sheet
- SecureEdge Platform — Government & Public Sector Brief
- CloudID — Identity & Access Management Overview
- DevFlow Platform — DevSecOps Capabilities Brief
- AI Insights Engine — Product Overview
- AI Insights Engine — Healthcare & Life Sciences Brief

**RFPs with pre-generated draft answers:**

| Customer | Industry | Questions |
|----------|----------|-----------|
| Acme Financial Services | Financial Services | 5 |
| MedGroup Healthcare Network | Healthcare | 4 |
| State Department of Digital Services | Government | 5 |

To authenticate, `POST /auth/login` with `{"email": "admin@demo.com", "password": "Demo@1234"}` and use the returned `access_token` as a Bearer token. The demo seed is idempotent — re-running it will not create duplicates.

## Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Secret for signing JWTs — change in production |
| `ANTHROPIC_API_KEY` | Required if using Claude adapter |
| `GOOGLE_API_KEY` | Required if using Gemini adapter |
| `OLLAMA_BASE_URL` | Ollama base URL (default: `http://host.docker.internal:11434`) |
| `DEFAULT_TENANT_MODEL` | Default adapter: `claude`, `gemini`, or `ollama` |

For the Teams Copilot adapter, also set `BOT_APP_ID` and `BOT_APP_PASSWORD` from your Azure Bot registration.

## API Overview

### Auth

```
POST /auth/login          → {access_token}
POST /users               → create user (system_admin)
GET  /auth/me             → current user
```

### Ask

```
POST /ask                 → {answer, citations, confidence, partial_compliance}
POST /ask?stream=true     → SSE stream of answer chunks
```

Request body:
```json
{
  "question": "Does the product support SSO?",
  "mode": "answer",          // answer | draft | review | gap
  "detail_level": "balanced", // minimal | balanced | detailed
  "rfp_id": "<uuid>"
}
```

### RFP Workspace

```
POST   /rfps                                          → create RFP
GET    /rfps/{id}                                     → RFP with questions + latest answers
POST   /rfps/{id}/questions                           → add questions (single or bulk)
POST   /rfps/{id}/questions/{qid}/generate            → AI draft answer
PATCH  /rfps/{id}/questions/{qid}/answers/{aid}       → edit (optimistic lock)
POST   /rfps/{id}/questions/{qid}/answers/{aid}/approve
POST   /rfps/{id}/questionnaire/complete              → auto-fill questionnaire items
POST   /rfps/{id}/recommend-solution                  → portfolio coverage + recommendation
POST   /rfps/{id}/outcome                             → record win/loss
```

### Content

```
POST  /documents                    → upload document (PDF or DOCX)
PATCH /documents/{id}/approve       → approve for retrieval (content_admin)
POST  /rfps/{id}/ingest             → parse RFP document → extract requirements + questionnaire
```

### Admin

```
GET  /admin/insights    → win rate, top products, gap areas (system_admin)
POST /products          → add product to catalog (system_admin)
```

## Roles

| Role | Permissions |
|------|-------------|
| `end_user` | Ask questions, create RFPs, add questions, generate answers |
| `content_admin` | All above + upload/approve documents, approve answers |
| `system_admin` | All above + manage users, products, view insights |

## Data Model (key tables)

```
users            — id, email, role, password_hash, tenant_config JSONB
teams / user_teams
documents        — id, title, status, metadata JSONB
chunks           — id, document_id, text, embedding VECTOR(384), text_search TSVECTOR
rfps             — id, customer, industry, region, raw_text
rfp_questions    — id, rfp_id, question
rfp_answers      — id, question_id, answer, version, approved, detail_level, partial_compliance
questionnaire_items  — id, rfp_id, question_type, answer, confidence, flagged
products         — id, name, vendor, category, description, features JSONB
product_embeddings   — product_id, embedding VECTOR(384)
rfp_requirements — id, rfp_id, text, category
win_loss_records — id, rfp_id, outcome, score_boosts JSONB
audit_logs       — id, user_id, action, payload JSONB
```

## Embeddings

Uses `all-MiniLM-L6-v2` (384 dimensions) via `sentence-transformers`. The `common/embedder.py` package provides a shared `EmbedderInterface` ABC used by content-service, retrieval-service, and portfolio-service.

## Development

```bash
# Verify environment
./how_to/maistro doctor

# Run a service locally (example: retrieval-service)
cd services/retrieval-service
pip install -e ../../common -e .
uvicorn main:app --reload --port 8002
```

The `how_to/` directory contains the Maistro orchestrator used during development for plan review and code review loops.

## License

MIT
