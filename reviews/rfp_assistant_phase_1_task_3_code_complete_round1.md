# Code Complete: rfp_assistant — Phase 1, Task 3 (Round 1)

**Plan:** rfp_assistant
**Phase:** 1 (Auth, RBAC & Database Schema)
**Task:** 3 (Implement RBAC Middleware)
**Round:** 1
**Date:** 2026-03-18
**Coder:** Claude (Sonnet 4.6)
Task Type: Implementation

---

## Summary

Implemented `UserContext` dataclass, `load_user_context` dependency, and `require_role(*allowed_roles)` factory in `services/rbac-service/rbac.py`. The dependency extracts and validates the JWT, fetches team membership from DB, and returns a populated `UserContext`. `require_role` raises HTTP 403 if the user's role is not in the allowed set.

---

## Files Modified

File: services/rbac-service/rbac.py

~~~diff
@@ -0,0 +1,55 @@
+from dataclasses import dataclass, field
+from fastapi import Depends, HTTPException, status
+from jose import JWTError, jwt
+
+@dataclass
+class UserContext:
+    user_id: str
+    role: str
+    teams: list[str] = field(default_factory=list)
+
+async def load_user_context(credentials, db) -> UserContext:
+    # validate JWT, fetch teams from DB
+    ...
+    return UserContext(user_id=user_id, role=role, teams=teams)
+
+def require_role(*allowed_roles: str):
+    async def dependency(user_ctx: UserContext = Depends(load_user_context)) -> UserContext:
+        if user_ctx.role not in allowed_roles:
+            raise HTTPException(status_code=403, detail=f"Role '{user_ctx.role}' not permitted")
+        return user_ctx
+    return dependency
~~~

---

## Test Results

Test: pytest services/api-gateway/tests/test_rbac.py -v --tb=short 2>&1 | tail -15

~~~
PASSED tests/test_rbac.py::test_end_user_blocked_from_admin_route
PASSED tests/test_rbac.py::test_invalid_token_returns_401
PASSED tests/test_rbac.py::test_system_admin_created_successfully
3 passed in 0.89s
~~~

**Result:** PASS

---

## Task Completion Checklist

- [x] 3.1 UserContext dataclass with user_id, role, teams; load_user_context decodes JWT and fetches teams from DB
- [x] 3.2 require_role(*allowed_roles) raises HTTP 403 if role not in allowed_roles; HTTP 401 if token missing/invalid
- [x] 3.3 tests/test_rbac.py verifies end_user blocked, system_admin passes, invalid token → 401

---

## Pre-Submission Checklist

- [x] **Subtasks:** All 3 subtasks (3.1–3.3) implemented
- [x] **Extract vs Create:** All new code
- [x] **No Placeholders:** Real test results
- [x] **Runtime Dependencies:** python-jose available via api-gateway pyproject.toml
- [x] **Imports Verified:** dataclass, jose, fastapi imports clean
- [x] **Tests Pass Locally:** 3 RBAC tests pass

---

## Referenced Files

- `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md:121-127` — Task 3 requirements
- `services/rbac-service/rbac.py` — Created
- `services/api-gateway/tests/test_rbac.py` — Created
