# Phase 0: Project Foundation & Infrastructure

**Status:** Pending
**Planned Start:** 2026-03-18
**Target End:** 2026-03-22
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_0_foundation.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: None | Next: Phase 1

---

## Detailed Objective

This phase establishes the monorepo layout, tooling, and infrastructure scaffolding that all subsequent phases depend on. It defines the Python FastAPI project skeleton across all services, shared libraries, Docker-based local development environment (Postgres + pgvector + Redis), and Alembic migration tooling. No business logic is implemented here — only the stable foundation.

The stack decision is Python (FastAPI) for all backend services, driven by deep AI/ML library compatibility (anthropic SDK, sentence-transformers, pgvector via psycopg), and Next.js for the frontend. All services are independently deployable containers orchestrated via Docker Compose for local dev and Kubernetes-ready for production.

Success is defined as: a developer can clone the repo, run `docker compose up`, and reach a healthy Postgres+pgvector instance with the Alembic baseline migration applied. All service skeletons import cleanly with no errors.

---

## Deliverables Snapshot

1. Monorepo directory layout: `services/` with one folder per service (`api-gateway`, `orchestrator`, `retrieval-service`, `content-service`, `rbac-service`, `rfp-service`, `model-router`, `adapters/`, `audit-service`), plus `common/` shared library and `frontend/`.
2. `docker-compose.yml` running Postgres 16 + pgvector, Redis, and all service containers with hot-reload.
3. Alembic migration toolchain: `alembic.ini`, `env.py`, baseline migration enabling pgvector extension, initial empty schema.
4. `common/` Python package: shared SQLAlchemy async engine factory, base models, settings loader (pydantic-settings), logging config.
5. `pyproject.toml` per service with ruff + black configured; `.env.example` at repo root.

---

## Acceptance Gates

- [ ] Gate 1: `docker compose up` starts Postgres + pgvector + Redis with no errors; `SELECT extname FROM pg_extension WHERE extname='vector'` returns a row.
- [ ] Gate 2: `alembic upgrade head` runs cleanly against the containerized Postgres with zero errors.
- [ ] Gate 3: Each service skeleton (`uvicorn <service>.main:app --reload`) starts and returns `{"status":"ok"}` from `GET /healthz`.
- [ ] Gate 4: `ruff check .` and `black --check .` pass with zero errors across all services.

---

## Scope

- In Scope:
  1. Directory structure for all 9 services + `common/` + `frontend/` (scaffold only, no business logic).
  2. Docker Compose local dev environment (Postgres 16/pgvector, Redis, all service containers).
  3. Alembic setup with baseline migration (pgvector extension only; schema tables in Phase 1).
  4. `common/` shared library: async SQLAlchemy engine, pydantic-settings config loader, structured logging.
  5. Per-service `pyproject.toml`, `Dockerfile`, and `/healthz` endpoint.
  6. `.env.example` with all required environment variable stubs.
- Out of Scope:
  1. Database schema tables (Phase 1).
  2. Auth or RBAC logic (Phase 1).
  3. Any business logic endpoints (Phase 2+).
  4. Kubernetes manifests (post-MVP).
  5. Frontend implementation (Phase 6).

---

## Interfaces & Dependencies

- Internal: None (this is the base layer).
- External: Python 3.12, FastAPI, SQLAlchemy 2.x (async), psycopg (async driver), Alembic, pydantic-settings, ruff, black, Docker, docker-compose v2.
- Artifacts: `docker-compose.yml`, `alembic.ini`, `common/` package, per-service `Dockerfile` and `main.py`, `.env.example`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| pgvector extension not available in chosen Postgres image | Vector search blocked | Use `pgvector/pgvector:pg16` official image which ships with the extension |
| SQLAlchemy async + psycopg3 compatibility gaps | DB layer unusable | Pin versions in `pyproject.toml`; test engine connection in Gate 1 |
| Monorepo import paths break across services | All services fail | Use `common/` as an installable package (`pip install -e ./common`) in each service Dockerfile |

