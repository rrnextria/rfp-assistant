# Phase 2: Knowledge-Base Extensions

**Status:** Pending
**Planned Start:** 2026-05-29
**Target End:** 2026-06-03
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_2_knowledge_base.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: Phase 1 | Next: Phase 3

---

## Detailed Objective

Extend the knowledge base to support four categories of content (`product_doc`, `past_proposal`, `contract`, `boilerplate_snippet`, `general`), introduce a curated snippet library, and teach retrieval to weight chunks by category and topic-tag. Snippets are physically `documents` rows — no new table — but participate specially in chunking (one chunk per snippet) and retrieval (highest category boost, plus topic-tag boost).

The ExtractionAgent gains a tag-classification step so requirements emerge tagged against the tenant's current snippet vocabulary; ComplianceAgent in Phase 3 will use these tags to find matching snippets. The phase also adds a snippet admin page so `content_admin`s can author and approve boilerplate without going through generic document upload.

Success: A `content_admin` can author a snippet that appears at retrieval time when the query matches its topic; the same snippet's tags expand the vocabulary that the ExtractionAgent uses to classify new RFPs.

---

## Deliverables Snapshot

1. Migration `migrations/versions/0012_documents_category.py` adding `documents.category` VARCHAR with a NOT NULL default of `'general'`.
2. Snippet façade endpoints under `services/content-service`: `POST /snippets`, `GET /snippets`, `PATCH /snippets/{id}`, `DELETE /snippets/{id}`.
3. Chunker branch in `services/content-service/chunker.py` for `boilerplate_snippet` category: one chunk per snippet, no splitting.
4. Auto-approve logic: snippets authored by `content_admin`/`system_admin` skip the pending-approval state.
5. Category-weighted RRF in `services/retrieval-service/retrieve.py` with tenant-config-driven boost values.
6. Tag-classification extension to `ExtractionAgent` reading the tenant's union of `snippet.metadata.topic_tags` as the vocabulary.
7. Snippet admin page `frontend/app/(admin)/admin/snippets/page.tsx`.
8. Akkodis seed expansion: 3 starter snippets (`gdpr.md`, `soc2.md`, `sla_defaults.md`) with YAML front-matter for tags.

---

## Acceptance Gates

- [ ] Gate 1: Alembic at revision 0012; all existing documents migrate to `category='general'`; round-trip test passes.
- [ ] Gate 2: `POST /snippets` as a `content_admin` creates a `documents` row with `category='boilerplate_snippet'`, `status='approved'`, `metadata.topic_tags=[...]`, and emits exactly one `chunks` row.
- [ ] Gate 3: A retrieval query for "GDPR compliance" against the Akkodis tenant returns the GDPR snippet within the top 3 results, ahead of generic product docs covering the same topic.
- [ ] Gate 4: `ExtractionAgent` on a new RFP produces `rfp_requirements.tags` matching the current snippet vocabulary.
- [ ] Gate 5: Snippet admin page allows create / edit / archive with role gates respected.

---

## Scope

- In Scope:
  1. `documents.category` column + per-category metadata convention.
  2. Snippet façade endpoints + chunker branch + auto-approve logic.
  3. Category-weighted RRF in retrieval-service (tenant-config-driven).
  4. Tag-classification in ExtractionAgent.
  5. Snippet admin page (basic CRUD).
  6. 3 Akkodis starter snippets.
- Out of Scope:
  1. Snippet templating with variables (`{{customer_name}}`) — Phase-2 backlog.
  2. Diff / rollback UI for snippet versions — audit log captures changes; manual rollback by re-edit.
  3. Auto-generation of snippets from past proposals — Phase-2 backlog.
  4. Multilingual snippets.
  5. Per-tenant separate snippet stores (snippets live in the same `documents` table, isolated by `tenant_id`).

---

## Interfaces & Dependencies

