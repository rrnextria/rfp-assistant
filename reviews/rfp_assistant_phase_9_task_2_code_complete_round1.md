# Code Complete: rfp_assistant — Phase 9, Task 2 (Round 1)

**Phase:** 9 — Win/Loss Learning
**Date:** 2026-03-18

## Summary

WinLossLearningAgent.learn(db, rfp_id, outcome) boosts recommended products +0.10 for wins / -0.05 for losses; stores in score_boosts JSONB; get_score_adjustments(db) sums boosts over last 90 days

## Smoke Test

```
All three new Python files parse without syntax errors
```
