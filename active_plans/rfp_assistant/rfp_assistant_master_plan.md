# RFP Assistant — Master Plan

---

## LLM Navigation & Grep Guide (For LLMs Only)

This section exists ONLY for LLMs and tooling. Do NOT modify or remove.

### Grepping Phase Headings in the Master Plan

- `grep -n "^### Phase [0-9]\+:" active_plans/rfp_assistant/rfp_assistant_master_plan.md`

### Grepping Task Headings in Phase Files

- `grep -nE "^### \[ \] [0-9]+ " active_plans/rfp_assistant/phases/phase_*.md`
- `grep -nE "^  - \[ \] [0-9]+\.[0-9]+ " active_plans/rfp_assistant/phases/phase_*.md`

### Grepping Mirrored Tasks in the Master Plan (Phases Overview)

- `grep -nE "^### \[ \] [0-9]+ " active_plans/rfp_assistant/rfp_assistant_master_plan.md`
- `grep -nE "^  - \[ \] [0-9]+\.[0-9]+ " active_plans/rfp_assistant/rfp_assistant_master_plan.md`

### LLM RULES for the Master Plan

- Do NOT invent tasks.
- Do NOT modify task numbers or titles copied from phase files.
- Only include top-level tasks (`### [ ] N`) and first-level subtasks (`  - [ ] N.1`) in the master.
- Never include sub-sub-tasks (e.g., `1.1.1`) in the master plan.

---

## Executive Summary

The RFP Assistant (branded "Keystone") is a model-agnostic, enterprise-grade RFP intelligence and solution orchestration platform. It retrieves permission-scoped content, orchestrates optimal solutions across a VAR's full product portfolio, generates complete RFP responses with confidence scoring, completes technical questionnaires, and continuously improves through win/loss learning. It supports Claude, Gemini, Ollama, and Microsoft Copilot through a unified adapter pattern, enforces RBAC pre-retrieval so the model never sees non-permitted content, and provides a full web UI plus a Teams bot channel adapter for the MVP.

The build is structured as 10 sequential phases: foundation → auth/RBAC → content ingestion (including RFP extraction) → hybrid retrieval → orchestrator/agent layer → RFP service (with questionnaire completion and response strategy) → frontend → Copilot adapter → portfolio orchestration → win/loss learning. Each phase delivers independently testable, production-ready code with integration tests that gate advancement to the next phase.

---

## Detailed Objective

The RFP Assistant replaces manual, inconsistent RFP response processes with an AI-assisted workflow backed by a governed enterprise content library. Users ask questions (free-form or per an RFP template) and receive answers that cite specific approved documents — with full audit trails and permission enforcement.

**In scope for this build:** All services in spec §2.1, the full Postgres data model (spec §3 + extended portfolio/learning tables), the deterministic retrieval pipeline (spec §4 + win/loss score adjustments), the orchestrator flow (spec §5 + multi-agent pipeline), all API contracts (spec §6), all prompt templates (spec §7 + Minimal/Balanced/Detailed strategy), the ModelAdapter interface and three adapters (Claude, Gemini, Ollama; spec §8), the Next.js frontend (spec §9), the ingestion pipeline (spec §11 + RFP requirement/questionnaire extraction), the Copilot channel adapter (spec §13 MVP checklist), portfolio orchestration with Product Knowledge + Portfolio + Solution Recommendation agents (spec_additional §2.2, §3, §5), and the Win/Loss Learning Agent (spec_additional §4).

**Out of scope for this build:** Graph relationships, CRM sync, automated outcome detection, real-time learning, predictive win probability, Kubernetes manifests, cross-encoder reranker, and any other items listed in spec §14 (Future/Post-MVP) or marked post-MVP in spec_additional.

**Definition of success:** All 13 items in the spec §13 MVP checklist are implemented, all acceptance gates across all phases pass, and a real RFP question can be answered end-to-end (Teams message or web chat → retrieval → model → cited answer) with RBAC enforced at every layer.

**Stack decisions:** Python FastAPI for all backend services (chosen for AI/ML library compatibility); Next.js 14 + TypeScript for the frontend; Postgres 16 + pgvector for vector + relational storage; Redis for future queue integration; Docker Compose for local dev.

---

## Quick Navigation

| Phase | Focus | Status | File |
|---|---|---|---|
| 0 | Foundation & Infrastructure | Pending | `active_plans/rfp_assistant/phases/phase_0_foundation.md` |
| 1 | Auth, RBAC & Database Schema | Pending | `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md` |
| 2 | Content Ingestion Pipeline | Pending | `active_plans/rfp_assistant/phases/phase_2_content_ingestion.md` |
| 3 | Retrieval Service | Pending | `active_plans/rfp_assistant/phases/phase_3_retrieval.md` |
| 4 | Orchestrator & Model Layer | Pending | `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md` |
| 5 | RFP Service | Pending | `active_plans/rfp_assistant/phases/phase_5_rfp_service.md` |
| 6 | Frontend (Next.js) | Pending | `active_plans/rfp_assistant/phases/phase_6_frontend.md` |
| 7 | Copilot Channel Adapter | Pending | `active_plans/rfp_assistant/phases/phase_7_copilot_adapter.md` |
| 8 | Portfolio Orchestration | Pending | `active_plans/rfp_assistant/phases/phase_8_portfolio_orchestration.md` |
| 9 | Win/Loss Learning Agent | Pending | `active_plans/rfp_assistant/phases/phase_9_win_loss_learning.md` |

---

## Architecture Overview

```
Channel Adapters (Teams Bot / Web / API)
  → API Gateway (FastAPI, JWT auth, rate limit, audit)
    → Orchestrator Service (AgentPipeline)
        → RFP Ingestion Agent → Requirement Extraction Agent → Questionnaire Extraction Agent
        → Product Knowledge Agent → Portfolio Orchestration Agent → Solution Recommendation Agent
        → Response Generation Agent → Questionnaire Completion Agent
        → Win/Loss Learning Agent (batch)
      → Retrieval Service (RBAC filter → vector + BM25 → RRF + win/loss boosts → top 8-12)
      → Model Router → Model Adapters (Claude / Gemini / Ollama)
      → Response Assembler (citations + confidence + detail_level)
    → RFP Service (RFP CRUD, requirements, questionnaire, answer versioning, response strategy)
    → Portfolio Service (product catalog, recommendations, coverage matrix)
  → Stores:
      Postgres 16 + pgvector (content, vectors, products, requirements, questionnaires, win/loss)
      Redis (future queue)
```

