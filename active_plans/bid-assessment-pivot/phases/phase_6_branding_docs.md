# Phase 6: Branding & Documentation

**Status:** Pending
**Planned Start:** 2026-07-08
**Target End:** 2026-07-14
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_6_branding_docs.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: Phase 5 | Next: None

---

## Detailed Objective

Close the loop on the "branded but generic" promise: surface tenant branding everywhere a user sees it, give system admins a way to edit it, and document the onboarding path for new customers. The phase has three threads — frontend `BrandThemeProvider` + admin page; gateway endpoints for reading and updating brand; documentation updates (README rewrite, spec.md additions, new onboarding playbook).

A standalone validation: copy `scripts/seeds/_example/` to `scripts/seeds/widgetco/`, edit it minimally, run `seed_tenant.py widgetco`, log in as a widgetco user, see widgetco branding throughout — including the report export. No code changes between Akkodis and widgetco.

Success: Akkodis branding is end-to-end (header logo, theme colours, report header/footer); editing brand vars via the admin page changes the UI on next page load; the second-tenant test produces a working alternate-branded instance through seed data only.

---

## Deliverables Snapshot

1. `GET /tenants/me` and `PATCH /tenants/me/brand` endpoints in `api-gateway` (or proxied to a small handler in `rfp-service`).
2. `frontend/components/branding/BrandThemeProvider.tsx` — wraps existing `ThemeProvider`; fetches `/tenants/me` once, sets CSS vars, exposes context for logo + display_name.
3. `frontend/app/layout.tsx` updated to mount `BrandThemeProvider`.
4. `frontend/components/AppShell.tsx` updated to render the tenant logo + display_name.
5. `frontend/app/(admin)/admin/branding/page.tsx` — system_admin-only editor for brand JSONB (logo upload + colour pickers + header/footer text).
6. `scripts/seeds/_example/` — template directory with placeholder content.
7. `scripts/seeds/widgetco/` — fixture used by the second-tenant validation test.
8. README rewrite leading with "Bid Assessment" as the primary value prop; existing "Quick Start" + new "Onboard a New Tenant" section.
9. `spec.md` additions covering the bid-assessment pipeline + new tables.
10. New `docs/onboarding-new-tenant.md` — one-page playbook.

---

## Acceptance Gates

- [ ] Gate 1: `GET /tenants/me` returns the seeded Akkodis tenant for an Akkodis user; CSS vars set from `brand.primary_color` / `brand.accent_color` are visible in the rendered HTML.
- [ ] Gate 2: `PATCH /tenants/me/brand` as a `system_admin` updates the tenant row; refreshing the page shows the new branding.
- [ ] Gate 3: An `end_user` cannot reach the branding admin page (`/(admin)/admin/branding` returns 403).
- [ ] Gate 4: Logo upload accepts SVG and PNG ≤2 MB; persisted to `/var/brand/<slug>/` volume.
- [ ] Gate 5: `seed_tenant.py widgetco` (using `seeds/_example/`) produces a working second tenant without any code changes. Logging in as a widgetco user shows widgetco branding throughout, including the exported report.
- [ ] Gate 6: README's "Quick Start" runs cleanly on a fresh checkout and reaches a working Akkodis demo. The "Onboard a New Tenant" section reaches a working widgetco demo.

---

## Scope

- In Scope:
  1. `GET /tenants/me` + `PATCH /tenants/me/brand` endpoints.
  2. Brand logo upload + local volume storage (`/var/brand/<slug>/`).
  3. `BrandThemeProvider` + AppShell integration.
  4. Branding admin page.
  5. `seeds/_example/` template directory.
  6. `seeds/widgetco/` validation fixture.
  7. Second-tenant validation test (integration).
  8. README rewrite.
  9. `spec.md` additions.
  10. `docs/onboarding-new-tenant.md`.
- Out of Scope:
  1. Live preview in the branding admin (changes apply on next reload).
  2. Multi-logo support (light + dark mode logos).
  3. Custom fonts.
  4. Per-tenant feature flags.
  5. CDN / object-storage backends for brand assets (deferred).
  6. Tenant self-signup.

---

## Interfaces & Dependencies

