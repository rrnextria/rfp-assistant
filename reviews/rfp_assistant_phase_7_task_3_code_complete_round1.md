# Code Complete: rfp_assistant — Phase 7, Task 3 (Round 1)

**Phase:** 7 — Copilot Channel Adapter
**Date:** 2026-03-18

## Summary

TeamsBot(ActivityHandler).on_message_activity strips <at> mention tags, calls POST /ask via httpx with 30s timeout, sends Adaptive Card reply via build_adaptive_card(answer, citations, mode)

## Smoke Test

```
Smoke test PASSED — module imports verified
```
