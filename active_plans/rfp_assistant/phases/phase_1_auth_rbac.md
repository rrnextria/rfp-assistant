# Phase 1: Auth, RBAC & Database Schema

**Status:** Pending
**Planned Start:** 2026-03-23
**Target End:** 2026-03-27
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 0 | Next: Phase 2

---

## Detailed Objective

This phase delivers the complete Postgres schema (all tables from spec §3), JWT-based authentication, and role-based access control enforced as FastAPI middleware. It also wires up the audit logger so every authenticated request is persisted to `audit_logs`. No retrieval or generation logic is included — only the identity and permissions layer that all later phases depend on.

The three roles (`end_user`, `content_admin`, `system_admin`) are enforced at the middleware level before any handler executes. RBAC is implemented as a dependency-injection pattern in FastAPI so individual route handlers declare their required role declaratively. Team membership is loaded from the database on every request and cached in the request state for downstream use.

Success is defined as: a developer can register a user, obtain a JWT, and make authenticated requests; role violations return HTTP 403; all actions are written to `audit_logs`.

---

## Deliverables Snapshot

1. Alembic migration `0002_schema.py` creating all tables: `users`, `teams`, `user_teams`, `documents`, `chunks`, `rfps`, `rfp_questions`, `rfp_answers`, `audit_logs`.
2. `services/api-gateway/auth.py` — JWT issue/validate logic using `python-jose`; `POST /auth/login` and `POST /users` endpoints.
3. `services/rbac-service/rbac.py` — FastAPI dependency `require_role(*roles)` and `load_user_context(token)` returning `UserContext(user_id, role, teams)`.
4. `services/audit-service/logger.py` — `log_action(user_id, action, payload)` async function writing to `audit_logs`.
5. Integration tests: auth flow (register → login → protected endpoint → 401/403 cases) and RBAC enforcement for all three roles.

---

## Acceptance Gates

- [ ] Gate 1: `POST /users` creates a user; `POST /auth/login` returns a valid JWT; `GET /me` with that JWT returns the user record.
- [ ] Gate 2: A request with an `end_user` JWT to a `content_admin`-required route returns HTTP 403; a request with no JWT returns HTTP 401.
- [ ] Gate 3: Every authenticated request writes one row to `audit_logs` with correct `user_id`, `action`, and `payload`.
- [ ] Gate 4: `alembic upgrade head` applies migration `0002_schema.py` cleanly; all tables and indexes exist in Postgres.

---

## Scope

- In Scope:
  1. All Postgres tables from spec §3.1–3.8 (users, teams, user_teams, documents, chunks, rfps, rfp_questions, rfp_answers, audit_logs).
  2. JWT auth (`POST /auth/login`, `POST /users`, `GET /me`).
  3. RBAC middleware as FastAPI dependency injection.
  4. Audit logging middleware (every authenticated request).
  5. Rate limiting on auth endpoints (slowapi, 10 req/min per IP).
- Out of Scope:
  1. Document upload or chunk storage (Phase 2).
  2. Retrieval or generation (Phases 3–4).
  3. Password reset / OAuth (post-MVP).
  4. Frontend auth flows (Phase 6).

---

## Interfaces & Dependencies