- Internal: `services/content-service/chunker.py` (existing), `services/retrieval-service/retrieve.py` (existing RRF), `services/orchestrator/agents.py` (existing ExtractionAgent), `common/tenancy.py`, `common/embedder.py`.
- External: `pyyaml` (for snippet front-matter), `python-frontmatter` (optional convenience).
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Category-weighted RRF unintentionally promotes irrelevant snippets | Generic queries surface unrelated boilerplate | Boosts are additive on top of RRF (not replacement); category boost is only +0.15 — won't dominate a near-zero RRF score. |
| Tag vocabulary changes between extraction and assessment runs | Stale tags on old requirements | Vocabulary is fetched at extraction time and stored on the row; no retroactive rewrite. Re-extracting an RFP refreshes tags. |
| Auto-approve risk: a junior `content_admin` ships an unreviewed snippet to retrieval immediately | Bad snippet leaks into answers | Audit log captures the create; `PATCH` on snippet body resets to `pending_approval` — re-approval required. |
| Existing `documents` rows without a `category` value break retrieval | Hidden chunks at query time | Migration sets `category='general'` for all existing rows; retrieval category-boost map has `general` at 0 (no behaviour change). |
| Single-chunk snippets exceed the embedder's max token length | Embedding fails | Cap snippet body at the embedder's known limit (256 tokens for MiniLM); API rejects longer bodies with 422. |

---

## Decision Log

- D1: One chunk per snippet (no splitting) — Status: Closed — Date: 2026-05-13
- D2: Auto-approve when author is `content_admin`/`system_admin`; require approval if `end_user` — Status: Closed — Date: 2026-05-13
- D3: PATCH on snippet body resets to `pending_approval` — Status: Closed — Date: 2026-05-13
- D4: Category-weighted RRF; boosts read from `tenants.config.retrieval.category_boosts` — Status: Closed — Date: 2026-05-13
- D5: Tag vocabulary is per-tenant and defined by the snippet library itself — Status: Closed — Date: 2026-05-13
- D6: Snippet body capped at the embedder's max token length — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `services/content-service/chunker.py` — existing splitter; gains snippet branch
- `services/content-service/ingestion.py` — existing pipeline; honours category
- `services/content-service/main.py` — gains snippet routes
- `services/retrieval-service/retrieve.py` — gains category boost + topic-tag boost
- `services/orchestrator/agents.py` — ExtractionAgent gains tag classification
- `services/orchestrator/prompts.py` — extraction prompt updated for tag output
- `common/common/embedder.py` — existing singleton

### Destination Files
- `migrations/versions/0012_documents_category.py`
- `scripts/seeds/akkodis/snippets/gdpr.md`
- `scripts/seeds/akkodis/snippets/soc2.md`
- `scripts/seeds/akkodis/snippets/sla_defaults.md`
- `frontend/app/(admin)/admin/snippets/page.tsx`
- `frontend/components/snippets/SnippetLibraryAdmin.tsx`

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §4.4, §6.3, §8

---

## Tasks

### [ ] 1 Add documents.category migration
Add `category VARCHAR NOT NULL DEFAULT 'general'` to `documents`. Backfill existing rows.

  - [ ] 1.1 Write `0012_documents_category.py`
  - [ ] 1.2 `ALTER TABLE documents ADD COLUMN category VARCHAR NOT NULL DEFAULT 'general'`
  - [ ] 1.3 No backfill needed for existing rows — default applies; verify all rows have a value
  - [ ] 1.4 Add an index on `(tenant_id, category)`
  - [ ] 1.5 Provide a working `downgrade()` dropping the column and index

