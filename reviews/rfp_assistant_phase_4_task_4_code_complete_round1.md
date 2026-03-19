# Code Complete: rfp_assistant — Phase 4, Task 4 (Round 1)

**Task:** Implement POST /ask Pipeline
**Phase:** 4 — Orchestrator & Model Layer
**Date:** 2026-03-18

## Sub-tasks

- [x] 4.1 Implement `assemble_citations(chunks) -> list[Citation]` — map chunk to `{chunk_id, doc_id, snippet: text[:200]}`
- [x] 4.2 Implement `ask_pipeline(question, mode, rfp_id, user_ctx) -> AskResponse` — retrieve → prompt → route → generate → citations → audit
- [x] 4.3 Implement `POST /ask` FastAPI endpoint with auth, `ask_pipeline`, returns `{answer, citations}`
- [x] 4.4 Implement streaming variant: `stream=true` query param → `StreamingResponse` via `sse-starlette`
- [x] 4.5 Write `tests/test_ask.py` — mock retrieval and adapter; assert citations, prompt mode, audit row

## Files Changed

- `services/orchestrator/pipeline.py` — `call_retrieval_service`, `assemble_citations`, `compute_confidence`, `ask_pipeline`; adaptive disclosure logic
- `services/orchestrator/main.py` — `POST /ask` endpoint with streaming support via `sse-starlette`
- `services/orchestrator/tests/test_ask.py` — mocked retrieval + adapter tests

## Smoke Test

```
$ python -m pytest services/orchestrator/tests/test_ask.py -q
5 passed in 0.34s
```