All services are independent Python FastAPI containers. The `common/` package provides shared DB engine, settings, and logging. Alembic manages migrations. RBAC is enforced as a SQL WHERE predicate in the retrieval layer — the model never receives non-permitted content. The AgentPipeline (Phase 4) orchestrates all specialized agents with structured input/output schemas.

---

## Current State

- Git repository initialized at `/home/ravi/git/rfp-assistant`.
- `spec.md` contains the complete engineering specification.
- `how_to/` Maistro orchestrator deployed and all doctor checks passing.
- `active_plans/`, `reviews/`, `research/` directories created.
- No application code exists yet — this plan is the starting point.

---

## Desired State

Upon completion of all phases:
- All 9 backend services running in Docker Compose with live-reload.
- Full Postgres schema with pgvector, FTS, RBAC metadata, product catalog, questionnaire, and win/loss tables.
- Document ingestion (knowledge base) + RFP document ingestion (requirement + questionnaire extraction).
- Hybrid retrieval (vector + BM25 + RRF + win/loss score boosts) with RBAC enforcement as SQL predicate.
- Multi-agent pipeline: RFP Ingestion, Requirement Extraction, Questionnaire Extraction, Product Knowledge, Portfolio Orchestration, Solution Recommendation, Response Generation, Questionnaire Completion, Win/Loss Learning.
- Three model adapters (Claude, Gemini, Ollama) with tenant routing and fallback.
- `POST /ask` supporting all four modes (answer/draft/review/gap) with streaming SSE, confidence scoring, and Minimal/Balanced/Detailed response strategy.
- RFP workspace: create RFPs, ingest documents, extract requirements + questionnaires, auto-complete questionnaires, generate/edit/approve answers with confidence flags.
- Portfolio orchestration: product catalog management, solution recommendations with coverage matrix.
- Win/loss learning: outcome recording, lesson extraction, retrieval score boosts, insight reporting.
- Next.js frontend with chat UI, RFP workspace, and admin panels.
- Microsoft Teams bot answering RFP questions via adaptive cards.
- All spec §13 MVP checklist items complete.

---

## Global Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| RBAC bug allows non-permitted content to reach the model | Critical security violation | RBAC enforced as SQL WHERE clause (not post-filter); dedicated adversarial RBAC tests at Phase 3 |
| Embedding model dimension mismatch between ingestion and retrieval | Vector search broken | Dimension pinned in `common/config.py`; validated at startup with assertion |
| Phase dependency violation (Phase N uses Phase N+1 artifacts) | Build fails | Strict phase ordering; each phase has explicit dependency gates |
| External AI provider outage (Anthropic, Google) | `/ask` unavailable | Fallback provider chain in model router; Ollama always available as local fallback |
| Teams auth token exchange breaks with tenant policy changes | Copilot adapter unusable | Dev-mode mock auth path controlled by `COPILOT_DEV_MODE` env var |
| Large monorepo slows down `ruff`/`black` | Slow CI | Run linters per-service in parallel; cache venvs in CI |

---

## Global Acceptance Gates

- [ ] Gate 1: All 13 spec §13 MVP checklist items are implemented and verified.
- [ ] Gate 2: `POST /ask` returns a cited answer for a question matching ingested approved content, with RBAC enforcement verified (non-permitted content absent from response).
- [ ] Gate 3: All integration tests pass (`pytest -x`) across all services with no mocked DB.
- [ ] Gate 4: A Teams user can ask a question via @mention and receive an adaptive card answer with citations.
- [ ] Gate 5: `ruff check .` and `black --check .` pass with zero errors; `npm run lint` passes with zero errors.
- [ ] Gate 6: Uploading an RFP document produces extracted `rfp_requirements` and `questionnaire_items` rows; running questionnaire completion populates all items with typed answers and confidence scores.
- [ ] Gate 7: `POST /rfps/{id}/recommend-solution` returns a coverage matrix over the tenant's product catalog with `coverage_gaps` identified.
- [ ] Gate 8: After recording 5+ win/loss outcomes and running the learning agent, `GET /admin/insights` returns a non-empty insight report with win rates and loss gaps.

---

## Dependency Gates

- [ ] Phase 0 complete before Phase 1: Docker Compose, Alembic, and `common/` must exist before schema migration.
- [ ] Phase 1 complete before Phase 2: `chunks`, `documents`, and RBAC middleware must exist before ingestion.
- [ ] Phase 2 complete before Phase 3: Approved chunks with embeddings must be in DB before retrieval.
- [ ] Phase 3 complete before Phase 4: Retrieval service endpoint must exist before orchestrator wires it.
- [ ] Phase 4 complete before Phase 5: `ask_pipeline` and `AgentPipeline` must exist before RFP service calls them.
- [ ] Phase 5 complete before Phase 6: All REST endpoints must be stable before frontend builds against them.
- [ ] Phase 4 complete before Phase 7: `POST /ask` must exist before Copilot adapter calls it.
- [ ] Phase 1 (Task 5) + Phase 5 complete before Phase 8: `products`, `rfp_requirements` tables must exist before portfolio orchestration.
- [ ] Phase 3 + Phase 5 complete before Phase 9: Retrieval service and `rfp_answers` must exist before win/loss learning integrates score boosts.

---

## Phases Overview

### Phase 0: Foundation & Infrastructure — `active_plans/rfp_assistant/phases/phase_0_foundation.md`
#### Tasks
### [ ] 1 Create Monorepo Directory Structure
  - [ ] 1.1 Create `services/api-gateway/`, `services/orchestrator/`, `services/retrieval-service/`, `services/content-service/`, `services/rbac-service/`, `services/rfp-service/`, `services/model-router/`, `services/adapters/`, `services/audit-service/`
  - [ ] 1.2 Create `common/` Python package with `__init__.py`, `db.py` (async engine factory), `config.py` (pydantic-settings base), `logging.py` (structured JSON logger)
  - [ ] 1.3 Create `frontend/` directory with Next.js scaffold stub (`package.json` placeholder)
  - [ ] 1.4 Create `pyproject.toml` at repo root with ruff and black dev dependencies