### [ ] 2 Implement snippet façade endpoints
Four endpoints in `content-service` wrapping `documents` rows with `category='boilerplate_snippet'`.

  - [ ] 2.1 `POST /snippets` — body `{title, body, topic_tags[]}`; creates document with category + metadata
  - [ ] 2.2 Auto-approve when caller has `content_admin`/`system_admin` role
  - [ ] 2.3 `GET /snippets?topic=...&q=...` — filter by topic_tag intersection + free-text on body
  - [ ] 2.4 `PATCH /snippets/{id}` — increment `metadata.version`, rewrite body, reset to `pending_approval`
  - [ ] 2.5 `DELETE /snippets/{id}` — soft-delete (status='archived')
  - [ ] 2.6 Body length validation: reject >256 tokens (MiniLM max) with 422
  - [ ] 2.7 Wire routes through `api-gateway` proxy

### [ ] 3 Add chunker branch for snippets
In `chunker.py`, when `document.category == 'boilerplate_snippet'`, emit one chunk and skip splitting.

  - [ ] 3.1 Add the conditional branch in `chunk_document()`
  - [ ] 3.2 Single-chunk: `position=0`, full body, no overlap
  - [ ] 3.3 Unit test: a snippet with multi-paragraph body produces exactly one chunk

### [ ] 4 Implement category-weighted RRF in retrieval
Apply category boost and topic-tag boost on top of the existing RRF score.

  - [ ] 4.1 Read `tenants.config.retrieval.category_boosts` once per request
  - [ ] 4.2 After RRF fusion, add `category_boost[chunk.document.category]` to each result
  - [ ] 4.3 If `chunk.document.category == 'boilerplate_snippet'` AND any of its `topic_tags` intersects the query's classified tags, add +0.10
  - [ ] 4.4 Add tenant_id filter to all retrieval queries (calls `common/tenancy.py:tenant_scope`)
  - [ ] 4.5 Unit test: a snippet with matching tag outranks a generic chunk with similar text

### [ ] 5 Add tag classification to ExtractionAgent
ExtractionAgent now emits `tags: list[str]` on each requirement, classified against the tenant's current snippet vocabulary.

  - [ ] 5.1 In `services/orchestrator/agents.py:ExtractionAgent`, fetch the tenant's snippet topic_tags via `content-service`
  - [ ] 5.2 Update the extraction prompt in `prompts.py` to instruct the LLM to assign 0+ tags per requirement from the provided vocabulary
  - [ ] 5.3 Update the Pydantic `Requirement` schema to include `tags: list[str]`
  - [ ] 5.4 Persist `tags` in `rfp_requirements.tags TEXT[]` (add a migration column inline with 0012 or as 0012b)
  - [ ] 5.5 Integration test: extract an RFP that mentions GDPR; assert the matching requirement has `["gdpr"]` in its tags

### [ ] 6 Build snippet admin page (frontend)
A page listing snippets with create / edit / archive actions.

  - [ ] 6.1 Create `frontend/components/snippets/SnippetLibraryAdmin.tsx` with a search box, tag filter, and list
  - [ ] 6.2 Modal for create/edit with title, body (multi-line), tags (chip input)
  - [ ] 6.3 Archive action with confirmation
  - [ ] 6.4 Create `frontend/app/(admin)/admin/snippets/page.tsx` mounting the component
  - [ ] 6.5 Wire `frontend/lib/api.ts` snippet functions
  - [ ] 6.6 Add the page to admin nav in `AppShell.tsx`

### [ ] 7 Seed Akkodis snippets
3 starter snippets with YAML front-matter capturing topic_tags.

  - [ ] 7.1 `scripts/seeds/akkodis/snippets/gdpr.md` — GDPR statement, tags `[gdpr, data_residency, privacy]`
  - [ ] 7.2 `scripts/seeds/akkodis/snippets/soc2.md` — SOC 2 attestation, tags `[soc2, security, compliance]`
  - [ ] 7.3 `scripts/seeds/akkodis/snippets/sla_defaults.md` — SLA defaults, tags `[sla, availability, support]`
  - [ ] 7.4 Extend `seed_tenant.py` to glob `snippets/*.md`, parse front-matter, call `POST /snippets`
  - [ ] 7.5 Verify seed is idempotent — re-running doesn't duplicate

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
