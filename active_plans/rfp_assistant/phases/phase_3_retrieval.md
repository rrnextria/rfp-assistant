# Phase 3: Retrieval Service

**Status:** Pending
**Planned Start:** 2026-04-04
**Target End:** 2026-04-10
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_3_retrieval.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 2 | Next: Phase 4

---

## Detailed Objective

This phase implements the deterministic retrieval pipeline from spec §4 in full: RBAC pre-filter → hybrid search (vector + BM25) → merge/dedup → rerank → top-8-to-12 results. The pipeline is exposed as an internal service endpoint consumed by the orchestrator in Phase 4.

RBAC enforcement is the security-critical step: every retrieval query is filtered to chunks where `metadata.approved=true`, `metadata.allowed_roles` contains the requesting user's role, and `metadata.allowed_teams` intersects the user's teams. This filter runs as a Postgres WHERE clause — the model never sees non-permitted content.

Reranking for the MVP uses a simple reciprocal rank fusion (RRF) of the vector and keyword scores, avoiding a separate cross-encoder model dependency. The interface is designed for a cross-encoder to replace RRF in a later iteration without changing the caller API.

Success is defined as: given a query and a `UserContext`, the retrieval service returns 8–12 chunks that are all approved, all permitted for the user's role/teams, and are the highest-scoring results by the hybrid metric.

---

## Deliverables Snapshot

1. `services/retrieval-service/rbac_filter.py` — Builds the Postgres WHERE clause from a `UserContext`.
2. `services/retrieval-service/vector_search.py` — Cosine similarity search via pgvector (`<=>` operator), top 50, with RBAC filter applied as a CTE.
3. `services/retrieval-service/keyword_search.py` — Full-text BM25 search via `tsvector`/`tsquery` (Postgres FTS), top 50, with same RBAC filter.
4. `services/retrieval-service/reranker.py` — Reciprocal Rank Fusion merging and deduplication; returns top 8–12 chunks with `chunk_id`, `doc_id`, `text`, `score`.
5. `GET /retrieve` internal endpoint accepting `{query, user_context, filters}` and returning ranked chunks; integration tests verifying RBAC correctness.

---

## Acceptance Gates

- [ ] Gate 1: A retrieval query for a user with `role=end_user` and `teams=["sales"]` returns only chunks where `metadata.allowed_roles` contains `end_user` AND `metadata.allowed_teams` intersects `["sales"]` AND `metadata.approved=true`.
- [ ] Gate 2: A chunk belonging to a document not approved (`approved=false`) never appears in retrieval results regardless of role/team match.
- [ ] Gate 3: The endpoint returns between 8 and 12 chunks for a query that has ≥ 12 eligible results; returns all eligible chunks (< 8) when fewer exist.
- [ ] Gate 4: Retrieval latency for a query against 10,000 chunks is under 500ms (measured in integration test with `pytest-benchmark`).

---

## Scope

- In Scope:
  1. RBAC filter as Postgres WHERE predicate (approved, role, team intersection).
  2. Vector search via pgvector `<=>` cosine operator (top 50).
  3. Keyword search via Postgres FTS `tsvector`/`tsquery` (top 50).
  4. Hybrid merge via Reciprocal Rank Fusion.
  5. Optional metadata filter pass-through (product, industry) from query context.
  6. Internal `GET /retrieve` endpoint (not exposed through API gateway).
- Out of Scope:
  1. Cross-encoder reranker (post-MVP; RRF used for MVP).
  2. Elasticsearch/OpenSearch (pg_trgm + FTS sufficient for MVP).
  3. Query expansion or synonym handling (post-MVP).
  4. Caching of retrieval results (post-MVP).

---

## Interfaces & Dependencies

