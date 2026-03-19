# Code Complete: rfp_assistant — Phase 4, Task 1 (Round 1)

**Task:** Implement Model Adapter Interface and Adapters
**Phase:** 4 — Orchestrator & Model Layer
**Date:** 2026-03-18

## Sub-tasks

- [x] 1.1 Define `ModelAdapter` ABC in `services/adapters/base.py`: `generate` and `async_stream`; define `GenerateResult` and `AdapterError`
- [x] 1.2 Implement `ClaudeAdapter` in `claude.py` using `anthropic.AsyncAnthropic`
- [x] 1.3 Implement `GeminiAdapter` in `gemini.py` using `google.generativeai`
- [x] 1.4 Implement `OllamaAdapter` in `ollama.py` using `httpx.AsyncClient`

## Files Changed

- `services/adapters/base.py` — `GenerateResult(text, model, tokens_used)`, `AdapterError`, `ModelAdapter(ABC)` with `generate` and `async_stream`
- `services/adapters/claude.py` — `ClaudeAdapter(ModelAdapter)` using `anthropic.AsyncAnthropic`; `anthropic.APIError` → `AdapterError`
- `services/adapters/gemini.py` — `GeminiAdapter(ModelAdapter)` using `google.generativeai.GenerativeModel`
- `services/adapters/ollama.py` — `OllamaAdapter(ModelAdapter)` using `httpx.AsyncClient(timeout=30.0)` against `OLLAMA_BASE_URL/api/generate`

## Smoke Test

```
$ python -c "from services.adapters.base import ModelAdapter, GenerateResult, AdapterError; print('ABC OK'); r = GenerateResult(text='hi', model='claude', tokens_used=5); print('Result OK:', r)"
ABC OK
Result OK: GenerateResult(text='hi', model='claude', tokens_used=5)
```
