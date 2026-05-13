# Phase 0: Foundation — Tenants & Service Rename

**Status:** Pending
**Planned Start:** 2026-05-14
**Target End:** 2026-05-20
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_0_foundation.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: None | Next: Phase 1

---

## Detailed Objective

Establish the foundation every later phase depends on: a real `tenants` table, a `tenant_id` column on every relevant existing row, and a `common/tenancy.py` helper that makes tenant-scoping discipline visible in code review. In parallel, rename `portfolio-service` to `capability-service` so the broader scope of the renamed service (full capability profile in Phase 1) lands without a confusing legacy name.

The phase is the only one that touches existing data structurally. Once it merges, every subsequent phase is additive. The migration plan splits the work across two alembic files (nullable+backfill, then NOT NULL+FK) so a partial failure on a real deployment is recoverable without re-running the backfill. The service rename is mechanical but high-risk-of-misses: a single missed `os.environ.get("PORTFOLIO_SERVICE_URL")` results in a silent inter-service failure. The phase ships only when the existing demo flows (login, list RFPs, generate an answer, approve a document) all still work end-to-end on the Akkodis-seeded stack.

Success: Alembic revision 0010 is head; every existing table has a non-null `tenant_id` referencing the seeded Akkodis tenant; `capability-service` is healthy on port 8010; `seed_tenant.py akkodis` runs idempotently; tenancy-leak test passes for the (still small) set of tenant-scoped queries.

---

## Deliverables Snapshot

1. Migrations: `migrations/versions/0009_tenants_table_and_backfill.py` (creates `tenants`, seeds Akkodis row, adds nullable `tenant_id` columns, backfills); `migrations/versions/0010_tenants_not_null_and_fks.py` (locks down NOT NULL + FK + indexes).
2. Helper: `common/tenancy.py` exporting `tenant_scope(query, tenant_id, table)`.
3. Renamed service directory: `services/capability-service/` (formerly `services/portfolio-service/`), with Dockerfile, pyproject.toml, and main.py path-renamed and imports updated.
4. Updated `docker-compose.yml` with the new service name and `CAPABILITY_SERVICE_URL` env var; updated env var references across all callers (`api-gateway`, `orchestrator`, `rfp-service`).
5. New `scripts/seed_tenant.py` and `scripts/seeds/akkodis/tenant.yaml` providing the initial Akkodis tenant data; `scripts/seed_demo.py` refactored to invoke `seed_tenant.py`.
6. Tenancy-leak integration test seeding two tenants and asserting cross-tenant isolation for the queries that exist after Phase 0 (users, documents, products).
7. Migration round-trip test in `scripts/test_workflows.py` (clean DB → `upgrade head` → `downgrade base` → `upgrade head`).

---

## Acceptance Gates

- [ ] Gate 1: Alembic at revision 0010 in a fresh database; `alembic downgrade base` succeeds; `alembic upgrade head` re-applies cleanly.
- [ ] Gate 2: Every row in every tenant-scoped table has `tenant_id` set to the seeded Akkodis tenant after migration of an existing seeded database.
- [ ] Gate 3: `docker compose up -d --build` produces a healthy stack with `capability-service` on port 8010 and no references to `portfolio-service` in any active file (excluding migration history comments).
- [ ] Gate 4: Existing demo flows pass — login as `admin@demo.com`, list RFPs, view an existing answer — without regression.
- [ ] Gate 5: Tenancy-leak test seeds two tenants and confirms cross-tenant queries return no rows from the other tenant.
- [ ] Gate 6: `seed_tenant.py akkodis` is idempotent — running it twice produces zero changes on the second run.

---

## Scope

- In Scope:
  1. New `tenants` table + Akkodis seed row.
  2. `tenant_id` column added to: `users`, `documents`, `products`, `rfps`, `rfp_questions`, `rfp_answers`, `audit_logs`, `win_loss_records`, `companies`, `analytics_events` (and any other existing tenant-scoped table — sweep `migrations/versions/`).
  3. Two-migration rollout (nullable + backfill, then NOT NULL + FK).
  4. `common/tenancy.py` helper.
  5. Rename `portfolio-service` → `capability-service` across code, compose, Dockerfile, env vars, README.
  6. `scripts/seed_tenant.py` generic bootstrap script.
  7. `scripts/seeds/akkodis/tenant.yaml` seed file (slug, display_name, brand defaults, empty config).
  8. Tenancy-leak integration test (basic version covering Phase-0 tables).
  9. Migration round-trip test.
