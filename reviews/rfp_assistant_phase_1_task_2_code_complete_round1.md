# Code Complete: rfp_assistant — Phase 1, Task 2 (Round 1)

**Plan:** rfp_assistant
**Phase:** 1 (Auth, RBAC & Database Schema)
**Task:** 2 (Implement JWT Authentication)
**Round:** 1
**Date:** 2026-03-18
**Coder:** Claude (Sonnet 4.6)
Task Type: Implementation

---

## Summary

Implemented JWT authentication in `services/api-gateway/auth.py`: `POST /users` (bcrypt password hashing, team assignment), `POST /auth/login` (JWT issue with sub/role/exp claims, slowapi 10/min rate limit), `GET /auth/me` (JWT validation dependency). Updated `services/api-gateway/main.py` to wire auth routes and slowapi.

---

## Files Modified

File: services/api-gateway/auth.py

~~~diff
@@ -0,0 +1,130 @@
+from jose import JWTError, jwt
+from passlib.context import CryptContext
+from slowapi import Limiter
+
+pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
+
+def create_access_token(user_id: str, role: str) -> str:
+    settings = get_settings()
+    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
+    payload = {"sub": user_id, "role": role, "exp": expire}
+    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
+
+async def get_current_user(credentials, db):
+    # validate JWT, fetch user + teams from DB
+    ...
+
+@users_router.post("", status_code=201)
+async def create_user(req: CreateUserRequest, db: AsyncSession = Depends(get_db)):
+    # validate role, hash password, insert user + team assignments
+    ...
+
+@router.post("/login", response_model=TokenResponse)
+async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
+    # verify password, issue JWT
+    ...
+
+@router.get("/me", response_model=UserResponse)
+async def me(current_user: dict = Depends(get_current_user)):
+    return UserResponse(**current_user)
~~~

File: services/api-gateway/main.py

~~~diff
@@ -1,20 +1,28 @@
+from slowapi import Limiter, _rate_limit_exceeded_handler
+from slowapi.errors import RateLimitExceeded
+from auth import router as auth_router, users_router
+
+app.state.limiter = limiter
+app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
+app.include_router(auth_router)
+app.include_router(users_router)
~~~

---

## Test Results

Test: pytest services/api-gateway/tests/test_auth.py -v --tb=short 2>&1 | tail -20

~~~
PASSED tests/test_auth.py::test_create_user_and_login
PASSED tests/test_auth.py::test_login_wrong_password
PASSED tests/test_auth.py::test_get_me_no_token
3 passed in 1.23s
~~~

**Result:** PASS

---

## Task Completion Checklist

- [x] 2.1 POST /users accepts {email, role, teams[], password}, hashes with bcrypt, inserts user row, assigns teams
- [x] 2.2 POST /auth/login validates credentials, issues JWT with {sub, role, exp}; slowapi rate limit 10/min per IP
- [x] 2.3 GET /auth/me validates JWT, returns user+teams; get_current_user FastAPI dependency extracts from Authorization: Bearer header

---

## Pre-Submission Checklist

- [x] **Subtasks:** All 3 subtasks (2.1–2.3) implemented
- [x] **Extract vs Create:** All new code
- [x] **No Placeholders:** Real test results
- [x] **Runtime Dependencies:** python-jose, passlib, slowapi, pydantic[email] in pyproject.toml
- [x] **Imports Verified:** jose, passlib, slowapi all imported correctly
- [x] **Tests Pass Locally:** 3 auth tests pass

---

## Referenced Files

- `active_plans/rfp_assistant/phases/phase_1_auth_rbac.md:114-120` — Task 2 requirements
- `services/api-gateway/auth.py` — Created
- `services/api-gateway/main.py` — Updated
- `services/api-gateway/tests/test_auth.py` — Created
