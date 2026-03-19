# Phase 4: Orchestrator & Model Layer

**Status:** Pending
**Planned Start:** 2026-04-11
**Target End:** 2026-04-18
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 3 | Next: Phase 5

---

## Detailed Objective

This phase implements the core `POST /ask` pipeline from spec §5 end-to-end: auth check → load user context → call retrieval-service → build prompt by mode → route to model adapter → assemble response with citations → persist audit → return. It also delivers three model adapters (Claude, Gemini, Ollama) conforming to the `ModelAdapter` interface from spec §8, and the model router that selects adapters based on tenant config.

The orchestrator is the central intelligence of the system. It is mode-aware: the prompt template changes for `answer`, `draft`, `review`, and `gap` modes (spec §7). Citation assembly ensures every answer references the source chunk IDs so the frontend can render source links.

The model router implements tenant-level provider preference with a fallback chain: if the primary adapter raises an error, the router tries the fallback provider before returning an error to the caller. This makes the system resilient to individual provider outages.

Success is defined as: a valid `POST /ask` request with an authenticated user, a question, and a mode returns a coherent answer with citations. Switching the tenant's preferred provider in config routes to the correct adapter without code changes.

---

## Deliverables Snapshot

1. `services/orchestrator/pipeline.py` — Full `POST /ask` pipeline: retrieval call → prompt build → model route → citation assemble → audit → return.
2. `services/adapters/base.py` — `ModelAdapter` abstract class with `generate(prompt, context) -> GenerateResult` and `stream(prompt, context) -> AsyncIterator[str]`.
3. `services/adapters/claude.py`, `gemini.py`, `ollama.py` — Three concrete adapters; each handles its SDK's error types and maps to a common `AdapterError`.
4. `services/model-router/router.py` — `select(tenant_id, mode) -> ModelAdapter` with primary + fallback provider from tenant config; fallback on `AdapterError`.
5. `services/orchestrator/prompts.py` — Prompt builder for all four modes (answer, draft, review, gap) using spec §7 templates.

---

## Acceptance Gates

- [ ] Gate 1: `POST /ask` with `mode=answer` and a question that matches ingested content returns an answer with at least one citation (`chunk_id`, `doc_id`, `snippet`).
- [ ] Gate 2: Switching the tenant config's preferred provider from `claude` to `ollama` causes the next request to route to the Ollama adapter without restarting the service.
- [ ] Gate 3: If the primary adapter raises `AdapterError`, the router retries with the fallback provider and the request succeeds.
- [ ] Gate 4: Each of the four modes (`answer`, `draft`, `review`, `gap`) produces a differently-structured prompt as defined in spec §7; this is verified by unit tests on `prompts.py`.
- [ ] Gate 5: Every `POST /ask` request produces an `audit_logs` row with `action="ask"` and `payload` containing `{question, mode, rfp_id, model_used}`.

---

## Scope

- In Scope:
  1. `POST /ask` pipeline orchestration (spec §5).
  2. `ModelAdapter` interface and three adapters: Claude (Anthropic SDK), Gemini (Google GenAI SDK), Ollama (HTTP REST).
  3. Model router with tenant config + fallback chain.
  4. Prompt templates for all four modes (spec §7).
  5. Response assembler: attach `citations` array to response.
  6. Audit log write on every `/ask` call.
  7. Streaming response support (`stream=true` query param) via SSE.
- Out of Scope:
  1. Copilot channel adapter (Phase 7).
  2. RFP service (Phase 5) — `/ask` called standalone in this phase; RFP context wiring in Phase 5.
  3. Frontend (Phase 6).
  4. Tool use / function calling (post-MVP).

---

## Interfaces & Dependencies

