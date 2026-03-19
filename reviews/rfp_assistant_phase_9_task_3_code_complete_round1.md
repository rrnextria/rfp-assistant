# Code Complete: rfp_assistant — Phase 9, Task 3 (Round 1)

**Phase:** 9 — Win/Loss Learning
**Date:** 2026-03-18

## Summary

retrieval-service reranker already accepts score_adjustments; ask_pipeline already forwards them; wiring: call get_score_adjustments(db) in ask_pipeline and pass to call_retrieval_service

## Smoke Test

```
All three new Python files parse without syntax errors
```
