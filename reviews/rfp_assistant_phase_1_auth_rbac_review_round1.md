<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 2
MAJOR: 1
MINOR: 0
DECISIONS: 0
VERIFIED: 0
-->

# Phase 1: Auth, RBAC & Database Schema — Plan Review Round 1

**Stage:** phase_1_auth_rbac
**Round:** 1 of 5
**Verdict:** FIXES_REQUIRED

---

## Summary

Phase 1 covers auth, RBAC, and the complete database schema — the foundation that all subsequent phases depend on. Two blocker-level issues and one major issue were found. The blockers must be fixed before implementation begins, as they will cause runtime failures in the vector storage and portfolio subsystems.

---

## Findings

### B1 (Blocker): Vector dimension mismatch — Task 1.2 specifies `VECTOR(1536)`, model is 384-dim

**Location:** Task 1.2

**Finding:** Task 1.2 creates the `chunks` table with `embedding VECTOR(1536)`. However:
- Phase 2 Task 3.2 selects `all-MiniLM-L6-v2` as the embedding model, which produces 384-dimensional vectors.
- The project Decision Log (D7 in Phase 2) explicitly confirms 384-dim.
- pgvector requires the column dimension to exactly match the inserted vector. A mismatch causes an `invalid vector dimension` runtime error on every insert and search.

**Required fix:** Change `VECTOR(1536)` to `VECTOR(384)` in Task 1.2. Add a parenthetical noting this matches the `all-MiniLM-L6-v2` model.

### B2 (Blocker): `product_embeddings` table never defined in any migration

**Location:** Task 5.1

**Finding:** Task 5.1 creates `products` and `tenant_products` tables but omits `product_embeddings`. Phase 8 Task 1.1 explicitly inserts into `product_embeddings(product_id, embedding VECTOR(384))` as part of the product catalog implementation. Since the table is never created by any migration, Phase 8 will fail with a "relation does not exist" error.

**Required fix:** Add `product_embeddings(product_id UUID FK products, embedding VECTOR(384))` to the migration in Task 5.1, alongside `products` and `tenant_products`.

### M1 (Major): `rfps.raw_text TEXT` column referenced but never defined in schema

**Location:** Task 5.2 (missing); Phase 2 Task 5.1

**Finding:** Phase 2 Task 5.1 stores RFP document text in `rfps.raw_text`. The `rfps` table is defined in Task 1.3 as `rfps(id, customer, industry, region, created_by FK)` — no `raw_text` column. Task 5.2 adds Keystone extensions to `rfp_answers` and `rfp_requirements` but does not add the missing `rfps.raw_text TEXT` column. This will cause a "column does not exist" error when Phase 2 ingests RFP documents.

**Required fix:** Add `rfps.raw_text TEXT NULL` to the Keystone extensions migration in Task 5.2, so it is defined before Phase 2 uses it.

---

## Checklist Results

### Structure & Numbering
- [x] All formatting correct.

### Traceability
- [x] Tasks match objective and scope.
- [ ] **FAIL** — B1, B2, M1: schema definitions do not match usage in downstream phases.

### Consistency
- [x] Section ordering correct. Metadata complete.

### References
- [x] All sections present.

---

*Reviewer: Claude*