---

## Decision Log

- D1: Python FastAPI chosen over NestJS — Status: Closed — Date: 2026-03-18
- D2: Postgres 16 + pgvector (official image) chosen for vector store — Status: Closed — Date: 2026-03-18
- D3: Alembic for migrations (not raw SQL scripts) — Status: Closed — Date: 2026-03-18
- D4: Monorepo (single git repo, multiple service directories) over polyrepo — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — Engineering specification (§2.1 Services, §2.2 Tech, §12 Deployment)

### Destination Files (new files this phase creates)
- `docker-compose.yml` — Local dev orchestration
- `.env.example` — Environment variable stubs
- `alembic.ini` — Alembic config
- `common/` — Shared Python library
- `services/*/main.py` — Service entry points with `/healthz`
- `services/*/Dockerfile` — Per-service container definitions

### Related Documentation (context only)
- `how_to/guides/orchestrator.md` — Orchestration system reference
- `spec.md` — Full engineering spec

---

## Tasks

### [✅] 1 Create Monorepo Directory Structure
Create all service directories and the `common/` shared library scaffold.

  - [✅] 1.1 Create `services/api-gateway/`, `services/orchestrator/`, `services/retrieval-service/`, `services/content-service/`, `services/rbac-service/`, `services/rfp-service/`, `services/model-router/`, `services/adapters/`, `services/audit-service/`
  - [✅] 1.2 Create `common/` Python package with `__init__.py`, `db.py` (async engine factory), `config.py` (pydantic-settings base), `logging.py` (structured JSON logger), `embedder.py` (abstract `EmbedderInterface` + `SentenceTransformerEmbedder` implementation, shared by content-service and retrieval-service)
  - [✅] 1.3 Create `frontend/` directory with Next.js scaffold stub (`package.json` placeholder)
  - [✅] 1.4 Create `pyproject.toml` at repo root with ruff and black dev dependencies

### [✅] 2 Set Up Per-Service FastAPI Skeletons
Each of the 9 services from Task 1.1 gets a minimal FastAPI app with `/healthz` and its own `pyproject.toml`.

  - [✅] 2.1 Create `main.py` in each of the 9 service directories (api-gateway, orchestrator, retrieval-service, content-service, rbac-service, rfp-service, model-router, adapters, audit-service) with a FastAPI app, `/healthz` returning `{"status": "ok", "service": "<service-name>"}` where `<service-name>` is the directory name, and a lifespan hook for DB connection pool
  - [✅] 2.2 Create `pyproject.toml` in each of the 9 service directories declaring FastAPI, SQLAlchemy, psycopg, pydantic-settings, and `common` as dependencies; ruff + black in dev deps
  - [✅] 2.3 Create `Dockerfile` in each of the 9 service directories using `python:3.12-slim`, installs `common` via `pip install -e /common`, runs `uvicorn`

### [✅] 3 Configure Docker Compose Environment
Stand up the full local dev environment with infrastructure services and all app containers.

  - [✅] 3.1 Write `docker-compose.yml` with `postgres` (pgvector/pgvector:pg16), `redis` (redis:7-alpine), and one container per service with volume mounts for hot-reload
  - [✅] 3.2 Write `.env.example` with stubs for `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, `DEFAULT_TENANT_MODEL`
  - [✅] 3.3 Add `depends_on` and `healthcheck` directives so app containers wait for Postgres to be ready

### [✅] 4 Bootstrap Alembic Migration Toolchain
Configure Alembic and apply the baseline migration that enables pgvector.

  - [✅] 4.1 Initialise Alembic in `migrations/` directory; configure `env.py` to read `DATABASE_URL` from environment and import `common.db.Base` for autogenerate
  - [✅] 4.2 Write baseline migration `0001_enable_pgvector.py` that runs `CREATE EXTENSION IF NOT EXISTS vector`
  - [✅] 4.3 Verify `alembic upgrade head` applies cleanly against the Docker Compose Postgres; capture output in `migrations/README.md`


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
