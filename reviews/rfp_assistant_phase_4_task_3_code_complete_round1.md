# Code Complete: rfp_assistant — Phase 4, Task 3 (Round 1)

**Task:** Implement Prompt Templates
**Phase:** 4 — Orchestrator & Model Layer
**Date:** 2026-03-18

## Sub-tasks

- [x] 3.1 Implement `build_system_prompt() -> str` with spec §7.1 system prompt
- [x] 3.2 Implement `build_user_prompt(question, context_chunks, mode, detail_level)` for all four modes
- [x] 3.3 Write `tests/test_prompts.py` — assert each mode produces mode-specific instruction and includes the user question

## Files Changed

- `services/orchestrator/prompts.py` — `SYSTEM_PROMPT`; `build_system_prompt()`; `build_user_prompt(question, context_chunks, mode, detail_level)` with answer/draft/review/gap branches and minimal/balanced/detailed detail instructions
- `services/orchestrator/tests/test_prompts.py` — 4 mode tests + 3 detail_level tests

## Smoke Test

```
$ python -m pytest services/orchestrator/tests/test_prompts.py -q
7 passed in 0.21s
```
