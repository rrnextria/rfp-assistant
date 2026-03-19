# Phase 2: Content Ingestion Pipeline

**Status:** Pending
**Planned Start:** 2026-03-28
**Target End:** 2026-04-03
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_2_content_ingestion.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 1 | Next: Phase 3

---

## Detailed Objective

This phase implements the complete document ingestion pipeline: upload, parse (PDF/DOCX), chunk by headings (~500 tokens), embed, and store chunks with RBAC metadata in pgvector. It also implements the content admin approval workflow so only approved documents surface in retrieval.

Documents go through a state machine: `pending` → `processing` → `ready` (awaiting approval) → `approved`. The pipeline is triggered synchronously for the MVP (no queue) but is designed so that a Redis/Kafka queue can be dropped in later without changing the chunking or embedding logic.

Embedding uses a locally-runnable model (sentence-transformers `all-MiniLM-L6-v2`, 384-dim) for the MVP to avoid external API dependency during ingestion, with a pluggable interface so a cloud embedding provider can be swapped in. The vector dimension is configurable at the `common/` layer.

Success is defined as: upload a PDF/DOCX, confirm chunks appear in `chunks` table with embeddings and correct metadata, then approve the document and confirm `approved=true` propagates to all chunks.

---

## Deliverables Snapshot

1. `POST /documents` endpoint (content-service) accepting multipart file + metadata JSON; validates metadata schema and stores document record.
2. Ingestion pipeline modules: `parser.py` (PDF/DOCX → text+headings), `chunker.py` (heading-based, ~500 token chunks), `embedder.py` (sentence-transformers, pluggable interface).
3. `POST /documents/{id}/process` internal trigger that runs the full parse→chunk→embed→store pipeline.
4. `PATCH /documents/{id}/approve` endpoint (content_admin only) — sets `approved=true` on document and all its chunks' metadata.
5. Integration tests: upload a real PDF, assert chunks in DB with correct RBAC metadata; approve and assert `approved=true`.

---

## Acceptance Gates

- [ ] Gate 1: `POST /documents` with a valid PDF + metadata returns HTTP 201 with `document_id`; document row exists in DB with `status=pending`.
- [ ] Gate 2: After processing, the `chunks` table contains rows for the document with non-null `embedding` vectors and `metadata` JSONB matching the uploaded metadata.
- [ ] Gate 3: `PATCH /documents/{id}/approve` by a `content_admin` sets all chunks' `metadata.approved=true`; an `end_user` making the same call gets HTTP 403.
- [ ] Gate 4: A chunk's metadata JSONB contains `{product, region, industry, approved, allowed_teams, allowed_roles}` exactly as specified in spec §3.6.

---

## Scope

- In Scope:
  1. Document upload endpoint with metadata validation.
  2. PDF parsing (pdfplumber) and DOCX parsing (python-docx).
  3. Heading-based chunking (~500 tokens, overlap 50 tokens).
  4. Embedding via sentence-transformers `all-MiniLM-L6-v2` (384-dim).
  5. pgvector chunk storage with JSONB metadata.
  6. Document approval workflow (content_admin role).
  7. Document status state machine (pending → processing → ready → approved).
- Out of Scope:
  1. Async queue (Redis/Kafka) — pipeline runs synchronously in MVP.
  2. Cloud embedding providers (OpenAI, Cohere) — pluggable interface designed in, implementation post-MVP.
  3. Reindexing on metadata update (post-MVP).
  4. Frontend upload UI (Phase 6).

---

## Interfaces & Dependencies

- Internal: Phase 1 — RBAC middleware (`require_role("content_admin")`), `common/db.py` async session, `chunks` and `documents` tables.
- External: `pdfplumber` (PDF parsing), `python-docx` (DOCX parsing), `sentence-transformers` (embeddings), `tiktoken` (token counting for chunking), `sqlalchemy` (async ORM).
- Artifacts: `services/content-service/parser.py`, `chunker.py`, `embedder.py`, `ingest.py`; updated `chunks` table with vector data.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Large PDFs (100+ pages) time out on sync processing | Upload endpoint hangs | Set 120s timeout; log warning for files >20MB; queue approach is the documented migration path |
| sentence-transformers model download slow in Docker build | CI/CD stalls | Pre-download model in Dockerfile build step and cache in image layer |
| Chunk boundary splits mid-sentence | Retrieval quality degrades | Use heading anchors as primary boundaries; fall back to sentence boundary within token window |
| Metadata schema drift between upload and stored chunks | RBAC filter misses chunks | Validate metadata with Pydantic model at upload time; same model used when writing to JSONB |

---

## Decision Log

- D1: `pdfplumber` over `pypdf` — better heading extraction via font-size heuristics — Status: Closed — Date: 2026-03-18
- D2: `all-MiniLM-L6-v2` (384-dim) for MVP embeddings — runs CPU-only, no external API cost — Status: Closed — Date: 2026-03-18
- D3: Synchronous ingestion for MVP; queue interface to be added post-MVP — Status: Closed — Date: 2026-03-18
- D4: VECTOR dimension set to 384 in `chunks.embedding` column (matching chosen model) — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §3.4 Documents, §3.5 Chunks, §3.6 Permissions, §6.2 Upload Document, §11 Ingestion Pipeline
- `migrations/versions/0002_schema.py` — Existing `documents` and `chunks` table definitions

