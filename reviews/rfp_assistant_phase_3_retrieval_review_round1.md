<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 0
MAJOR: 1
MINOR: 0
DECISIONS: 0
VERIFIED: 0
-->

# Phase 3: Retrieval Service — Plan Review Round 1

**Stage:** phase_3_retrieval
**Round:** 1 of 5
**Verdict:** FIXES_REQUIRED

---

## Summary

Phase 3's retrieval logic is sound: RBAC-as-SQL-predicate is the correct architectural choice, the RRF implementation is well-specified, and the acceptance gates include the crucial latency requirement (< 500ms). One major finding must be addressed.

---

## Findings

### M1 (Major): Cross-service import of embedder from content-service violates service isolation

**Location:** Task 2.2 (original version)

**Finding:** Task 2.2 originally stated "Embed the query text inline using the same `EmbedderInterface` from Phase 2 (`services/content-service/embedder.py` imported via `common/`)." This is architecturally incorrect:
1. `services/content-service/embedder.py` is internal to content-service. Retrieval-service importing it directly creates a cross-service module dependency.
2. In Docker deployments, each service has its own virtualenv and filesystem. `services/content-service/` is not on retrieval-service's Python path.
3. The parenthetical "imported via `common/`" is contradictory — the file is not in `common/`.

The `EmbedderInterface` abstract class and `SentenceTransformerEmbedder` implementation must live in `common/embedder.py` (as established in Phase 0 Task 1.2) so both services can import it independently without coupling.

**Required fix:** Reword Task 2.2 to import from `common/embedder.py`.

---

## Checklist Results

### Traceability
- [ ] **FAIL** — M1: Task 2.2 creates a cross-service dependency that violates service isolation and will fail in Docker.

All other checklist items pass.

---

*Reviewer: Claude*
