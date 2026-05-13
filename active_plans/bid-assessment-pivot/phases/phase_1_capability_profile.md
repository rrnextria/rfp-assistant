# Phase 1: Capability Profile

**Status:** Pending
**Planned Start:** 2026-05-21
**Target End:** 2026-05-28
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_1_capability_profile.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: Phase 0 | Next: Phase 2

---

## Detailed Objective

Model "what a tenant can deliver" across seven new tables, alongside the existing `products` table. The capability profile drives the BestFit and Eligibility agents in Phase 3, so the schema and embeddings need to be in place — and seeded for Akkodis — before assessment can run.

The phase adds CRUD endpoints to `capability-service` for each dimension, generates embeddings for `service_lines` (so requirement→service-line semantic matching is possible in BestFit), and ships a tabbed admin UI for managing the profile. The admin UI is the most consequential frontend addition outside the RFP workspace itself: Akkodis bid-desk leads will use it daily to curate certifications, partnerships, and rate cards.

Success: A `content_admin` can edit every capability dimension via the admin page; the Akkodis profile is seeded from YAML files (service lines, industries, geographies, certifications, contract vehicles, partnerships, rate cards, engagement sizes); `service_lines` embeddings are populated and indexed; tenancy-leak test extends to all new tables.

---

## Deliverables Snapshot

1. Migration `migrations/versions/0011_capability_profile.py` creating 7 capability tables + 2 M2M tables, all with `tenant_id` FK to `tenants`.
2. `services/capability-service/` gains 8 CRUD modules (one per dimension) plus the `/capabilities/profile` rollup endpoint.
3. `services/capability-service/embeddings.py` populates `service_lines.embedding` on create/update.
4. Akkodis seed expansion: 8 new YAML files under `scripts/seeds/akkodis/` (service_lines.yaml, industries.yaml, geographies.yaml, certifications.yaml, contract_vehicles.yaml, partnerships.yaml, rate_cards.yaml, engagement_sizes.yaml).
5. Frontend admin page `frontend/app/(admin)/admin/capabilities/page.tsx` with 8 tabs.
6. Reusable `frontend/components/capability/CapabilityDimensionTable.tsx` for the standard CRUD table pattern.
7. Tenancy-leak test extended to cover all 9 new tables.

---

## Acceptance Gates

- [ ] Gate 1: Alembic at revision 0011; round-trip test passes.
- [ ] Gate 2: `GET /capabilities/profile` returns all 8 dimensions for the Akkodis tenant after seed.
- [ ] Gate 3: Creating a new `service_line` populates an embedding within the same request (synchronous embed).
- [ ] Gate 4: `content_admin` can create, edit, and delete in every dimension via the admin UI; `end_user` is blocked at the write endpoints (403).
- [ ] Gate 5: Tenancy-leak test asserts cross-tenant queries return zero rows from all 9 new tables.

---

## Scope

- In Scope:
  1. 7 capability tables + 2 M2M tables (per spec §4.2).
  2. CRUD endpoints for each dimension + `/capabilities/profile` rollup.
  3. Synchronous embedding of `service_lines.description` on create/update.
  4. Frontend admin page with 8 tabs, reusable table component.
  5. Akkodis YAML seed data for all 8 dimensions.
  6. Role checks: writes require `content_admin` or `system_admin`; reads require any authenticated user.
  7. Tenancy-leak test extension.
- Out of Scope:
  1. Snippet library (Phase 2).
  2. Bid assessment agents that *consume* the profile (Phase 3).
  3. Rich UX (drag-drop reorder, bulk import) — basic table CRUD only.
  4. Per-dimension audit log views — falls back on the existing `audit_logs` query path.
  5. Validation that certifications haven't expired — surfaced read-only; flagging happens in Phase 3.

---

## Interfaces & Dependencies

- Internal: `common/db.py`, `common/embedder.py` (existing `EmbedderInterface`), `common/tenancy.py` (Phase 0), `services/api-gateway/proxy.py` (proxy routes added).
- External: `sentence-transformers/all-MiniLM-L6-v2` (already pinned), `sqlalchemy`, `psycopg`, `pyyaml`.
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Embedding model load time blows up per-request latency | Slow profile editing | Re-use the existing singleton embedder pattern from `content-service`; load once at service start. |
| Hierarchical service lines (parent_id) create cycles | Bad data corrupts the tree | API rejects requests whose `parent_id` would create a cycle (depth-limited BFS check); migration adds no DB-level constraint to avoid complexity. |
| M2M tables grow without indexes | Slow joins on `/capabilities/profile` rollup | Composite PK on `(service_line_id, industry_id)` etc. provides the lookup index naturally. |
| Frontend tabs over-fetch on every switch | Slow admin UX | `/capabilities/profile` returns all 8 dimensions in one payload; tabs are pure client-side filters. |
| Akkodis seed grows brittle (e.g., service_line→industry FK referenced before insert) | Seed fails mid-run | `seed_tenant.py` inserts in dependency order (industries, geographies → service_lines → M2M links). |