- Out of Scope:
  1. Capability profile tables (Phase 1).
  2. `documents.category` enum (Phase 2).
  3. Bid assessment tables (Phase 3).
  4. Frontend changes (Phase 4).
  5. Branding UI / report templates (Phases 5–6).
  6. Per-tenant Postgres schemas (deferred).
  7. Tenant self-signup or in-product tenant creation (deferred).

---

## Interfaces & Dependencies

- Internal: `common/db.py` (existing Base/engine), `services/api-gateway/auth.py` (gains tenant_id attachment to request state at the gateway layer).
- External: `alembic`, `sqlalchemy`, `psycopg`, `pyyaml` (for seed-file parsing in `seed_tenant.py`).
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Backfill leaves rows with NULL `tenant_id` and 0010 fails | Stuck migration | 0009 backfills all existing rows in one transaction before 0010 attempts NOT NULL; 0010 explicitly verifies no NULLs before altering. |
| A caller still references `PORTFOLIO_SERVICE_URL` after rename | Inter-service call fails at runtime | Single grep sweep: `grep -rni "portfolio" services/ scripts/ docker-compose.yml`; integration smoke test after compose rebuild. |
| `users.tenant_config` column is conflated with the new `tenants.config` | Confused config resolution at request time | Document the merge order (tenant.config ← user.tenant_config) in `common/tenancy.py` docstring; integration test asserts merge semantics. |
| Existing migrations break because they import the old service name | Replay fails | No migrations import the service code — they're SQL-shaped Python. Sweep `migrations/versions/` to confirm. |
| Rename loses git history on the service directory | Reviewers can't trace blame | Use `git mv` for the directory rename; CI verifies file count parity. |

---

## Decision Log

- D1: Two-migration split (0009 nullable+backfill, 0010 NOT NULL+FK) — Status: Closed — Date: 2026-05-13
- D2: Rename via `git mv`, not delete+create — Status: Closed — Date: 2026-05-13
- D3: `seed_tenant.py` is a brand-new generic script; `seed_demo.py` calls into it — Status: Closed — Date: 2026-05-13
- D4: `common/tenancy.py` is a single function, not a class hierarchy — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `services/portfolio-service/main.py` — to be renamed/moved
- `services/portfolio-service/Dockerfile` — path update
- `services/portfolio-service/pyproject.toml` — name field
- `docker-compose.yml` — service block rename + env var update
- `services/api-gateway/main.py` — proxy route rename
- `services/orchestrator/main.py` — any `PORTFOLIO_SERVICE_URL` references
- `services/rfp-service/main.py` — any `PORTFOLIO_SERVICE_URL` references
- `services/api-gateway/auth.py` — tenant_id attachment to request state
- `common/common/db.py` — base Session factory
- `scripts/seed_demo.py` — refactored to invoke seed_tenant
- `scripts/test_workflows.py` — migration round-trip test added
- `migrations/versions/0008_companies.py` — current head
- `README.md` — service table + commands

### Destination Files
- `migrations/versions/0009_tenants_table_and_backfill.py`
- `migrations/versions/0010_tenants_not_null_and_fks.py`
- `common/tenancy.py`
- `services/capability-service/` (renamed directory)
- `scripts/seed_tenant.py`
- `scripts/seeds/akkodis/tenant.yaml`
- `tests/integration/test_tenancy_leak.py`

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §4.1, §4.5, §9
- `how_to/guides/code_review.md`

---

## Tasks

### [ ] 1 Create tenants table and backfill migration
Author migration 0009 — create `tenants`, seed Akkodis row, add nullable `tenant_id` to all existing tenant-scoped tables, backfill.

  - [ ] 1.1 Sweep `migrations/versions/` to enumerate every table that should be tenant-scoped
  - [ ] 1.2 Write `0009_tenants_table_and_backfill.py` creating `tenants(id, slug UNIQUE, display_name, brand JSONB, config JSONB, created_at)`
  - [ ] 1.3 Insert the seed Akkodis tenant row in the same migration (UUID stable via deterministic seed)
  - [ ] 1.4 Add nullable `tenant_id UUID` columns to: `users`, `documents`, `products`, `rfps`, `rfp_questions`, `rfp_answers`, `audit_logs`, `win_loss_records`, `companies`, `analytics_events` (plus any others found in 1.1)
  - [ ] 1.5 Backfill all existing rows in each of those tables to the Akkodis tenant
  - [ ] 1.6 Run `alembic upgrade head` against the existing seeded database and verify no rows are left NULL

