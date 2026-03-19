# Add Health Check Endpoint

---

## Objective

Add a `/healthz` HTTP endpoint to the API server that returns service status, enabling automated monitoring and load balancer integration. Success is recognized when the endpoint responds with 200 OK and a JSON body containing uptime and dependency statuses.

---

## Current vs Desired

### Current Behavior

- The API server exposes `/api/v1/` routes for business logic only.
- No health check endpoint exists; monitoring relies on TCP port checks.
- Load balancers use basic TCP probes that cannot detect degraded service states.

### Current Structure

- Key files: `src/server.py` (FastAPI app, 320 lines), `src/routes/` (route modules).
- Entry point: `python -m src.server --port 8080`.
- Dependencies: PostgreSQL (`src/db.py`), Redis cache (`src/cache.py`).

### Baseline Snapshot

- `src/server.py` contains the FastAPI app instance and startup/shutdown hooks.
- `src/db.py` exposes `get_pool()` for database connections.
- `src/cache.py` exposes `get_client()` for Redis connections.
- No existing health-related routes or utilities.

### Invariants (MUST Remain True)

- All existing `/api/v1/` routes continue to function without changes.
- Server startup and shutdown hooks remain unchanged.
- No new required environment variables are introduced.

### Desired Behavior

- `GET /healthz` returns `200 OK` with JSON: `{"status": "healthy", "uptime_s": 123.4, "dependencies": {"db": "ok", "cache": "ok"}}`.
- If a dependency is unreachable, its status shows `"error"` and the top-level status becomes `"degraded"`.
- Response time for `/healthz` is under 500ms even when dependencies are slow (timeout per check: 2s).

### Desired Technical Constraints

- Health check must not require authentication.
- Dependency checks run in parallel with a 2-second timeout each.
- CPU overhead of health check must be negligible (<1ms excluding dependency probes).

### Non-Goals

- Readiness vs liveness probe distinction (future work).
- Metrics endpoint (`/metrics` for Prometheus) -- separate plan.
- Health check UI dashboard.

---

## Scope

### In Scope

- Implementing the `/healthz` route with dependency checks.
- Adding a `HealthChecker` utility class for probing dependencies.
- Writing unit and integration tests for the endpoint.

### Out of Scope

- Modifying existing routes or middleware.
- Adding new dependencies or environment variables.

---

## Policies & Contracts

- The `/healthz` endpoint must not require authentication or API keys.
- Dependency probe timeout is 2 seconds; total endpoint timeout is 5 seconds.
- The endpoint must return valid JSON with `Content-Type: application/json`.

---

## Tasks

### [ ] 1 Implement HealthChecker Utility

Short description: Create a utility class that probes database and cache dependencies in parallel and returns structured status results.
Acceptance notes:
- HealthChecker returns status dict within 2s timeout per dependency
- Parallel execution verified (total time < sum of individual timeouts)

**Files:** `src/health.py`

#### [ ] 1.1 Create HealthChecker class with probe methods

Implementation details:
- File: `src/health.py`
- Responsibility: Define `check_db()` and `check_cache()` methods with 2s timeouts.

  - [ ] 1.1.1 Implement `check_db()` using `db.get_pool().fetchval('SELECT 1')`.
  - [ ] 1.1.2 Implement `check_cache()` using `cache.get_client().ping()`.
  - [ ] 1.1.3 Implement `check_all()` running probes in parallel via `asyncio.gather()`.

### [ ] 2 Add /healthz Route

Short description: Register the health check endpoint on the FastAPI app that uses HealthChecker and returns structured JSON.
Acceptance notes:
- GET /healthz returns 200 with correct JSON schema
- Degraded status returned when dependency is down

**Files:** `src/server.py`, `src/health.py`

#### [ ] 2.1 Register route and wire HealthChecker

Implementation details:
- File: `src/server.py`
- Responsibility: Add `@app.get("/healthz")` that calls `HealthChecker.check_all()` and formats the response.