- Internal: `services/api-gateway/main.py`, `services/rfp-service/main.py` (or wherever the `tenants` row read/write lives), `frontend/components/ThemeProvider.tsx`, `frontend/components/AppShell.tsx`, `frontend/app/layout.tsx`, all the Phase 5 export templates.
- External: `pillow` (server-side logo validation), no new frontend packages.
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Brand variables don't propagate to existing components | Inconsistent look mid-page | Audit every component reading hard-coded colours; replace with CSS vars; lint rule (`stylelint-color-no-hex-named` or equivalent) flags new hard-codes. |
| Logo file too large; embed crashes weasyprint | Export fails | Server-side validation: SVG strip dangerous tags, PNG resize to 200x200 max before storage; reject >2 MB pre-resize. |
| Cached browser session retains old brand after PATCH | User reports "didn't change" | Document "refresh required" in the admin page; future: emit a `branding_updated` event for live propagation. |
| README rewrite makes the spec drift | Mismatched docs across files | README links to spec.md as canonical; spec.md links to the design doc as ultimate source of truth. |
| `seeds/_example/` becomes outdated as schemas evolve | Onboarding instructions break | Add a smoke test that runs `seed_tenant.py widgetco` from `seeds/_example/` as part of `scripts/test_workflows.py`. |

---

## Decision Log

- D1: Brand vars persist on the `tenants.brand` JSONB column (no separate `tenant_brands` table) — Status: Closed — Date: 2026-05-13
- D2: Logo storage on local volume in v1; S3/Azure adapter deferred — Status: Closed — Date: 2026-05-13
- D3: SVG and PNG accepted; ≤2 MB; sanitised server-side — Status: Closed — Date: 2026-05-13
- D4: No live preview in admin; changes apply on reload — Status: Closed — Date: 2026-05-13
- D5: README rewrite leads with bid assessment; answer drafting demoted to a downstream feature — Status: Closed — Date: 2026-05-13
- D6: Second-tenant validation is automated (smoke test) — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `services/api-gateway/main.py` — gains tenant brand routes
- `services/api-gateway/auth.py` — Phase 0 tenant_id loader (reused)
- `frontend/components/ThemeProvider.tsx` — wrapped by BrandThemeProvider
- `frontend/components/AppShell.tsx` — gains logo + display_name
- `frontend/app/layout.tsx` — mounts BrandThemeProvider
- `frontend/app/globals.css` — CSS var slots
- `frontend/lib/api.ts` — new branding client functions
- `README.md` — rewrite
- `spec.md` — additions
- `scripts/test_workflows.py` — smoke test extension
- `docker-compose.yml` — adds `brand_assets` volume

### Destination Files
- `frontend/components/branding/BrandThemeProvider.tsx`
- `frontend/app/(admin)/admin/branding/page.tsx`
- `frontend/components/branding/BrandingAdmin.tsx`
- `scripts/seeds/_example/` (template tree)
- `scripts/seeds/widgetco/` (fixture tenant)
- `docs/onboarding-new-tenant.md`
- `tests/integration/test_second_tenant_smoke.py`

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §6.1, §7.5, §9, §10.5

---

## Tasks

### [ ] 1 Implement /tenants/me endpoints
GET (any auth) + PATCH (system_admin) for brand.

  - [ ] 1.1 Add `GET /tenants/me` to `api-gateway/main.py` returning `{id, slug, display_name, brand}` for the request's tenant
  - [ ] 1.2 Add `PATCH /tenants/me/brand` accepting partial `brand JSONB` updates
  - [ ] 1.3 Logo upload route: `POST /tenants/me/brand/logo` accepting SVG/PNG ≤2 MB; sanitise SVG; resize PNG to ≤200x200; store at `/var/brand/<slug>/logo.<ext>`
  - [ ] 1.4 Static-serve `/brand/<slug>/...` (or proxy) so the frontend can `<img src="/brand/akkodis/logo.svg" />`
  - [ ] 1.5 Role check enforced at gateway
  - [ ] 1.6 Unit tests for happy path + role gate + invalid logo rejection

### [ ] 2 Build BrandThemeProvider
Wrap ThemeProvider; fetch tenant brand once; set CSS vars + context.

  - [ ] 2.1 `frontend/components/branding/BrandThemeProvider.tsx` — fetches `/tenants/me` on mount; sets `--brand-primary`, `--brand-accent` on `:root`; exposes `{logoUrl, displayName}` via React context
  - [ ] 2.2 Mount in `frontend/app/layout.tsx` between auth and ThemeProvider
  - [ ] 2.3 Update `frontend/components/AppShell.tsx` to render logo + display_name from context
  - [ ] 2.4 Update document `<title>` to include the tenant display_name