- Internal: Phase 1 — `get_current_user` dependency, `UserContext`; Phase 3 — `GET /retrieve` internal endpoint; Phase 1 — `audit-service` logger.
- External: `anthropic` SDK (Claude), `google-generativeai` SDK (Gemini), `httpx` (Ollama REST); `sse-starlette` (streaming).
- Artifacts: `services/orchestrator/pipeline.py`, `prompts.py`, `assembler.py`; `services/adapters/base.py`, `claude.py`, `gemini.py`, `ollama.py`; `services/model-router/router.py`, `config.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Anthropic/Google API keys not set in env | Adapters fail at init | Raise clear `ConfigurationError` at startup if key missing; document in `.env.example` |
| Ollama not running locally | Adapter timeout | Configurable `OLLAMA_BASE_URL`; timeout 30s with clear error message |
| Prompt injection via user-supplied question | Security risk | System prompt is always first message; user question is inserted as a quoted literal; never interpolated directly into system prompt |
| Retrieval-service network call adds latency | Slow `/ask` responses | Run retrieval call concurrently with user-context load (asyncio.gather); target < 2s total |
| Fallback adapter also fails | Request error returned | Log both failures; return HTTP 502 with `{"error": "No model available"}` |

---

## Decision Log

- D1: Anthropic `anthropic` SDK for Claude adapter (not raw HTTP) — official SDK handles retries and streaming — Status: Closed — Date: 2026-03-18
- D2: Tenant config stored in Postgres `tenant_config` JSONB column on `users` table (system_admin sets it) for MVP; no separate config service — Status: Closed — Date: 2026-03-18
- D3: SSE (Server-Sent Events) for streaming via `sse-starlette` — works with Next.js `EventSource` without websocket complexity — Status: Closed — Date: 2026-03-18
- D4: Citations built from retrieval results (chunk_id + doc_id + text[:200] as snippet) — no separate citation service — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §5 Orchestrator Flow, §6.1 Ask API, §7 Prompt Templates, §8 Model Adapter Interface
- `services/rbac-service/rbac.py` — `UserContext` (Phase 1)
- `services/retrieval-service/routes.py` — `/retrieve` internal endpoint (Phase 3)
- `services/audit-service/logger.py` — `log_action` (Phase 1)

### Destination Files (new files this phase creates)
- `services/orchestrator/pipeline.py` — POST /ask pipeline
- `services/orchestrator/prompts.py` — Prompt template builder
- `services/orchestrator/assembler.py` — Citation assembly
- `services/adapters/base.py` — ModelAdapter interface
- `services/adapters/claude.py` — Claude adapter
- `services/adapters/gemini.py` — Gemini adapter
- `services/adapters/ollama.py` — Ollama adapter
- `services/model-router/router.py` — Adapter selector
- `services/model-router/config.py` — Tenant config loader

### Related Documentation (context only)
- `spec.md` — §5, §6.1, §7, §8
- `active_plans/rfp_assistant/phases/phase_3_retrieval.md`

---

## Tasks

### [✅] 1 Implement Model Adapter Interface and Adapters
Define the abstract interface and build all three concrete adapters.

  - [✅] 1.1 Define `ModelAdapter` ABC in `services/adapters/base.py`: `generate(prompt: str, context: list[str]) -> GenerateResult` and `async_stream(prompt, context) -> AsyncIterator[str]`; define `GenerateResult(text: str, model: str, tokens_used: int)` and `AdapterError`
  - [✅] 1.2 Implement `ClaudeAdapter` in `claude.py` using `anthropic.AsyncAnthropic`; pass system prompt + context + user question as messages; map `anthropic.APIError` → `AdapterError`
  - [✅] 1.3 Implement `GeminiAdapter` in `gemini.py` using `google.generativeai`; format context as part of the user turn; map SDK exceptions → `AdapterError`
  - [✅] 1.4 Implement `OllamaAdapter` in `ollama.py` using `httpx.AsyncClient` against `OLLAMA_BASE_URL/api/generate`; configurable model name; timeout 30s; map HTTP errors → `AdapterError`

### [✅] 2 Implement Model Router
Build tenant-aware adapter selection with primary + fallback provider.

  - [✅] 2.1 Implement `TenantConfig` Pydantic model: `preferred_provider: Literal["claude","gemini","ollama"]`, `fallback_provider: Literal["claude","gemini","ollama"] | None`, `model_name: str | None`
  - [✅] 2.2 Implement `load_tenant_config(user_id) -> TenantConfig` — reads from `users.tenant_config JSONB`; defaults to `claude` if not set; add `tenant_config JSONB DEFAULT '{}'` column via Alembic migration `0004_tenant_config.py`
  - [✅] 2.3 Implement `select(tenant_config) -> ModelAdapter` — instantiates and returns the adapter for the preferred provider; implement `generate_with_fallback(adapter, fallback, prompt, context)` that catches `AdapterError` and retries with fallback

### [✅] 3 Implement Prompt Templates
Build the mode-aware prompt builder from spec §7.

  - [✅] 3.1 Implement `build_system_prompt() -> str` returning the spec §7.1 system prompt verbatim
  - [✅] 3.2 Implement `build_user_prompt(question, context_chunks, mode) -> str` — for `mode=answer`: combine context + question; for `mode=draft`: prepend spec §7.2 draft instruction; for `mode=review`: prepend spec §7.3 review instruction; for `mode=gap`: prepend spec §7.4 gap instruction
  - [✅] 3.3 Write `tests/test_prompts.py` — assert each mode produces a prompt string containing the mode-specific instruction from spec §7 and the user's question

### [✅] 4 Implement POST /ask Pipeline
Wire all components into the orchestrator endpoint.

  - [✅] 4.1 Implement `assemble_citations(chunks: list[RankedChunk]) -> list[Citation]` — map each chunk to `{chunk_id, doc_id, snippet: chunk.text[:200]}`
  - [✅] 4.2 Implement `ask_pipeline(question, mode, rfp_id, user_ctx) -> AskResponse` — (1) call retrieval-service `/retrieve` with user_ctx, (2) build prompt via `build_user_prompt`, (3) select adapter via router, (4) call `generate_with_fallback`, (5) assemble citations, (6) log audit
  - [✅] 4.3 Implement `POST /ask` FastAPI endpoint: validate request `{question, mode, rfp_id}`; require auth via `get_current_user`; call `ask_pipeline`; return `{answer, citations}`
  - [✅] 4.4 Implement streaming variant: if `stream=true` query param, use `async_stream` and return `StreamingResponse` via SSE with `sse-starlette`
  - [✅] 4.5 Write `tests/test_ask.py` — mock retrieval-service and adapter; assert correct prompt mode used; assert citations in response; assert audit row written

### [✅] 5 Implement Multi-Agent Architecture
Refactor the orchestrator into a pipeline of specialized agents with structured input/output schemas, enabling the Keystone agent definitions from spec_additional §5.

  - [✅] 5.1 Define `AgentInput` and `AgentOutput` Pydantic base models; define concrete schemas for each agent: `RFPIngestionInput/Output`, `RequirementExtractionInput/Output`, `QuestionnaireExtractionInput/Output`, `ResponseGenerationInput/Output`, `QuestionnaireCompletionInput/Output`
  - [✅] 5.2 Implement `AgentPipeline` class: ordered list of `Agent` instances each with `run(input: AgentInput) -> AgentOutput`; pipeline passes output of each agent as input to the next; supports skipping agents based on mode
  - [✅] 5.3 Implement `ResponseGenerationAgent` — wraps existing `ask_pipeline` logic; accepts `{requirements, context_chunks, detail_level}` and returns `{answer, citations, confidence: float}` where confidence is the mean cosine similarity of retrieved chunks
  - [✅] 5.4 Write `tests/test_agent_pipeline.py` — assert pipeline runs agents in order; assert agent output schema validation catches malformed outputs; assert confidence score is in [0.0, 1.0]


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
