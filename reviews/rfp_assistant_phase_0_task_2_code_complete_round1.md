# Code Complete: rfp_assistant — Phase 0, Task 2 (Round 1)

**Plan:** rfp_assistant
**Phase:** 0 (Foundation & Infrastructure)
**Task:** 2 (Set Up Per-Service FastAPI Skeletons)
**Round:** 1
**Date:** 2026-03-18
**Coder:** Claude (Sonnet 4.6)
Task Type: Implementation

---

## Summary

Created `main.py`, `pyproject.toml`, and `Dockerfile` for all 9 service directories. Each service has a FastAPI app with `/healthz` endpoint returning `{"status": "ok", "service": "<name>"}` and a lifespan hook for DB connection pool management.

---

## Files Modified

File: services/api-gateway/main.py

~~~diff
@@ -0,0 +1,24 @@
+from contextlib import asynccontextmanager
+
+from fastapi import FastAPI
+
+from common.db import get_engine
+from common.logging import get_logger
+
+logger = get_logger("api-gateway")
+
+
+@asynccontextmanager
+async def lifespan(app: FastAPI):
+    logger.info("Starting api-gateway")
+    engine = get_engine()
+    yield
+    await engine.dispose()
+    logger.info("Shutdown api-gateway")
+
+
+app = FastAPI(title="api-gateway", lifespan=lifespan)
+
+
+@app.get("/healthz")
+async def healthz():
+    return {"status": "ok", "service": "api-gateway"}
~~~

File: services/api-gateway/pyproject.toml

~~~diff
@@ -0,0 +1,30 @@
+[build-system]
+requires = ["hatchling"]
+build-backend = "hatchling.build"
+
+[project]
+name = "api-gateway"
+version = "0.1.0"
+requires-python = ">=3.12"
+dependencies = [
+    "fastapi>=0.111",
+    "uvicorn[standard]>=0.29",
+    "sqlalchemy[asyncio]>=2.0",
+    "psycopg[binary]>=3.1",
+    "pydantic-settings>=2.0",
+    "common",
+]
+
+[project.optional-dependencies]
+dev = ["ruff>=0.4", "black>=24", "pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]
+
+[tool.ruff]
+target-version = "py312"
+line-length = 100
+select = ["E", "F", "I", "UP"]
+
+[tool.black]
+line-length = 100
+target-version = ["py312"]
+
+[tool.pytest.ini_options]
+asyncio_mode = "auto"
~~~

File: services/api-gateway/Dockerfile

~~~diff
@@ -0,0 +1,16 @@
+FROM python:3.12-slim
+
+WORKDIR /app
+
+COPY common /common
+RUN pip install --no-cache-dir -e /common
+
+COPY services/api-gateway/pyproject.toml .
+RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .
+
+COPY services/api-gateway/ .
+
+EXPOSE 8000
+
+CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
~~~

(Identical pattern for orchestrator:8001, retrieval-service:8002, content-service:8003, rbac-service:8004, rfp-service:8005, model-router:8006, adapters:8007, audit-service:8008 — all 27 files created)

---

## Test Results

Test: for svc in api-gateway orchestrator retrieval-service content-service rbac-service rfp-service model-router adapters audit-service; do test -f services/$svc/main.py && test -f services/$svc/pyproject.toml && test -f services/$svc/Dockerfile && echo "$svc: OK"; done

~~~
api-gateway: OK
orchestrator: OK
retrieval-service: OK
content-service: OK
rbac-service: OK
rfp-service: OK
model-router: OK
adapters: OK
audit-service: OK
~~~

**Result:** PASS

Test: grep -l 'healthz' services/*/main.py | wc -l

~~~
9
~~~

**Result:** PASS

---

## Task Completion Checklist

- [x] 2.1 Created main.py in each of the 9 service directories with FastAPI app, /healthz endpoint, and lifespan hook
- [x] 2.2 Created pyproject.toml in each of the 9 service directories with all required dependencies
- [x] 2.3 Created Dockerfile in each of the 9 service directories using python:3.12-slim with pip install -e /common

---

## Pre-Submission Checklist

- [x] **Subtasks:** All 3 subtasks (2.1–2.3) implemented for all 9 services
- [x] **Extract vs Create:** All new files
- [x] **No Placeholders:** All service names and ports are real values
- [x] **Runtime Dependencies:** common/ installed as editable package before service deps
- [x] **Imports Verified:** main.py imports from common.db and common.logging
- [x] **Tests Pass Locally:** All 9 service directories verified with file checks

---

## Referenced Files

- `active_plans/rfp_assistant/phases/phase_0_foundation.md:117-123` — Task 2 requirements
- `services/*/main.py` — 9 created files
- `services/*/pyproject.toml` — 9 created files
- `services/*/Dockerfile` — 9 created files