### [ ] 3 Convert hard-coded colours to CSS vars
Audit components reading hex colours; replace with `var(--brand-primary)` / `var(--brand-accent)`.

  - [ ] 3.1 Grep `frontend/` for hex colours and Tailwind class hard-codes
  - [ ] 3.2 Replace canonical brand uses with CSS-var equivalents
  - [ ] 3.3 Document the convention in a short comment in `globals.css`

### [ ] 4 Build branding admin page
system_admin-only editor for the brand JSONB.

  - [ ] 4.1 `frontend/components/branding/BrandingAdmin.tsx` — form with logo upload, two colour pickers, header text, footer text
  - [ ] 4.2 `frontend/app/(admin)/admin/branding/page.tsx` mounting the component
  - [ ] 4.3 Submit calls `PATCH /tenants/me/brand` (and `POST .../logo` separately if a new file is selected)
  - [ ] 4.4 Show a "Refresh to see changes" toast on success
  - [ ] 4.5 Role-gate the page in middleware or layout
  - [ ] 4.6 Add the page to admin nav in `AppShell.tsx`

### [ ] 5 Create seeds/_example/ template
Empty template that an onboarding engineer copies for a new tenant.

  - [ ] 5.1 Mirror `seeds/akkodis/` directory structure with placeholder content (TODOs, minimal valid rows)
  - [ ] 5.2 Include a `README.md` explaining each file's purpose
  - [ ] 5.3 Verify `seed_tenant.py _example` (or similar) produces a valid tenant — used as a smoke test

### [ ] 6 Create seeds/widgetco/ validation fixture
Concrete second tenant used by the smoke test.

  - [ ] 6.1 Copy `seeds/_example/` to `seeds/widgetco/`
  - [ ] 6.2 Edit slug, display_name, brand (different primary/accent colours, distinct logo)
  - [ ] 6.3 Add minimal seed data: 2 service lines, 1 industry, 1 certification, 1 snippet
  - [ ] 6.4 Verify `seed_tenant.py widgetco` runs idempotently

### [ ] 7 Add second-tenant smoke test
Automated validation that the "generic" promise holds.

  - [ ] 7.1 `tests/integration/test_second_tenant_smoke.py`: spin up a clean DB, run migrations, seed Akkodis + widgetco
  - [ ] 7.2 Create one user in widgetco, fetch JWT, call `/tenants/me`, assert widgetco branding
  - [ ] 7.3 Assert no Akkodis rows surface in any widgetco list
  - [ ] 7.4 Wire into `scripts/test_workflows.py`

### [ ] 8 Rewrite README
Lead with Bid Assessment; restructure quick-start; new onboarding section.

  - [ ] 8.1 Rewrite the top of `README.md` to lead with "Bid Assessment" as the primary value prop
  - [ ] 8.2 Demote answer drafting to a downstream feature in the overview
  - [ ] 8.3 Update the architecture diagram with the renamed `capability-service` and new pipeline
  - [ ] 8.4 Update the services table
  - [ ] 8.5 Add an "Onboarding a New Tenant" section linking to `docs/onboarding-new-tenant.md`
  - [ ] 8.6 Verify the README's commands run against a fresh checkout

### [ ] 9 Update spec.md
Add a Bid Assessment Pipeline section.

  - [ ] 9.1 Add a new top-level section to `spec.md` summarising the pipeline + agents
  - [ ] 9.2 Add the 7 assessment tables + 7 capability tables to the Data Model section
  - [ ] 9.3 Add the new endpoints to the API Overview section
  - [ ] 9.4 Link to the canonical design doc

### [ ] 10 Write onboarding playbook
One-page guide for onboarding a new tenant.

  - [ ] 10.1 `docs/onboarding-new-tenant.md` covering: copy `seeds/_example/` → edit → run `seed_tenant.py` → log in → verify brand → seed real capability data via admin UI
  - [ ] 10.2 Include screenshots of the branding admin page
  - [ ] 10.3 Cross-link from README

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