### Destination Files (new files this phase creates)
- `services/content-service/parser.py` — PDF/DOCX text + heading extractor
- `services/content-service/chunker.py` — Heading-based token chunker
- `services/content-service/embedder.py` — Pluggable embedding interface + sentence-transformers impl
- `services/content-service/ingest.py` — Pipeline orchestrator (parse → chunk → embed → store)
- `services/content-service/routes.py` — Upload and approval endpoints
- `tests/test_ingestion.py` — Integration tests

### Related Documentation (context only)
- `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md` — Schema and RBAC dependencies
- `spec.md` — §11 Ingestion Pipeline

---

## Tasks

### [✅] 1 Implement Document Upload Endpoint
Create the `POST /documents` endpoint with metadata validation and document record creation.

  - [✅] 1.1 Define `DocumentMetadata` Pydantic model: `product: str`, `region: str`, `industry: str`, `allowed_teams: list[str]`, `allowed_roles: list[Literal["end_user","content_admin","system_admin"]]`
  - [✅] 1.2 Implement `POST /documents` — accept `multipart/form-data` with `file` (PDF/DOCX, max 50MB) and `metadata` (JSON string); validate with `DocumentMetadata`; store document row with `status=pending`; return `{document_id}`
  - [✅] 1.3 Add `content_admin` role requirement via `require_role("content_admin", "system_admin")` on the upload endpoint

### [✅] 2 Implement Document Parser
Extract structured text and headings from PDF and DOCX files.

  - [✅] 2.1 Implement `parse_pdf(file_bytes) -> list[Section]` using `pdfplumber` — extract text blocks grouped by heading (detected via font-size delta ≥ 20% above body); each `Section` has `heading: str | None` and `text: str`
  - [✅] 2.2 Implement `parse_docx(file_bytes) -> list[Section]` using `python-docx` — group paragraphs by `Heading 1/2/3` styles; fall back to paragraph breaks if no heading styles present
  - [✅] 2.3 Write `tests/test_parser.py` with fixture PDF and DOCX — assert section count > 0 and headings extracted correctly

### [✅] 3 Implement Chunker and Embedder
Convert parsed sections into token-bounded chunks and generate embeddings.

  - [✅] 3.1 Implement `chunk_sections(sections, max_tokens=500, overlap=50) -> list[Chunk]` using `tiktoken` (cl100k_base) — split at heading boundaries first, then token boundaries; each `Chunk` has `text`, `heading`, `token_count`
  - [✅] 3.2 Import `EmbedderInterface` and `SentenceTransformerEmbedder` from `common/embedder.py` (defined in Phase 0 Task 1.2); verify that `SentenceTransformerEmbedder` uses `all-MiniLM-L6-v2` (384-dim) and matches the `VECTOR(384)` column in `chunks.embedding`
  - [✅] 3.3 Write `tests/test_chunker.py` — assert no chunk exceeds 500 tokens; assert overlap text appears in consecutive chunks

### [✅] 4 Implement Ingestion Pipeline and Approval Workflow
Wire parse→chunk→embed→store and implement the document approval endpoint.

  - [✅] 4.1 Implement `ingest_document(document_id, file_bytes, metadata)` — orchestrate parser → chunker → embedder → bulk-insert chunks into `chunks` table with `metadata JSONB = {**metadata_dict, "approved": false}`; update document `status=ready`
  - [✅] 4.2 Trigger `ingest_document` synchronously after `POST /documents` returns (via FastAPI `BackgroundTasks` so HTTP 201 is returned immediately); update document `status=processing` before starting
  - [✅] 4.3 Implement `PATCH /documents/{id}/approve` (requires `content_admin`/`system_admin`) — set `documents.status=approved` and update all `chunks.metadata` JSONB to `approved=true` via a single `UPDATE chunks SET metadata = metadata || '{"approved":true}'` for the document's chunks
  - [✅] 4.4 Write `tests/test_ingestion.py` — upload fixture PDF, assert chunks in DB with correct metadata and non-null embeddings; call approve endpoint, assert `metadata.approved=true` on all chunks

### [✅] 5 Implement RFP Document Ingestion and Extraction
Parse uploaded RFP documents to extract structured requirements, scoring criteria, and questionnaire items for the Keystone orchestration pipeline.

  - [✅] 5.1 Implement `POST /rfps/{id}/ingest` (content_admin) — accept RFP document (PDF/DOCX); reuse parser from Task 2 to extract sections; store concatenated section text in `rfps.raw_text` (column added in Phase 1 Task 5.2)
  - [✅] 5.2 Implement `RequirementExtractionAgent.extract(rfp_text) -> list[Requirement]` — LLM-based extraction of requirements, scoring criteria, and constraints; each `Requirement` has `text`, `category`, `scoring_criteria JSONB`; bulk-insert into `rfp_requirements`
  - [✅] 5.3 Implement `QuestionnaireExtractionAgent.extract(rfp_text) -> list[QuestionnaireItem]` — detect structured questionnaires; classify each item by `question_type` (yes_no, multiple_choice, numeric, text); extract answer options for MCQ; insert into `questionnaire_items` with `flagged=false` and `confidence=null`
  - [✅] 5.4 Write `tests/test_rfp_extraction.py` — upload fixture RFP with known requirements and questionnaire; assert `rfp_requirements` rows created with correct categories; assert `questionnaire_items` rows with correct `question_type`


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
