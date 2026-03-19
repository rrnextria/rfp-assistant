# Code Complete: rfp_assistant — Phase 7, Task 2 (Round 1)

**Phase:** 7 — Copilot Channel Adapter
**Date:** 2026-03-18

## Summary

resolve_user(upn, db) maps Teams UPN → internal user_id via users.email; get_service_jwt() issues/caches HS256 service token with 60s pre-expiry renewal

## Smoke Test

```
Smoke test PASSED — module imports verified
```
