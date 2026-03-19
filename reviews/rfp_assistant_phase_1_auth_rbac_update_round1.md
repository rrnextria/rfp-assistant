# Phase 1: Auth, RBAC & Database Schema — Planner Response Round 1

**Stage:** phase_1_auth_rbac
**Responding to:** review_round1.md
**Verdict received:** FIXES_REQUIRED (2 blockers, 1 major)

---

## Changes Made

### B1 addressed: VECTOR dimension corrected to 384

Task 1.2 updated: `embedding VECTOR(1536)` → `embedding VECTOR(384)`. Added parenthetical `(384-dim matches all-MiniLM-L6-v2 model selected in Phase 2)` for traceability.

### B2 addressed: `product_embeddings` table added to migration 0005

Task 5.1 updated to include `product_embeddings(product_id UUID FK products, embedding VECTOR(384))` in migration `0005_portfolio_schema.py` alongside `products` and `tenant_products`.

### M1 addressed: `rfps.raw_text TEXT` column added to Task 5.2

Task 5.2 updated to include `rfps.raw_text TEXT NULL` as part of the Keystone extensions migration. This column is now defined before Phase 2 RFP ingestion (Task 5.1) attempts to write to it.

---

*Planner: Claude*