- Internal: Phase 0 — `common/db.py` async engine, `common/config.py` settings, Alembic toolchain.
- External: `python-jose[cryptography]` (JWT), `passlib[bcrypt]` (password hashing), `slowapi` (rate limiting), `pytest-asyncio` + `httpx` (tests).
- Artifacts: Alembic migration `0002_schema.py`; `services/api-gateway/auth.py`; `services/rbac-service/rbac.py`; `services/audit-service/logger.py`; `tests/test_auth.py`, `tests/test_rbac.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| JWT secret rotation breaks existing tokens | All sessions invalidated | Document rotation procedure; use short-lived tokens (1h) + refresh tokens (future) |
| RBAC middleware bypassed by direct service-to-service calls | Security hole | Internal services accept only service-account tokens; document in CLAUDE.md |
| Audit log writes slow down hot path | Latency increase | Write audit logs via background task (FastAPI `BackgroundTasks`) — not in the critical path |

---

## Decision Log

- D1: `python-jose` chosen for JWT over `authlib` — simpler API for this use case — Status: Closed — Date: 2026-03-18
- D2: Audit writes via FastAPI `BackgroundTasks` to avoid latency impact — Status: Closed — Date: 2026-03-18
- D3: `chunks.metadata` stored as Postgres JSONB with GIN index for RBAC filter queries — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §3 Data Model, §6.3 Create User API, §10 Security

### Destination Files (new files this phase creates)
- `migrations/versions/0002_schema.py` — Full schema migration
- `services/api-gateway/auth.py` — JWT logic and auth endpoints
- `services/rbac-service/rbac.py` — RBAC dependency and UserContext
- `services/audit-service/logger.py` — Audit log writer
- `tests/test_auth.py` — Auth integration tests
- `tests/test_rbac.py` — RBAC enforcement tests

### Related Documentation (context only)
- `spec.md` — §3 Data Model, §10 Security
- `active_plans/rfp_assistant/phases/phase_0_foundation.md` — Foundation phase

---

## Tasks

### [✅] 1 Create Full Database Schema Migration
Write and apply the Alembic migration that creates all tables from spec §3.

  - [✅] 1.1 Create `migrations/versions/0002_schema.py` with tables: `users(id UUID PK, email UNIQUE, name, role, password_hash, created_at)`, `teams(id, name)`, `user_teams(user_id FK, team_id FK)`
  - [✅] 1.2 Add tables: `documents(id, title, status, created_by FK users, created_at, version)`, `chunks(id, document_id FK, text, embedding VECTOR(384), metadata JSONB)`; add GIN index on `chunks.metadata` and ivfflat index on `chunks.embedding` (384-dim matches `all-MiniLM-L6-v2` model selected in Phase 2)
  - [✅] 1.3 Add tables: `rfps(id, customer, industry, region, created_by FK)`, `rfp_questions(id, rfp_id FK, question)`, `rfp_answers(id, question_id FK, answer TEXT, approved BOOL, version INT)`
  - [✅] 1.4 Add table: `audit_logs(id, user_id FK, action VARCHAR, payload JSONB, created_at)`; apply migration and verify all tables exist

### [✅] 2 Implement JWT Authentication
Build the user registration, login, and token validation layer.

  - [✅] 2.1 Implement `POST /users` — accept `{email, role, teams[]}`, hash password with bcrypt, insert `users` row, assign teams via `user_teams`
  - [✅] 2.2 Implement `POST /auth/login` — validate credentials, issue JWT with claims `{sub: user_id, role, exp}`; apply slowapi rate limit (10/min per IP)
  - [✅] 2.3 Implement `GET /me` — validate JWT, return user record with teams; implement `get_current_user` FastAPI dependency that extracts and validates JWT from `Authorization: Bearer` header

### [✅] 3 Implement RBAC Middleware
Build the role-enforcement dependency and user-context loader used by all downstream services.

  - [✅] 3.1 Implement `UserContext` dataclass: `user_id`, `role`, `teams: list[str]`; implement `load_user_context(token)` that decodes JWT and fetches teams from DB
  - [✅] 3.2 Implement `require_role(*allowed_roles)` FastAPI dependency factory — raises HTTP 403 if `user.role not in allowed_roles`; raise HTTP 401 if token missing/invalid
  - [✅] 3.3 Write `tests/test_rbac.py` — verify `end_user` blocked from `content_admin` routes; `system_admin` passes all; invalid token → 401

### [✅] 4 Implement Audit Logging Middleware
Ensure every authenticated request is logged to `audit_logs` without blocking the response.

  - [✅] 4.1 Implement `log_action(user_id, action, payload)` async function in `services/audit-service/logger.py` — inserts row into `audit_logs`
  - [✅] 4.2 Wire `log_action` as a FastAPI `BackgroundTasks` call in a middleware that fires after every authenticated response; log `action=<METHOD> <path>` and sanitized payload (strip passwords)
  - [✅] 4.3 Write `tests/test_audit.py` — make an authenticated request, assert one `audit_logs` row written with correct `user_id` and `action`

### [✅] 5 Add Portfolio and Learning Schema Tables
Create database tables for the product catalog, portfolio assignments, RFP requirements, questionnaire items, and win/loss records required by the Keystone capabilities.

  - [✅] 5.1 Add `products(id UUID PK, name, vendor, category, description TEXT, features JSONB, created_at)`, `tenant_products(tenant_id, product_id)`, and `product_embeddings(product_id UUID FK products, embedding VECTOR(384))` tables via Alembic migration `0005_portfolio_schema.py`
  - [✅] 5.2 Add `rfp_requirements(id, rfp_id FK, text TEXT, category VARCHAR, scoring_criteria JSONB, is_questionnaire BOOL)` table; add `rfps.raw_text TEXT` column (used by Phase 2 RFP ingestion); add `rfp_answers.confidence FLOAT` column and `rfp_answers.detail_level ENUM('minimal','balanced','detailed')` column
  - [✅] 5.3 Add `questionnaire_items(id, rfp_requirement_id FK, question_type ENUM('yes_no','multiple_choice','numeric','text'), options JSONB, answer TEXT, confidence FLOAT, flagged BOOL)` table
  - [✅] 5.4 Add `win_loss_records(id, rfp_id FK, outcome ENUM('win','loss','no_decision'), notes TEXT, lessons_learned TEXT, created_at)` table; apply migration and verify all new tables exist


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