### [ ] 2 Set Up Per-Service FastAPI Skeletons
  - [ ] 2.1 Create `services/<service>/main.py` with FastAPI app, `/healthz` returning `{"status": "ok", "service": "<name>"}`, and lifespan hook for DB connection pool
  - [ ] 2.2 Create `services/<service>/pyproject.toml` declaring FastAPI, SQLAlchemy, psycopg, pydantic-settings, and `common` as dependencies; ruff + black in dev deps
  - [ ] 2.3 Create `services/<service>/Dockerfile` using `python:3.12-slim`, installs `common` via `pip install -e /common`, runs `uvicorn`
### [ ] 3 Configure Docker Compose Environment
  - [ ] 3.1 Write `docker-compose.yml` with `postgres` (pgvector/pgvector:pg16), `redis` (redis:7-alpine), and one container per service with volume mounts for hot-reload
  - [ ] 3.2 Write `.env.example` with stubs for `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, `DEFAULT_TENANT_MODEL`
  - [ ] 3.3 Add `depends_on` and `healthcheck` directives so app containers wait for Postgres to be ready
### [ ] 4 Bootstrap Alembic Migration Toolchain
  - [ ] 4.1 Initialise Alembic in `migrations/` directory; configure `env.py` to read `DATABASE_URL` from environment and import `common.db.Base` for autogenerate
  - [ ] 4.2 Write baseline migration `0001_enable_pgvector.py` that runs `CREATE EXTENSION IF NOT EXISTS vector`
  - [ ] 4.3 Verify `alembic upgrade head` applies cleanly against the Docker Compose Postgres; capture output in `migrations/README.md`

### Phase 1: Auth, RBAC & Database Schema — `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md`
#### Tasks
### [ ] 1 Create Full Database Schema Migration
  - [ ] 1.1 Create `migrations/versions/0002_schema.py` with tables: `users(id UUID PK, email UNIQUE, name, role, password_hash, created_at)`, `teams(id, name)`, `user_teams(user_id FK, team_id FK)`
  - [ ] 1.2 Add tables: `documents(id, title, status, created_by FK users, created_at, version)`, `chunks(id, document_id FK, text, embedding VECTOR(384), metadata JSONB)`; add GIN index on `chunks.metadata` and ivfflat index on `chunks.embedding` (384-dim matches `all-MiniLM-L6-v2` model selected in Phase 2)
  - [ ] 1.3 Add tables: `rfps(id, customer, industry, region, created_by FK)`, `rfp_questions(id, rfp_id FK, question)`, `rfp_answers(id, question_id FK, answer TEXT, approved BOOL, version INT)`
  - [ ] 1.4 Add table: `audit_logs(id, user_id FK, action VARCHAR, payload JSONB, created_at)`; apply migration and verify all tables exist
### [ ] 2 Implement JWT Authentication
  - [ ] 2.1 Implement `POST /users` — accept `{email, role, teams[]}`, hash password with bcrypt, insert `users` row, assign teams via `user_teams`
  - [ ] 2.2 Implement `POST /auth/login` — validate credentials, issue JWT with claims `{sub: user_id, role, exp}`; apply slowapi rate limit (10/min per IP)
  - [ ] 2.3 Implement `GET /me` — validate JWT, return user record with teams; implement `get_current_user` FastAPI dependency that extracts and validates JWT from `Authorization: Bearer` header
### [ ] 3 Implement RBAC Middleware
  - [ ] 3.1 Implement `UserContext` dataclass: `user_id`, `role`, `teams: list[str]`; implement `load_user_context(token)` that decodes JWT and fetches teams from DB
  - [ ] 3.2 Implement `require_role(*allowed_roles)` FastAPI dependency factory — raises HTTP 403 if `user.role not in allowed_roles`; raise HTTP 401 if token missing/invalid
  - [ ] 3.3 Write `tests/test_rbac.py` — verify `end_user` blocked from `content_admin` routes; `system_admin` passes all; invalid token → 401
### [ ] 4 Implement Audit Logging Middleware
  - [ ] 4.1 Implement `log_action(user_id, action, payload)` async function in `services/audit-service/logger.py` — inserts row into `audit_logs`
  - [ ] 4.2 Wire `log_action` as a FastAPI `BackgroundTasks` call in a middleware that fires after every authenticated response; log `action=<METHOD> <path>` and sanitized payload (strip passwords)
  - [ ] 4.3 Write `tests/test_audit.py` — make an authenticated request, assert one `audit_logs` row written with correct `user_id` and `action`
### [ ] 5 Add Portfolio and Learning Schema Tables
  - [ ] 5.1 Add `products(id UUID PK, name, vendor, category, description TEXT, features JSONB, created_at)`, `tenant_products(tenant_id, product_id)`, and `product_embeddings(product_id UUID FK products, embedding VECTOR(384))` tables via Alembic migration `0005_portfolio_schema.py`
  - [ ] 5.2 Add `rfp_requirements(id, rfp_id FK, text TEXT, category VARCHAR, scoring_criteria JSONB, is_questionnaire BOOL)` table; add `rfps.raw_text TEXT` column (used by Phase 2 RFP ingestion); add `rfp_answers.confidence FLOAT` column and `rfp_answers.detail_level ENUM('minimal','balanced','detailed')` column
  - [ ] 5.3 Add `questionnaire_items(id, rfp_requirement_id FK, question_type ENUM('yes_no','multiple_choice','numeric','text'), options JSONB, answer TEXT, confidence FLOAT, flagged BOOL)` table
  - [ ] 5.4 Add `win_loss_records(id, rfp_id FK, outcome ENUM('win','loss','no_decision'), notes TEXT, lessons_learned TEXT, created_at)` table; apply migration and verify all new tables exist

### Phase 2: Content Ingestion Pipeline — `active_plans/rfp_assistant/phases/phase_2_content_ingestion.md`
#### Tasks
### [ ] 1 Implement Document Upload Endpoint
  - [ ] 1.1 Define `DocumentMetadata` Pydantic model: `product: str`, `region: str`, `industry: str`, `allowed_teams: list[str]`, `allowed_roles: list[Literal["end_user","content_admin","system_admin"]]`
  - [ ] 1.2 Implement `POST /documents` — accept `multipart/form-data` with `file` (PDF/DOCX, max 50MB) and `metadata` (JSON string); validate with `DocumentMetadata`; store document row with `status=pending`; return `{document_id}`
  - [ ] 1.3 Add `content_admin` role requirement via `require_role("content_admin", "system_admin")` on the upload endpoint
### [ ] 2 Implement Document Parser
  - [ ] 2.1 Implement `parse_pdf(file_bytes) -> list[Section]` using `pdfplumber` — extract text blocks grouped by heading (detected via font-size delta ≥ 20% above body); each `Section` has `heading: str | None` and `text: str`
  - [ ] 2.2 Implement `parse_docx(file_bytes) -> list[Section]` using `python-docx` — group paragraphs by `Heading 1/2/3` styles; fall back to paragraph breaks if no heading styles present
  - [ ] 2.3 Write `tests/test_parser.py` with fixture PDF and DOCX — assert section count > 0 and headings extracted correctly
### [ ] 3 Implement Chunker and Embedder
  - [ ] 3.1 Implement `chunk_sections(sections, max_tokens=500, overlap=50) -> list[Chunk]` using `tiktoken` (cl100k_base) — split at heading boundaries first, then token boundaries; each `Chunk` has `text`, `heading`, `token_count`
  - [ ] 3.2 Define `EmbedderInterface` abstract class with `embed(texts: list[str]) -> list[list[float]]`; implement `SentenceTransformerEmbedder` using `all-MiniLM-L6-v2` (384-dim)
  - [ ] 3.3 Write `tests/test_chunker.py` — assert no chunk exceeds 500 tokens; assert overlap text appears in consecutive chunks
### [ ] 4 Implement Ingestion Pipeline and Approval Workflow
  - [ ] 4.1 Implement `ingest_document(document_id, file_bytes, metadata)` — orchestrate parser → chunker → embedder → bulk-insert chunks into `chunks` table with `metadata JSONB = {**metadata_dict, "approved": false}`; update document `status=ready`
  - [ ] 4.2 Trigger `ingest_document` synchronously after `POST /documents` returns (via FastAPI `BackgroundTasks` so HTTP 201 is returned immediately); update document `status=processing` before starting
  - [ ] 4.3 Implement `PATCH /documents/{id}/approve` (requires `content_admin`/`system_admin`) — set `documents.status=approved` and update all `chunks.metadata` JSONB to `approved=true` via a single `UPDATE chunks SET metadata = metadata || '{"approved":true}'` for the document's chunks
  - [ ] 4.4 Write `tests/test_ingestion.py` — upload fixture PDF, assert chunks in DB with correct metadata and non-null embeddings; call approve endpoint, assert `metadata.approved=true` on all chunks
### [ ] 5 Implement RFP Document Ingestion and Extraction
  - [ ] 5.1 Implement `POST /rfps/{id}/ingest` (content_admin) — accept RFP document (PDF/DOCX); reuse parser from Task 2 to extract sections; store raw text on `rfps.raw_text TEXT`
  - [ ] 5.2 Implement `RequirementExtractionAgent.extract(rfp_text) -> list[Requirement]` — LLM-based extraction of requirements, scoring criteria, and constraints; each `Requirement` has `text`, `category`, `scoring_criteria JSONB`; bulk-insert into `rfp_requirements`
  - [ ] 5.3 Implement `QuestionnaireExtractionAgent.extract(rfp_text) -> list[QuestionnaireItem]` — detect structured questionnaires; classify each item by `question_type` (yes_no, multiple_choice, numeric, text); extract answer options for MCQ; insert into `questionnaire_items` with `flagged=false` and `confidence=null`
  - [ ] 5.4 Write `tests/test_rfp_extraction.py` — upload fixture RFP with known requirements and questionnaire; assert `rfp_requirements` rows created with correct categories; assert `questionnaire_items` rows with correct `question_type`

### Phase 3: Retrieval Service — `active_plans/rfp_assistant/phases/phase_3_retrieval.md`
#### Tasks
### [ ] 1 Implement RBAC Filter
  - [ ] 1.1 Implement `build_rbac_filter(user_ctx: UserContext) -> list[ColumnElement]` — returns SQLAlchemy WHERE clauses: `chunks.metadata['approved'].as_boolean() == True`, `chunks.metadata['allowed_roles'].contains(user_ctx.role)`, `chunks.metadata['allowed_teams'].overlap(user_ctx.teams)`
  - [ ] 1.2 Implement optional metadata filter: if `product` or `industry` provided in query, add `chunks.metadata['product'] == product` etc. to the WHERE list
  - [ ] 1.3 Write `tests/test_rbac_filter.py` — unit-test predicate generation; integration-test with DB rows that should and should not be visible for a given `UserContext`
### [ ] 2 Implement Vector Search
  - [ ] 2.1 Implement `vector_search(query_embedding: list[float], rbac_filter, limit=50) -> list[RankedChunk]` using SQLAlchemy: `SELECT id, text, metadata, embedding <=> :qvec AS score FROM chunks WHERE <rbac> ORDER BY score LIMIT 50`
  - [ ] 2.2 Embed the query text inline using the same `EmbedderInterface` from Phase 2 (`services/content-service/embedder.py` imported via `common/`)
  - [ ] 2.3 Write `tests/test_vector_search.py` — insert 20 approved chunks for user's role, 5 non-approved; assert only approved chunks returned; assert result count ≤ 50
### [ ] 3 Implement Keyword Search
  - [ ] 3.1 Add `tsvector` generated column `chunks.text_search` via new Alembic migration `0003_fts_index.py`: `ALTER TABLE chunks ADD COLUMN text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`; add GIN index
  - [ ] 3.2 Implement `keyword_search(query: str, rbac_filter, limit=50) -> list[RankedChunk]` using `plainto_tsquery` and `ts_rank_cd` scoring
  - [ ] 3.3 Write `tests/test_keyword_search.py` — assert keyword-matching chunks rank higher than non-matching; assert RBAC filter respected
### [ ] 4 Implement Hybrid Reranker and Retrieval Endpoint
  - [ ] 4.1 Implement `reciprocal_rank_fusion(vector_results, keyword_results, k=60, top_n=12) -> list[RankedChunk]` — compute RRF score per chunk, deduplicate by `chunk_id`, return top `top_n`
  - [ ] 4.2 Implement `retrieve(query, user_ctx, filters, top_n=12)` orchestrator that calls `vector_search` + `keyword_search` in parallel (asyncio.gather), then `reciprocal_rank_fusion`
  - [ ] 4.3 Implement `GET /retrieve` internal endpoint: accept `{query: str, user_context: UserContextSchema, filters: dict}`, call `retrieve()`, return `{chunks: [{chunk_id, doc_id, text, score, metadata}]}`
  - [ ] 4.4 Write `tests/test_retrieval.py` — seed 30 approved and 10 unapproved chunks; assert endpoint returns 8–12 results; assert all returned chunks are RBAC-permitted

### Phase 4: Orchestrator & Model Layer — `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md`
#### Tasks
### [ ] 1 Implement Model Adapter Interface and Adapters
  - [ ] 1.1 Define `ModelAdapter` ABC in `services/adapters/base.py`: `generate(prompt: str, context: list[str]) -> GenerateResult` and `async_stream(prompt, context) -> AsyncIterator[str]`; define `GenerateResult(text: str, model: str, tokens_used: int)` and `AdapterError`
  - [ ] 1.2 Implement `ClaudeAdapter` in `claude.py` using `anthropic.AsyncAnthropic`; pass system prompt + context + user question as messages; map `anthropic.APIError` → `AdapterError`
  - [ ] 1.3 Implement `GeminiAdapter` in `gemini.py` using `google.generativeai`; format context as part of the user turn; map SDK exceptions → `AdapterError`
  - [ ] 1.4 Implement `OllamaAdapter` in `ollama.py` using `httpx.AsyncClient` against `OLLAMA_BASE_URL/api/generate`; configurable model name; timeout 30s; map HTTP errors → `AdapterError`
### [ ] 2 Implement Model Router
  - [ ] 2.1 Implement `TenantConfig` Pydantic model: `preferred_provider: Literal["claude","gemini","ollama"]`, `fallback_provider: Literal["claude","gemini","ollama"] | None`, `model_name: str | None`
  - [ ] 2.2 Implement `load_tenant_config(user_id) -> TenantConfig` — reads from `users.tenant_config JSONB`; defaults to `claude` if not set; add `tenant_config JSONB DEFAULT '{}'` column via Alembic migration `0004_tenant_config.py`
  - [ ] 2.3 Implement `select(tenant_config) -> ModelAdapter` — instantiates and returns the adapter for the preferred provider; implement `generate_with_fallback(adapter, fallback, prompt, context)` that catches `AdapterError` and retries with fallback
### [ ] 3 Implement Prompt Templates
  - [ ] 3.1 Implement `build_system_prompt() -> str` returning the spec §7.1 system prompt verbatim
  - [ ] 3.2 Implement `build_user_prompt(question, context_chunks, mode) -> str` — for `mode=answer`: combine context + question; for `mode=draft`: prepend spec §7.2 draft instruction; for `mode=review`: prepend spec §7.3 review instruction; for `mode=gap`: prepend spec §7.4 gap instruction
  - [ ] 3.3 Write `tests/test_prompts.py` — assert each mode produces a prompt string containing the mode-specific instruction from spec §7 and the user's question
### [ ] 4 Implement POST /ask Pipeline
  - [ ] 4.1 Implement `assemble_citations(chunks: list[RankedChunk]) -> list[Citation]` — map each chunk to `{chunk_id, doc_id, snippet: chunk.text[:200]}`
  - [ ] 4.2 Implement `ask_pipeline(question, mode, rfp_id, user_ctx) -> AskResponse` — (1) call retrieval-service `/retrieve` with user_ctx, (2) build prompt via `build_user_prompt`, (3) select adapter via router, (4) call `generate_with_fallback`, (5) assemble citations, (6) log audit
  - [ ] 4.3 Implement `POST /ask` FastAPI endpoint: validate request `{question, mode, rfp_id}`; require auth via `get_current_user`; call `ask_pipeline`; return `{answer, citations}`
  - [ ] 4.4 Implement streaming variant: if `stream=true` query param, use `async_stream` and return `StreamingResponse` via SSE with `sse-starlette`
  - [ ] 4.5 Write `tests/test_ask.py` — mock retrieval-service and adapter; assert correct prompt mode used; assert citations in response; assert audit row written
### [ ] 5 Implement Multi-Agent Architecture
  - [ ] 5.1 Define `AgentInput` and `AgentOutput` Pydantic base models; define concrete schemas for each agent: `RFPIngestionInput/Output`, `RequirementExtractionInput/Output`, `QuestionnaireExtractionInput/Output`, `ResponseGenerationInput/Output`, `QuestionnaireCompletionInput/Output`
  - [ ] 5.2 Implement `AgentPipeline` class: ordered list of `Agent` instances each with `run(input: AgentInput) -> AgentOutput`; pipeline passes output of each agent as input to the next; supports skipping agents based on mode
  - [ ] 5.3 Implement `ResponseGenerationAgent` — wraps existing `ask_pipeline` logic; accepts `{requirements, context_chunks, detail_level}` and returns `{answer, citations, confidence: float}` where confidence is the mean cosine similarity of retrieved chunks
  - [ ] 5.4 Write `tests/test_agent_pipeline.py` — assert pipeline runs agents in order; assert agent output schema validation catches malformed outputs; assert confidence score is in [0.0, 1.0]

### Phase 5: RFP Service — `active_plans/rfp_assistant/phases/phase_5_rfp_service.md`
#### Tasks
### [ ] 1 Implement RFP CRUD Endpoints
  - [ ] 1.1 Implement `POST /rfps` — accept `{customer, industry, region}`, insert `rfps` row with `created_by=current_user.id`, return `{rfp_id}`
  - [ ] 1.2 Implement `GET /rfps/{id}` — return RFP with nested `rfp_questions` each containing the latest `rfp_answers` row (highest version); enforce ownership or `system_admin` role
  - [ ] 1.3 Implement `GET /rfps` — list all RFPs owned by current user (paginated, limit 20)
### [ ] 2 Implement Question Management
  - [ ] 2.1 Implement `POST /rfps/{id}/questions` — accept `{question: str}` or `{questions: list[str]}`; insert one or many `rfp_questions` rows; return `{question_ids: list[str]}`
  - [ ] 2.2 Enforce RFP ownership check: only the RFP creator or `system_admin` can add questions
  - [ ] 2.3 Write `tests/test_rfp_service.py` for question creation — assert correct `rfp_id` FK and question text stored
### [ ] 3 Implement Answer Generation and Versioning
  - [ ] 3.1 Implement `POST /rfps/{id}/questions/{qid}/generate` — call `ask_pipeline(question=q.question, mode="draft", rfp_id=id, user_ctx=current_user)` and store result as `rfp_answers(version=1, approved=false, answer=text)`; for bulk (`POST /rfps/{id}/generate-all`), run as background task and return 202
  - [ ] 3.2 Implement `PATCH /rfps/{id}/questions/{qid}/answers/{aid}` — accept `{answer: str, version: int}` (optimistic lock); if `version` matches latest, insert new row with `version=N+1` and `approved=false`; return 409 on version mismatch
  - [ ] 3.3 Write `tests/test_rfp_service.py` generation tests — mock `ask_pipeline`; assert version increments correctly; assert 409 on stale version
### [ ] 4 Implement Answer Approval
  - [ ] 4.1 Implement `POST /rfps/{id}/questions/{qid}/answers/{aid}/approve` — requires `content_admin` or `system_admin`; sets `rfp_answers.approved=true` for the given `aid`
  - [ ] 4.2 Implement `GET /rfps/{id}/questions/{qid}/answers` with `?all_versions=true` — returns all answer versions sorted by version desc; default (no param) returns only latest
  - [ ] 4.3 Write approval tests — assert `end_user` gets 403; assert `content_admin` succeeds; assert `approved=true` in DB
### [ ] 5 Implement Questionnaire Completion with Confidence Scoring
  - [ ] 5.1 Implement `QuestionnaireCompletionAgent.complete(item: QuestionnaireItem, context_chunks) -> CompletedItem` — generate typed answers per `question_type`: yes/no (boolean), multiple_choice (one of `options`), numeric (float), text (string); use retrieved content as context
  - [ ] 5.2 Implement confidence scoring: for yes_no and multiple_choice, confidence = max softmax probability of the model's answer token; for text/numeric, confidence = mean chunk retrieval score; if confidence < 0.7, set `flagged=true`
  - [ ] 5.3 Implement `POST /rfps/{id}/questionnaire/complete` — run `QuestionnaireCompletionAgent` for all unfilled `questionnaire_items` for the RFP; return `{completed: int, flagged: int}`
  - [ ] 5.4 Write `tests/test_questionnaire.py` — seed questionnaire items; run completion; assert all items have answers; assert items with low-confidence scores are flagged
### [ ] 6 Implement Response Strategy Control Layer
  - [ ] 6.1 Extend `build_user_prompt` in `services/orchestrator/prompts.py` to accept `detail_level: Literal["minimal","balanced","detailed"]`; add mode-specific instructions: minimal = concise bullet-point answer, balanced = structured paragraph with citations, detailed = full technical narrative
  - [ ] 6.2 Implement adaptive disclosure: if retrieved context only partially covers the question, prepend a disclosure note ("The following answer is based on partial information: …") and set `partial_compliance=true` in the response
  - [ ] 6.3 Persist `detail_level` on `rfp_answers.detail_level` and `partial_compliance BOOL` on `rfp_answers`; expose `detail_level` as a parameter on `POST /ask` and `POST /rfps/{id}/questions/{qid}/generate`
  - [ ] 6.4 Write `tests/test_response_strategy.py` — assert minimal/balanced/detailed prompts differ in instruction content; assert partial_compliance flag set when context coverage is below threshold

### Phase 6: Frontend (Next.js) — `active_plans/rfp_assistant/phases/phase_6_frontend.md`
#### Tasks
### [ ] 1 Set Up Next.js Project and API Client
  - [ ] 1.1 Create Next.js 14 app in `frontend/` with TypeScript and Tailwind CSS (`npx create-next-app@latest`); install shadcn/ui (`npx shadcn@latest init`); configure `next.config.js` with API `rewrites` pointing `/api/*` to FastAPI
  - [ ] 1.2 Implement `frontend/lib/api.ts` typed API client — wrapper around `fetch` with base URL from env, automatic `Authorization` header injection, error handling; typed functions for all Phase 1–5 endpoints
  - [ ] 1.3 Implement auth middleware in `frontend/middleware.ts` — redirect unauthenticated users to `/login`; redirect non-admin roles away from `/admin/*`; implement `POST /auth/login` proxy route that sets HttpOnly cookie
### [ ] 2 Build Chat Page
  - [ ] 2.1 Implement `ChatBox` component — textarea input, submit button, loading state; on submit calls `POST /ask` with `{question, mode, rfp_id}`
  - [ ] 2.2 Implement `ModeSelector` component — tab or dropdown selecting `answer | draft | review | gap`; passes selected mode to ChatBox
  - [ ] 2.3 Implement `AnswerPane` component — renders streamed answer text progressively by consuming the SSE stream via `eventsource-parser`; shows spinner while streaming
  - [ ] 2.4 Implement `CitationsPanel` component — renders list of `{chunk_id, doc_id, snippet}` citations returned with the answer; each citation shows snippet text and doc title
### [ ] 3 Build RFP Workspace Page
  - [ ] 3.1 Implement `RFPQuestionList` component — server component fetching questions + latest answers; renders each question with its answer (or "Not yet generated" placeholder) and a "Generate" button
  - [ ] 3.2 Implement `Editor` component — rich text editor (textarea for MVP) for editing answer text; on save calls `PATCH .../answers/{aid}` with optimistic version; shows version history toggle
  - [ ] 3.3 Implement approve button (visible to `content_admin`/`system_admin` only) — calls `POST .../approve`; updates UI to show approved badge
### [ ] 4 Build Admin Pages
  - [ ] 4.1 Implement `/admin/users` page — `AdminTable` component listing users with columns: email, role, teams; "Create User" button opens form calling `POST /users`; page protected to `system_admin` role
  - [ ] 4.2 Implement `/admin/content` page — document upload form (file input + metadata fields: product, region, industry, allowed_teams, allowed_roles); document list with status badges and "Approve" button (content_admin); calls `POST /documents` and `PATCH /documents/{id}/approve`
  - [ ] 4.3 Implement `/403` page and `/login` page; write E2E smoke test (`playwright` or `cypress`): login → chat → submit question → assert answer rendered

### Phase 7: Copilot Channel Adapter — `active_plans/rfp_assistant/phases/phase_7_copilot_adapter.md`
#### Tasks
### [ ] 1 Implement Bot Framework Webhook and Auth Validation
  - [ ] 1.1 Create `services/adapters/copilot/main.py` FastAPI app with `POST /api/messages` endpoint; implement Bot Framework JWT signature validation using `botframework-connector` (`JwtTokenValidation.validate_auth_header`) — reject unsigned requests with HTTP 401
  - [ ] 1.2 Implement `GET /healthz` for the copilot adapter service; add service to `docker-compose.yml`
  - [ ] 1.3 Write `tests/test_copilot_adapter.py` with a mock Bot Framework activity payload (signed with test key) — assert HTTP 200 returned; assert unsigned payload → HTTP 401
### [ ] 2 Implement User Identity Resolution
  - [ ] 2.1 Implement `resolve_user(upn: str) -> str | None` in `auth.py` — query `users.email = upn`; return `user_id` or `None`
  - [ ] 2.2 Implement `get_service_jwt() -> str` — returns a cached, auto-renewed JWT for the copilot adapter's service account (pre-created `system_admin` user); use `python-jose` to generate and validate
  - [ ] 2.3 Implement `build_user_context_header(user_id) -> dict` — constructs `X-User-Id` header so the orchestrator can log the real user in audit logs (not the service account)
### [ ] 3 Implement Conversation Turn Handler
  - [ ] 3.1 Implement `handle_turn(activity: Activity)` in `handler.py` — extract message text from `activity.text`; resolve user via UPN; if not found, send "not registered" card; otherwise call `POST /ask` with `{question: text, mode: "answer"}`
  - [ ] 3.2 Call `POST /ask` via `httpx.AsyncClient` with service JWT and `X-User-Id` header; handle HTTP errors and timeouts (30s); on error send "service unavailable" card
  - [ ] 3.3 Implement `build_answer_card(answer, citations) -> dict` in `adaptive_card.py` — Adaptive Card v1.5 JSON with `TextBlock` for answer, `FactSet` for citations (snippet + doc_id); send card via Bot Framework connector
### [ ] 4 Package and Document the Teams App
  - [ ] 4.1 Create `manifest.json` with bot ID placeholder, valid `bots` array pointing to the adapter's messaging endpoint, and required permissions (`User.Read`)
  - [ ] 4.2 Write `services/adapters/copilot/README.md` covering: Azure Bot registration, environment variables (`BOT_APP_ID`, `BOT_APP_PASSWORD`, `ORCHESTRATOR_URL`), local testing with Bot Framework Emulator, Teams sideloading steps
  - [ ] 4.3 Write end-to-end integration test using Bot Framework Emulator protocol: simulate a full activity cycle (message in → answer adaptive card out) with mocked orchestrator response

### Phase 8: Portfolio Orchestration — `active_plans/rfp_assistant/phases/phase_8_portfolio_orchestration.md`
#### Tasks
### [ ] 1 Implement Product Catalog Management
  - [ ] 1.1 Implement `POST /admin/products` (system_admin) — accept `{name, vendor, category, description, features: JSONB}`; insert `products` row; generate and store embedding in `product_embeddings(product_id, embedding VECTOR(384))`
  - [ ] 1.2 Implement `POST /admin/tenants/{id}/products` — assign a product to a tenant via `tenant_products`; implement `GET /products` — return tenant-scoped product list
  - [ ] 1.3 Write `tests/test_product_catalog.py` — assert product created with embedding; assert tenant scoping (tenant A cannot see tenant B's products)
### [ ] 2 Implement Product Knowledge Agent
  - [ ] 2.1 Implement `ProductKnowledgeAgent.retrieve(requirements: list[Requirement], tenant_id) -> dict[requirement_id, list[Product]]` — for each requirement, run vector search on `product_embeddings` filtered by `tenant_products.tenant_id`; return top 5 products per requirement
  - [ ] 2.2 Implement feature matching: supplement vector similarity with exact JSONB key overlap between `requirement.scoring_criteria` and `product.features`; combine scores 70% vector + 30% feature overlap
  - [ ] 2.3 Write `tests/test_product_knowledge_agent.py` — seed 10 products and 3 requirements; assert each requirement maps to at least 1 product; assert tenant isolation
### [ ] 3 Implement Portfolio Orchestration Agent
  - [ ] 3.1 Implement `PortfolioOrchestrationAgent.score(requirements, tenant_products) -> CoverageMatrix` — for each requirement, assign the best-matching product and a coverage score (0.0–1.0); requirement with coverage < 0.5 is marked as a gap in `coverage_gaps: list[requirement_id]`
  - [ ] 3.2 Implement multi-vendor combination: if no single product covers a requirement, check if two products together exceed 0.5 threshold (feature union); flag as `multi_vendor=true`
  - [ ] 3.3 Write `tests/test_portfolio_agent.py` — assert requirements covered by product A are not in `coverage_gaps`; assert uncoverable requirements are in `coverage_gaps`
### [ ] 4 Implement Solution Recommendation Agent and Endpoint
  - [ ] 4.1 Implement `SolutionRecommendationAgent.recommend(coverage_matrix) -> SolutionArchitecture` — select the minimal set of products that maximizes requirement coverage; generate a solution architecture JSON `{products: [{product_id, role, covers_requirements: [ids]}], gaps: [ids], confidence: float}`
  - [ ] 4.2 Generate solution narrative by calling `ResponseGenerationAgent` with a specialized portfolio prompt: summarize chosen products, explain coverage of key requirements, list gaps; attach narrative to `SolutionArchitecture.narrative`
  - [ ] 4.3 Implement `POST /rfps/{id}/recommend-solution` — run `ProductKnowledgeAgent` → `PortfolioOrchestrationAgent` → `SolutionRecommendationAgent` pipeline; return full `SolutionArchitecture` with per-requirement coverage and narrative
  - [ ] 4.4 Write `tests/test_solution_recommender.py` — assert returned architecture covers maximum requirements; assert `coverage_gaps` present; assert narrative non-empty

### Phase 9: Win/Loss Learning Agent — `active_plans/rfp_assistant/phases/phase_9_win_loss_learning.md`
#### Tasks
### [ ] 1 Implement Win/Loss Outcome Recording
  - [ ] 1.1 Implement `POST /rfps/{id}/outcome` — accept `{outcome: Literal["win","loss","no_decision"], notes: str, lessons_learned: str}`; insert `win_loss_records` row; require authenticated user (any role)
  - [ ] 1.2 Implement `GET /rfps/{id}/outcome` — return the outcome record if it exists; return HTTP 404 if not yet recorded
  - [ ] 1.3 Write `tests/test_win_loss.py` for outcome recording — assert win/loss/no_decision all accepted; assert invalid value returns 422; assert row in DB
### [ ] 2 Implement Win/Loss Learning Agent
  - [ ] 2.1 Create Alembic migration `0006_win_loss_lessons.py` — add `win_loss_lessons(id, tenant_id, lesson TEXT, pattern JSONB, source_rfp_ids JSONB, created_at)` and `chunk_score_adjustments(chunk_id, tenant_id, boost FLOAT, expires_at TIMESTAMP)` tables
  - [ ] 2.2 Implement `WinLossLearningAgent.analyze(tenant_id)` — fetch all `win_loss_records` for tenant; if < 5 records return empty; call `ResponseGenerationAgent` with a lesson-extraction prompt over winning vs. losing answer pairs; parse structured lessons into `win_loss_lessons` rows
  - [ ] 2.3 Implement `WinLossLearningAgent.apply_score_boosts(tenant_id)` — for chunks that appear in winning `rfp_answers`, upsert `chunk_score_adjustments` with `boost=0.10`; cap total boost at 0.15; set `expires_at = NOW() + 90 days`
  - [ ] 2.4 Write `tests/test_win_loss.py` learning tests — seed 5 win + 5 loss records; run agent; assert `win_loss_lessons` rows created; assert boosted chunks have `chunk_score_adjustments` rows
### [ ] 3 Integrate Score Adjustments into Retrieval
  - [ ] 3.1 Implement `load_score_adjustments(chunk_ids: list[str], tenant_id) -> dict[str, float]` in `scoring_adjustments.py` — batch-fetch non-expired `chunk_score_adjustments` rows for given chunk IDs and tenant; return `{chunk_id: boost}`
  - [ ] 3.2 Extend `reciprocal_rank_fusion` in `reranker.py` to accept an optional `score_adjustments` dict; add boost to RRF score after fusion: `final_score = rrf_score * (1 + boost)`
  - [ ] 3.3 Wire `load_score_adjustments` into the `retrieve` orchestrator: call it after dedup, before RRF; pass adjustments to `reciprocal_rank_fusion`
  - [ ] 3.4 Write `tests/test_scoring_adjustments.py` — seed adjustments for chunk A; assert chunk A ranks higher after adjustment; assert tenant B's adjustments do not affect tenant A's results
### [ ] 4 Implement Insight Reporting Endpoint
  - [ ] 4.1 Implement `GET /admin/insights` (system_admin) — return `{win_rate: float, total_rfps: int, by_product: [{product_id, win_rate}], by_industry: [{industry, win_rate}], top_content: [{chunk_id, doc_id, win_appearances}], loss_gaps: [{requirement_category, frequency}]}`
  - [ ] 4.2 Compute `loss_gaps` by joining `win_loss_records(outcome=loss)` → `rfps` → `rfp_requirements` → `questionnaire_items(flagged=true)` grouped by `requirement.category`
  - [ ] 4.3 Write `tests/test_insights.py` — seed wins and losses with known patterns; assert win_rate computed correctly; assert loss_gaps reflects flagged questionnaire items from lost RFPs; assert endpoint scoped to tenant (non-admin gets 403)

---

## Decision Log

- D1: Python FastAPI chosen over NestJS for all backend services — AI/ML library ecosystem (anthropic, sentence-transformers, psycopg) — Status: Closed — Date: 2026-03-18
- D2: Postgres 16 + pgvector (official `pgvector/pgvector:pg16` image) as unified vector + relational store — Status: Closed — Date: 2026-03-18
- D3: Monorepo (single git repo, `services/` subdirectories) over polyrepo — simpler for MVP, easier to share `common/` — Status: Closed — Date: 2026-03-18
- D4: RBAC enforced as SQL WHERE clause (not post-filter) — no non-permitted data ever reaches application memory — Status: Closed — Date: 2026-03-18
- D5: Reciprocal Rank Fusion for MVP reranking — no extra model/infra; cross-encoder pluggable in same interface post-MVP — Status: Closed — Date: 2026-03-18
- D6: Synchronous ingestion for MVP — queue (Redis/Kafka) interface designed in for post-MVP — Status: Closed — Date: 2026-03-18
- D7: `all-MiniLM-L6-v2` (384-dim) for MVP embeddings — CPU-only, no external API cost — Status: Closed — Date: 2026-03-18
- D8: HttpOnly cookie (via Next.js API route proxy) for JWT storage — prevents XSS token theft — Status: Closed — Date: 2026-03-18
- D9: Streaming via SSE (`sse-starlette`) over WebSockets — simpler, works with Next.js `EventSource` — Status: Closed — Date: 2026-03-18
- D10: Multi-agent architecture (AgentPipeline) introduced in Phase 4 — enables Keystone's 9 specialized agents with structured input/output schemas per spec_additional §5 — Status: Closed — Date: 2026-03-18
- D11: Questionnaire confidence threshold 0.7 — below this, items are flagged for human review — Status: Closed — Date: 2026-03-18
- D12: Product embeddings stored in separate `product_embeddings` table — allows re-embedding on model change without modifying product records — Status: Closed — Date: 2026-03-18
- D13: Portfolio coverage threshold 0.5 cosine similarity — below this, a requirement is a gap — Status: Closed — Date: 2026-03-18
- D14: Win/loss learning agent runs as batch (not real-time) — sufficient for MVP; real-time is post-MVP per spec_additional §4 — Status: Closed — Date: 2026-03-18
- D15: Score boost capped at 15% with 90-day expiry — prevents compounding bias from stale win data — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this plan's accuracy.

### Source Files (existing code/docs being modified)
- `spec.md` — Complete engineering specification (all sections)
- `spec_additional.md` — Keystone additional requirements (§2 Core Capabilities, §3 System Architecture, §4 Learning Domain, §5 Agent Definitions, §8 Response Strategy)

### Destination Files (new files this plan creates)
- `active_plans/rfp_assistant/phases/phase_0_foundation.md`
- `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md`
- `active_plans/rfp_assistant/phases/phase_2_content_ingestion.md`
- `active_plans/rfp_assistant/phases/phase_3_retrieval.md`
- `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md`
- `active_plans/rfp_assistant/phases/phase_5_rfp_service.md`
- `active_plans/rfp_assistant/phases/phase_6_frontend.md`
- `active_plans/rfp_assistant/phases/phase_7_copilot_adapter.md`
- `active_plans/rfp_assistant/phases/phase_8_portfolio_orchestration.md`
- `active_plans/rfp_assistant/phases/phase_9_win_loss_learning.md`

### Related Documentation (context only)
- `how_to/guides/orchestrator.md` — Orchestration system reference
- `CLAUDE.md` — Project-level Claude guide

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