- Internal: Phase 1 — `UserContext` (role, teams); `chunks` table with `embedding VECTOR`, `metadata JSONB`, `text`. Phase 2 — approved chunks in DB.
- External: `pgvector` (already installed); Postgres `tsvector`/`tsquery` built-ins; `sqlalchemy` async for query building.
- Artifacts: `services/retrieval-service/rbac_filter.py`, `vector_search.py`, `keyword_search.py`, `reranker.py`, `routes.py`; `tests/test_retrieval.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| RBAC filter bug leaks non-permitted chunks | Security violation | Dedicated RBAC-correctness tests with adversarial users (wrong role, wrong team, unapproved doc) |
| ivfflat index not built yet → full scan on vector search | Slow at scale | Run `CREATE INDEX CONCURRENTLY` on `chunks.embedding` in Phase 2 migration; note in docs |
| RRF score calibration not tuned | Poor ranking quality | Expose `k` parameter (default 60) in config; document tuning guide |
| FTS not tokenizing domain-specific terms correctly | Missed keyword matches | Use `english` dictionary for MVP; document custom dictionary path for post-MVP |

---

## Decision Log

- D1: Reciprocal Rank Fusion for MVP reranking — no extra model/infra, good baseline quality — Status: Closed — Date: 2026-03-18
- D2: Postgres FTS (`tsvector`) over pg_trgm for keyword search — better recall for phrase queries — Status: Closed — Date: 2026-03-18
- D3: RBAC filter as SQL WHERE clause (not post-filter) — ensures no non-permitted data touches application memory — Status: Closed — Date: 2026-03-18
- D4: Internal-only endpoint (not routed through API gateway) — retrieval is called service-to-service, not by end users directly — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §4 Retrieval Pipeline, §3.5 Chunks, §3.6 Permissions
- `services/rbac-service/rbac.py` — `UserContext` definition (Phase 1)
- `migrations/versions/0002_schema.py` — `chunks` table schema

### Destination Files (new files this phase creates)
- `services/retrieval-service/rbac_filter.py` — RBAC WHERE predicate builder
- `services/retrieval-service/vector_search.py` — pgvector cosine search
- `services/retrieval-service/keyword_search.py` — Postgres FTS search
- `services/retrieval-service/reranker.py` — RRF merge and dedup
- `services/retrieval-service/routes.py` — Internal `/retrieve` endpoint
- `tests/test_retrieval.py` — RBAC and ranking integration tests

### Related Documentation (context only)
- `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md` — UserContext source
- `active_plans/rfp_assistant/phases/phase_2_content_ingestion.md` — Chunk data source
- `spec.md` — §4 Retrieval Pipeline

---

## Tasks

### [✅] 1 Implement RBAC Filter
Build the SQL predicate factory that enforces permission scoping on all retrieval queries.

  - [✅] 1.1 Implement `build_rbac_filter(user_ctx: UserContext) -> list[ColumnElement]` — returns SQLAlchemy WHERE clauses: `chunks.metadata['approved'].as_boolean() == True`, `chunks.metadata['allowed_roles'].contains(user_ctx.role)`, `chunks.metadata['allowed_teams'].overlap(user_ctx.teams)`
  - [✅] 1.2 Implement optional metadata filter: if `product` or `industry` provided in query, add `chunks.metadata['product'] == product` etc. to the WHERE list
  - [✅] 1.3 Write `tests/test_rbac_filter.py` — unit-test predicate generation; integration-test with DB rows that should and should not be visible for a given `UserContext`

### [✅] 2 Implement Vector Search
Query pgvector for the top-50 semantically similar chunks within RBAC scope.

  - [✅] 2.1 Implement `vector_search(query_embedding: list[float], rbac_filter, limit=50) -> list[RankedChunk]` using SQLAlchemy: `SELECT id, text, metadata, embedding <=> :qvec AS score FROM chunks WHERE <rbac> ORDER BY score LIMIT 50`
  - [✅] 2.2 Embed the query text inline by importing `SentenceTransformerEmbedder` from `common/embedder.py` (Phase 0 Task 1.2) — avoiding cross-service dependency on content-service
  - [✅] 2.3 Write `tests/test_vector_search.py` — insert 20 approved chunks for user's role, 5 non-approved; assert only approved chunks returned; assert result count ≤ 50

### [✅] 3 Implement Keyword Search
Query Postgres FTS for the top-50 keyword-matching chunks within RBAC scope.

  - [✅] 3.1 Add `tsvector` generated column `chunks.text_search` via new Alembic migration `0003_fts_index.py`: `ALTER TABLE chunks ADD COLUMN text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`; add GIN index
  - [✅] 3.2 Implement `keyword_search(query: str, rbac_filter, limit=50) -> list[RankedChunk]` using `plainto_tsquery` and `ts_rank_cd` scoring
  - [✅] 3.3 Write `tests/test_keyword_search.py` — assert keyword-matching chunks rank higher than non-matching; assert RBAC filter respected

### [✅] 4 Implement Hybrid Reranker and Retrieval Endpoint
Merge vector and keyword results via RRF and expose as internal service endpoint.

  - [✅] 4.1 Implement `reciprocal_rank_fusion(vector_results, keyword_results, k=60, top_n=12) -> list[RankedChunk]` — compute RRF score per chunk, deduplicate by `chunk_id`, return top `top_n`
  - [✅] 4.2 Implement `retrieve(query, user_ctx, filters, top_n=12)` orchestrator that calls `vector_search` + `keyword_search` in parallel (asyncio.gather), then `reciprocal_rank_fusion`
  - [✅] 4.3 Implement `GET /retrieve` internal endpoint: accept `{query: str, user_context: UserContextSchema, filters: dict}`, call `retrieve()`, return `{chunks: [{chunk_id, doc_id, text, score, metadata}]}`
  - [✅] 4.4 Write `tests/test_retrieval.py` — seed 30 approved and 10 unapproved chunks; assert endpoint returns 8–12 results; assert all returned chunks are RBAC-permitted


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