---

## Decision Log

- D1: `service_lines.parent_id` is NULLable (top-level practices have no parent) — Status: Closed — Date: 2026-05-13
- D2: Synchronous embedding on create/update (no background queue) — Status: Closed — Date: 2026-05-13
- D3: `rate_cards` carries effective_from/effective_until for time-bounded pricing — Status: Closed — Date: 2026-05-13
- D4: Capability writes require `content_admin` (not `system_admin`-only) — Status: Closed — Date: 2026-05-13
- D5: One admin page with 8 tabs (vs 8 separate pages) — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `common/common/embedder.py` — existing embedder interface
- `services/api-gateway/proxy.py` — adds proxy routes

### Destination Files
- `migrations/versions/0011_capability_profile.py`
- `services/capability-service/service_lines.py`
- `services/capability-service/industries.py`
- `services/capability-service/geographies.py`
- `services/capability-service/certifications.py`
- `services/capability-service/contract_vehicles.py`
- `services/capability-service/partnerships.py`
- `services/capability-service/rate_cards.py`
- `services/capability-service/engagement_sizes.py`
- `services/capability-service/profile.py` — rollup endpoint
- `services/capability-service/embeddings.py` — embed on create/update
- `scripts/seeds/akkodis/service_lines.yaml`
- `scripts/seeds/akkodis/industries.yaml`
- `scripts/seeds/akkodis/geographies.yaml`
- `scripts/seeds/akkodis/certifications.yaml`
- `scripts/seeds/akkodis/contract_vehicles.yaml`
- `scripts/seeds/akkodis/partnerships.yaml`
- `scripts/seeds/akkodis/rate_cards.yaml`
- `scripts/seeds/akkodis/engagement_sizes.yaml`
- `frontend/app/(admin)/admin/capabilities/page.tsx`
- `frontend/components/capability/CapabilityProfileAdmin.tsx`
- `frontend/components/capability/CapabilityDimensionTable.tsx`

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §4.2, §6.2, §7.3, §9.2

---

## Tasks

### [ ] 1 Create capability profile migration
Author migration 0011 creating 7 capability tables + 2 M2M tables, all with `tenant_id` FK to `tenants`.

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
Eight CRUD resources with standard shape, plus a `/capabilities/profile` rollup.

  - [ ] 2.1 Implement `service_lines.py`: GET list, POST, GET one, PATCH, DELETE; hierarchy cycle check on POST/PATCH
  - [ ] 2.2 Implement `industries.py`, `geographies.py`, `certifications.py` with the same shape
  - [ ] 2.3 Implement `contract_vehicles.py`, `partnerships.py`, `rate_cards.py`, `engagement_sizes.py`
  - [ ] 2.4 Implement `profile.py` rollup returning `{service_lines, industries, geographies, certifications, contract_vehicles, partnerships, rate_cards, engagement_sizes}` for the request's tenant
  - [ ] 2.5 Wire all routes into `main.py` with role checks (`content_admin`+ for writes, any for reads)
  - [ ] 2.6 Every query uses `common/tenancy.py:tenant_scope()`

### [ ] 3 Add synchronous embedding for service_lines
On `POST` and `PATCH` of a service line, embed `description` and persist to `embedding`.

  - [ ] 3.1 Create `services/capability-service/embeddings.py` exporting `embed_service_line(text) -> list[float]`
  - [ ] 3.2 Reuse the singleton embedder pattern from `content-service`
  - [ ] 3.3 In `service_lines.py` POST/PATCH handlers, invoke `embed_service_line(description)` and persist
  - [ ] 3.4 Add a unit test asserting non-null `embedding` after create

### [ ] 4 Expand Akkodis YAML seed for capability profile
Write 8 YAML files representing a realistic Akkodis profile.

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
A tabbed admin page with 8 tabs, sharing a reusable table component.

  - [ ] 5.1 Create `frontend/components/capability/CapabilityDimensionTable.tsx` — generic over a dimension's columns
  - [ ] 5.2 Create `frontend/components/capability/CapabilityProfileAdmin.tsx` — tab bar + active tab content
  - [ ] 5.3 Create `frontend/app/(admin)/admin/capabilities/page.tsx` mounting the component
  - [ ] 5.4 Hook into `/capabilities/profile` for initial load (single fetch, 8 tabs from one payload)
  - [ ] 5.5 Wire add/edit/delete flows through `frontend/lib/api.ts`
  - [ ] 5.6 Add the page to the admin nav in `frontend/components/AppShell.tsx`

### [ ] 6 Extend tenancy-leak test
Add coverage for all 9 new tables.

  - [ ] 6.1 In `tests/integration/test_tenancy_leak.py`, seed `widgetco` with one row in each capability dimension
  - [ ] 6.2 Assert that a `widgetco` user's `GET /capabilities/profile` excludes all Akkodis rows
  - [ ] 6.3 Assert similar isolation on direct dimension endpoints

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