#### [ ] 2.2 Track server uptime

Implementation details:
- File: `src/server.py`
- Responsibility: Record startup timestamp in app state; compute uptime in health endpoint.

### [ ] 3 Write Tests

Short description: Create unit tests for HealthChecker and integration tests for the /healthz endpoint covering healthy and degraded scenarios.
Acceptance notes:
- All tests pass with `pytest tests/test_health.py -v`
- Coverage includes healthy, degraded, and timeout scenarios

**Files:** `tests/test_health.py`

#### [ ] 3.1 Unit test HealthChecker with mocked dependencies

  - [ ] 3.1.1 Test healthy scenario (all probes succeed).
  - [ ] 3.1.2 Test degraded scenario (one probe fails).
  - [ ] 3.1.3 Test timeout scenario (probe exceeds 2s).

#### [ ] 3.2 Integration test /healthz endpoint

  - [ ] 3.2.1 Test 200 response with valid JSON schema.
  - [ ] 3.2.2 Test degraded response when database is unavailable.

---

## Acceptance Criteria

### Global Criteria

- [ ] `GET /healthz` returns 200 with correct JSON schema when all dependencies are healthy.
- [ ] `GET /healthz` returns 200 with `"status": "degraded"` when any dependency is down.
- [ ] Response time is under 500ms in healthy state.
- [ ] All existing `/api/v1/` routes are unaffected.

---

## Risks & Mitigations

- Risk: Dependency probes add latency to health checks.
  Impact: Medium
  Mitigation: 2s timeout per probe with parallel execution (Task 1.1.3).

- Risk: Health endpoint could be used for DoS.
  Impact: Low
  Mitigation: Rate limiting at load balancer level (out of scope for this plan).

---

## Validation

### Automated Validation

- `pytest tests/test_health.py -v` -- all tests pass.
- `curl http://localhost:8080/healthz` -- returns valid JSON with 200 status.

### Manual Test Checklist

1. **Healthy State**
   - [ ] Start server with all dependencies running.
   - [ ] `curl /healthz` returns `{"status": "healthy", ...}`.

2. **Degraded State**
   - [ ] Stop Redis.
   - [ ] `curl /healthz` returns `{"status": "degraded", "dependencies": {"cache": "error", ...}}`.

---

## Artifacts Created

- `src/health.py` -- HealthChecker utility class.
- `tests/test_health.py` -- Unit and integration tests.

---

## Interfaces & Dependencies

### Internal Dependencies

- `src/db.py` -- Database connection pool used by health probes.
- `src/cache.py` -- Redis client used by health probes.
- `src/server.py` -- FastAPI app where route is registered.

### External Dependencies

- PostgreSQL -- Probed via `SELECT 1` query.
- Redis -- Probed via `PING` command.

---

## References

### Source Files (Existing Code/Docs Being Modified)

- `src/server.py` -- FastAPI app; health route will be added here.
- `src/db.py` -- Database pool accessor used by health probes.
- `src/cache.py` -- Redis client accessor used by health probes.

### Destination Files (New Files This Plan Creates)

- `src/health.py` -- HealthChecker utility class.
- `tests/test_health.py` -- Health endpoint tests.

### Related Documentation (Context Only)

- `docs/API.md` -- API documentation reference.

---

## Reviewer Checklist

### Structure & Numbering

- [ ] Top-level tasks use only: `1`, `2`, `3`.
- [ ] Subtasks use only: `1.1`, `2.1`, `2.2`, `3.1`, `3.2`.
- [ ] Leaf steps use only: `1.1.1`-`1.1.3`, `3.1.1`-`3.1.3`, `3.2.1`-`3.2.2`.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.

### Traceability

- [ ] Every Task maps to Scope (In) items.
- [ ] Acceptance Criteria map to top-level tasks.

### Content Discipline

- [ ] Objective states outcome, not implementation.
- [ ] Current vs Desired separates analysis from execution.