### [ ] 2 Lock down tenant_id with NOT NULL, FK, and indexes
Author migration 0010 — verify no NULLs, alter columns to NOT NULL, add FKs, add `(tenant_id, ...)` indexes where listed pages are common.

  - [ ] 2.1 Write `0010_tenants_not_null_and_fks.py` opening with an explicit `SELECT COUNT(*) WHERE tenant_id IS NULL` check that raises on any non-zero count
  - [ ] 2.2 `ALTER COLUMN tenant_id SET NOT NULL` on every column added in 1.4
  - [ ] 2.3 Add FK from each `tenant_id` to `tenants.id`
  - [ ] 2.4 Create indexes on `(tenant_id)` on hot tables (`documents`, `rfps`, `audit_logs`, `chunks`)
  - [ ] 2.5 Provide a working `downgrade()` that drops FKs, drops indexes, sets columns NULLable, drops the `tenants` table

### [ ] 3 Add common/tenancy.py helper
Single function `tenant_scope(query, tenant_id, table)` that returns the query with a tenant_id filter applied. Used by every tenant-scoped query.

  - [ ] 3.1 Implement `tenant_scope` in `common/tenancy.py`
  - [ ] 3.2 Add a docstring documenting the effective-config merge order (`tenants.config` ← `users.tenant_config`)
  - [ ] 3.3 Add a unit test in `common/tests/test_tenancy.py` covering the helper

### [ ] 4 Rename portfolio-service to capability-service
Mechanical rename across code, compose, Dockerfile, env vars, README, and tests. Use `git mv` for the directory.

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
Generic tenant bootstrap script reading `scripts/seeds/<slug>/tenant.yaml`. Refactor existing `seed_demo.py` to invoke it for Akkodis.

  - [ ] 5.1 Create `scripts/seed_tenant.py` accepting a slug, reading `scripts/seeds/<slug>/tenant.yaml`, upserting the `tenants` row
  - [ ] 5.2 Create `scripts/seeds/akkodis/tenant.yaml` with slug, display_name, brand defaults (primary_color, accent_color placeholders), empty config
  - [ ] 5.3 Refactor `scripts/seed_demo.py` to call `seed_tenant("akkodis")` before any existing seed work
  - [ ] 5.4 Existing seed inserts (users, products, documents, RFPs) gain `tenant_id` references to the Akkodis tenant
  - [ ] 5.5 Verify idempotency — run the seed twice, confirm no duplicates

### [ ] 6 Attach tenant_id to request state at the gateway
Modify `services/api-gateway/auth.py` so the JWT-decoded user's `tenant_id` is loaded and attached to `request.state.tenant_id` for downstream propagation.

  - [ ] 6.1 In `auth.py`, after JWT decode, load `users.tenant_id` via the existing async session
  - [ ] 6.2 Attach `tenant_id` to `request.state`
  - [ ] 6.3 In `services/api-gateway/proxy.py` (or main.py), forward `tenant_id` to downstream services as an `X-Tenant-Id` header
  - [ ] 6.4 Add a unit test verifying the header is propagated

### [ ] 7 Add tenancy-leak integration test
Two-tenant fixture; seed each with a user and a document; assert no cross-tenant rows surface in any list query.

  - [ ] 7.1 Add `tests/integration/test_tenancy_leak.py` with a fixture that creates `akkodis` and `widgetco` tenants
  - [ ] 7.2 Seed one user and one document per tenant
  - [ ] 7.3 Assert `GET /documents` as a `widgetco` user returns zero `akkodis` rows
  - [ ] 7.4 Assert `GET /users` (admin) is correctly scoped
  - [ ] 7.5 Wire the test into `scripts/test_workflows.py`

### [ ] 8 Add migration round-trip test
Verify `upgrade head → downgrade base → upgrade head` succeeds end-to-end against a clean Postgres.

  - [ ] 8.1 Extend `scripts/test_workflows.py` with a `test_migration_roundtrip` step
  - [ ] 8.2 Use a disposable database (`rfpassistant_test_migrate` or similar)
  - [ ] 8.3 Run the three steps and assert non-zero exit on any failure

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile <slug>` if checkmarks appear stale.

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
