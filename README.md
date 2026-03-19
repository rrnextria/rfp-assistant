# RFP Assistant (Keystone)

A model-agnostic RFP assistant that retrieves permission-scoped enterprise content and generates compliant, citation-backed answers. Supports Claude, Gemini, Ollama, and Microsoft Teams Copilot through a unified adapter layer.

## Architecture

```
Channel Adapters (Web / Teams Copilot)
  → API Gateway         — JWT auth, rate limiting, RBAC
  → Orchestrator        — POST /ask pipeline, multi-agent coordination
  → Retrieval Service   — Hybrid vector + FTS search, RRF reranking, RBAC filters
  → Model Router        — Tenant-aware adapter selection with fallback chain
  → Model Adapters      — Claude · Gemini · Ollama
  → Response Assembler  — Citations, adaptive disclosure, detail levels
  → Stores              — Postgres + pgvector · Redis
```

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
| `audit-service` | 8007 | Structured audit log writes |
| `analytics-service` | 8007 | Win/loss learning, insight reporting |
| `portfolio-service` | 8008 | Product catalog, coverage matrix, recommendations |
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

# 4. Open the UI
open http://localhost:3000
```

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
