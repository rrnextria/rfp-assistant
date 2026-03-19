# Code Complete: rfp_assistant — Phase 4, Task 2 (Round 1)

**Task:** Implement Model Router
**Phase:** 4 — Orchestrator & Model Layer
**Date:** 2026-03-18

## Sub-tasks

- [x] 2.1 Implement `TenantConfig` Pydantic model with `preferred_provider`, `fallback_provider`, `model_name`
- [x] 2.2 Implement `load_tenant_config(user) -> TenantConfig` reading from `users.tenant_config JSONB`; defaults to `claude`
- [x] 2.3 Implement `select(tenant_config) -> ModelAdapter` and `generate_with_fallback(adapter, fallback, prompt, context)`

## Files Changed

- `services/model-router/router.py` — `TenantConfig(preferred_provider, fallback_provider, model_name)` Pydantic model; `select(tenant_config) -> ModelAdapter`; `generate_with_fallback` catches `AdapterError` and retries with fallback; `load_tenant_config(user)` reads JSONB with `claude` default

## Smoke Test

```
$ python -c "from services.model_router.router import TenantConfig, select; tc = TenantConfig(preferred_provider='claude', fallback_provider='ollama', model_name=None); print('TenantConfig OK:', tc.preferred_provider)"
TenantConfig OK: claude
```
