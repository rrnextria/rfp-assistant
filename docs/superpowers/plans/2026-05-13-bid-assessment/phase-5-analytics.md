# Phase 5 — Analytics Gated Learning Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this phase task-by-task.

**Goal:** Make the `analytics-service` aggregate per-tenant outcome patterns from `past_proposals` and emit learned `win_probability` boosts to `SummaryAgent`, gated by a minimum-N threshold (default 20). Surface the gate's state in the branding admin page as a read-only "Learning status" card so the cold-start reality is honest.

**Architecture:** Aggregation runs on demand at `GET /score-boosts?tenant_id=…` (no scheduler in v1). The endpoint computes patterns from `past_proposals` joined to optional industry/value buckets. `BidAssessmentPipeline` (phase 3) fetches the relevant boost during the Summary step. The branding admin page calls `GET /score-boosts?tenant_id=…` and renders pattern → `(n_total, win_rate, boost, active|gated)`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x async. No new dependencies. Re-uses the existing `analytics-service`.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `services/analytics-service/main.py` | Add `/score-boosts` endpoint |
| Create | `services/analytics-service/patterns.py` | Per-tenant aggregation logic |
| Create | `services/analytics-service/tests/test_patterns.py` | Aggregation correctness + min-N gating |
| Modify | `services/orchestrator/main.py` | Fetch boost during `/assess/run` and pass to pipeline |
| Modify | `services/orchestrator/assessment/pipeline.py` | Accept `analytics_boost` argument from caller, already wired in phase 3 — confirm it actually pulls from analytics-service |
| Modify | `services/api-gateway/proxy.py` | Add `score-boosts` route key |
| Modify | `frontend/app/(admin)/admin/branding/page.tsx` | Append "Learning status" card |
| Modify | `frontend/lib/api.ts` | Add `getScoreBoosts()` |
| Modify | `scripts/seed_demo.py` | Add 10+ won proposals so we can demonstrate the min-N gate moving (optional but instructive) |

---

## Tasks

### Task 1 — Branch

- [ ] **Step 1**

```bash
git checkout feat/bid-assessment
git checkout -b feat/bid-assessment-phase-5-analytics
```

---

### Task 2 — Aggregation logic (TDD)

**Files:**
- Create: `services/analytics-service/patterns.py`
- Create: `services/analytics-service/tests/test_patterns.py`

- [ ] **Step 1: Failing test**

```python
import pytest

from patterns import compute_patterns, gate_patterns


def _row(industry_id, outcome, value_amount=None):
    return {"industry_id": industry_id, "outcome": outcome,
             "value_amount": value_amount}


def test_compute_patterns_groups_by_industry_only_when_present():
    rows = [
        _row("banking", "won"), _row("banking", "won"), _row("banking", "lost"),
        _row("healthcare", "won"),
    ]
    patterns = compute_patterns(rows)
    bank = next(p for p in patterns if p["industry_id"] == "banking")
    assert bank["n_total"] == 3
    assert bank["n_won"] == 2
    assert abs(bank["win_rate"] - (2 / 3)) < 1e-9
    hc = next(p for p in patterns if p["industry_id"] == "healthcare")
    assert hc["n_total"] == 1


def test_gate_patterns_zero_boost_below_threshold():
    raw = [{"industry_id": "x", "n_total": 5, "n_won": 4, "win_rate": 0.8}]
    gated = gate_patterns(raw, min_n=20, max_boost=0.10)
    assert gated[0]["boost"] == 0.0
    assert gated[0]["active"] is False


def test_gate_patterns_scales_above_threshold():
    raw = [{"industry_id": "x", "n_total": 40, "n_won": 28, "win_rate": 0.7}]
    gated = gate_patterns(raw, min_n=20, max_boost=0.10)
    # 0.7 maps to +0.04 boost (centred at 0.5; +max_boost at 1.0)
    assert gated[0]["active"] is True
    assert 0.0 < gated[0]["boost"] <= 0.10
```

- [ ] **Step 2: Run test (should fail)**

```bash
cd services/analytics-service && python -m pytest tests/test_patterns.py -v && cd -
```

Expected: FAIL — ImportError.

- [ ] **Step 3: Implement**

```python
"""Past-proposal outcome aggregation + min-N gating."""
from __future__ import annotations

from collections import defaultdict


def compute_patterns(rows: list[dict]) -> list[dict]:
    """Group rows by industry_id (None as a separate bucket). Compute per-bucket
    n_total, n_won, win_rate. value_amount buckets are deferred to phase-2."""
    grouped: dict[str | None, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r.get("industry_id")].append(r)
    out: list[dict] = []
    for industry_id, group in grouped.items():
        n_total = len(group)
        n_won = sum(1 for g in group if g["outcome"] == "won")
        win_rate = (n_won / n_total) if n_total else 0.0
        out.append({"industry_id": industry_id, "n_total": n_total,
                     "n_won": n_won, "win_rate": round(win_rate, 4)})
    return out


def gate_patterns(patterns: list[dict], *, min_n: int = 20,
                   max_boost: float = 0.10) -> list[dict]:
    """Apply min-N gating. Below threshold → boost=0, active=False.
    Above threshold → boost = max_boost * (win_rate - 0.5) * 2, clamped to
    [-max_boost, +max_boost]."""
    out: list[dict] = []
    for p in patterns:
        if p["n_total"] < min_n:
            out.append({**p, "boost": 0.0, "active": False})
            continue
        raw = max_boost * (p["win_rate"] - 0.5) * 2.0
        clipped = max(-max_boost, min(max_boost, round(raw, 4)))
        out.append({**p, "boost": clipped, "active": True})
    return out
```

- [ ] **Step 4: Run test (should pass)**

```bash
cd services/analytics-service && python -m pytest tests/test_patterns.py -v && cd -
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/analytics-service/patterns.py \
         services/analytics-service/tests/test_patterns.py
git commit -m "feat(analytics): pattern aggregation + min-N gating"
```

---

### Task 3 — `/score-boosts` endpoint

**Files:**
- Modify: `services/analytics-service/main.py`

- [ ] **Step 1: Append endpoint**

Add to `services/analytics-service/main.py`:

```python
from patterns import compute_patterns, gate_patterns


@app.get("/score-boosts")
async def score_boosts(tenant_id: str, db: AsyncSession = Depends(get_db),
                         min_n: int = 20, max_boost: float = 0.10) -> dict:
    rows = await db.execute(
        text("SELECT industry_id::text AS industry_id, outcome, value_amount "
             "FROM past_proposals WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    raw = [dict(r) for r in rows.mappings().all()]
    patterns = compute_patterns(raw)
    gated = gate_patterns(patterns, min_n=min_n, max_boost=max_boost)
    return {
        "tenant_id": tenant_id,
        "min_n": min_n,
        "max_boost": max_boost,
        "patterns": gated,
        "n_total_proposals": len(raw),
    }
```

- [ ] **Step 2: Smoke test**

```bash
docker compose restart analytics-service
sleep 3
TENANT_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT id FROM tenants WHERE slug='akkodis';")
curl -sf "http://localhost:8009/score-boosts?tenant_id=$TENANT_ID" | jq .
```

Expected: a JSON body with `patterns: []` (until past_proposals are seeded) or with one entry per industry seen so far. The `active` field is `false` for every entry while N < 20.

- [ ] **Step 3: Commit**

```bash
git add services/analytics-service/main.py
git commit -m "feat(analytics): GET /score-boosts endpoint (per-tenant)"
```

---

### Task 4 — Gateway route

**Files:**
- Modify: `services/api-gateway/proxy.py`

- [ ] **Step 1: Add route key**

In `_SERVICE_MAP`, add:

```python
    "score-boosts": os.environ.get("ANALYTICS_SERVICE_URL", "http://analytics-service:8009"),
```

- [ ] **Step 2: Smoke test through gateway**

```bash
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)
curl -sf -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8011/score-boosts?tenant_id=$TENANT_ID" | jq '.patterns[0]'
```

Expected: an object with `industry_id`, `n_total`, `boost`, `active`.

- [ ] **Step 3: Commit**

```bash
git add services/api-gateway/proxy.py
git commit -m "feat(gateway): route /score-boosts to analytics-service"
```

---

### Task 5 — Pipeline integration

**Files:**
- Modify: `services/orchestrator/main.py`
- Modify: `services/orchestrator/assessment/pipeline.py` (uses `analytics_boost` already)

- [ ] **Step 1: Fetch boost before pipeline run**

In `services/orchestrator/main.py`, inside `assess_run`, before constructing `BidAssessmentPipeline`, add:

```python
import httpx
async def _fetch_boost(tenant_id: str) -> float:
    """Find the boost for the RFP's industry (if any); else 0."""
    analytics_url = getattr(s, "analytics_service_url",
                               "http://analytics-service:8009")
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{analytics_url}/score-boosts",
                              params={"tenant_id": tenant_id})
            r.raise_for_status()
            data = r.json()
    except Exception:
        return 0.0
    # Find the RFP's industry. For now, use the highest active boost as a
    # tenant-wide signal (the per-RFP industry match is a phase-2 refinement).
    boosts = [p["boost"] for p in data.get("patterns", []) if p.get("active")]
    return max(boosts) if boosts else 0.0

boost = await _fetch_boost(ctx["tenant_id"])
```

Then pass `analytics_boost=boost` into the `BidAssessmentPipeline(...)` constructor (replacing the hardcoded `0.0`).

- [ ] **Step 2: Re-run assessment and inspect**

```bash
docker compose restart orchestrator
sleep 5
TENANT_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT id FROM tenants WHERE slug='akkodis';")
RFP_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT r.id FROM rfps r WHERE r.tenant_id = '$TENANT_ID' LIMIT 1;")
curl -sf -X POST http://localhost:8001/assess/run \
     -H "X-Tenant-Id: $TENANT_ID" -H "X-User-Id: 00000000-0000-0000-0000-000000000000" \
     -H 'Content-Type: application/json' \
     -d "{\"rfp_id\":\"$RFP_ID\"}" | jq '.win_probability'
```

Expected: a float. (Same as before until past_proposals cross N=20.)

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator/main.py
git commit -m "feat(orchestrator): fetch analytics boost and pass to assessment pipeline"
```

---

### Task 6 — Frontend learning-status card

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/(admin)/admin/branding/page.tsx`

- [ ] **Step 1: Add API helper**

In `frontend/lib/api.ts`:

```ts
export async function getScoreBoosts() {
  const r = await fetch(`${API_BASE}/score-boosts`, { credentials: "include" });
  // tenant_id is required as a query param; the gateway should infer from JWT.
  // If the backend rejects without explicit tenant_id, we'll surface it via getTenant first:
  if (!r.ok) {
    const t = await (await fetch(`${API_BASE}/tenants/me`, { credentials: "include" })).json();
    const r2 = await fetch(`${API_BASE}/score-boosts?tenant_id=${t.id}`, { credentials: "include" });
    if (!r2.ok) throw new Error(`score-boosts failed`);
    return r2.json();
  }
  return r.json();
}
```

(A cleaner path is to make analytics-service accept JWT-derived tenant; current backend reads `?tenant_id`. Keep both.)

- [ ] **Step 2: Append card to branding page**

In `frontend/app/(admin)/admin/branding/page.tsx`, after the existing brand form, add:

```tsx
import { getScoreBoosts } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";

// inside the component body:
const { data: boosts } = useQuery({ queryKey: ["score-boosts"], queryFn: getScoreBoosts });

// JSX:
<section className="mt-8 p-4 border rounded">
  <h2 className="font-semibold mb-2">Learning status</h2>
  <p className="text-xs text-gray-600 mb-2">
    Patterns aggregated from past proposals. Boosts only apply once a pattern has
    {` `}<code>n_total ≥ {boosts?.min_n ?? 20}</code>. Below the threshold the system
    is honest: no learned signal yet.
  </p>
  <table className="w-full text-sm">
    <thead><tr className="text-left">
      <th>Industry</th><th>N</th><th>Won</th><th>Win rate</th><th>Boost</th><th>Status</th>
    </tr></thead>
    <tbody>
      {(boosts?.patterns ?? []).map((p: any, i: number) => (
        <tr key={i} className="border-t">
          <td>{p.industry_id ?? "(none)"}</td>
          <td>{p.n_total}</td>
          <td>{p.n_won ?? "—"}</td>
          <td>{((p.win_rate ?? 0) * 100).toFixed(0)}%</td>
          <td>{p.boost >= 0 ? "+" : ""}{(p.boost * 100).toFixed(1)}%</td>
          <td className={p.active ? "text-emerald-600" : "text-gray-500"}>
            {p.active ? "active" : "gated"}
          </td>
        </tr>
      ))}
    </tbody>
  </table>
</section>
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 8
# Visit /admin/branding as system_admin; confirm the Learning status card renders.
kill $DEV_PID
```

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/\(admin\)/admin/branding/
git commit -m "feat(frontend-admin): Learning status card on branding page"
```

---

### Task 7 — (Optional) seed N=20 past proposals to demonstrate gate flip

**Files:**
- Modify: `scripts/seed_demo.py`

- [ ] **Step 1: Add a helper to seed N proposals**

Append to `seed_past_proposals` (from phase 2). Loop over a list of 25 synthetic proposals across the seeded industries with mixed outcomes, e.g.:

```python
import random
random.seed(42)

NAMES = ["Alpha Bank","Beta Health","Gamma Gov","Delta Care","Epsilon Holdings", ...]  # 25
for name in NAMES:
    industry = random.choice(industry_ids)
    outcome = random.choices(["won","lost"], weights=[0.65, 0.35])[0]
    # ... INSERT document + past_proposals row with this outcome
```

This raises N above 20 per industry so the gate flips to active during the next assessment.

- [ ] **Step 2: Run seed**

```bash
docker compose exec api-gateway python /scripts/seed_demo.py
TENANT_ID=$(docker compose exec -T postgres psql -U postgres -At -c \
  "SELECT id FROM tenants WHERE slug='akkodis';")
curl -sf "http://localhost:8009/score-boosts?tenant_id=$TENANT_ID" | jq '.patterns'
```

Expected: at least one pattern with `active: true`.

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_demo.py
git commit -m "feat(seed): synthetic past proposals to demonstrate gate activation"
```

---

### Task 8 — End-to-end demo and merge

- [ ] **Step 1: Full sweep**

```bash
for svc in analytics-service orchestrator rfp-service content-service \
           retrieval-service capability-service api-gateway; do
  echo "--- $svc ---"
  (cd services/$svc && python -m pytest -q)
done
cd frontend && npm test -- --run && npm run typecheck && npm run build && cd -
```

Expected: green.

- [ ] **Step 2: Migration reversibility (whole chain)**

```bash
docker compose exec api-gateway alembic upgrade head
docker compose exec api-gateway alembic downgrade base
docker compose exec api-gateway alembic upgrade head
```

Expected: zero errors.

- [ ] **Step 3: Final demo affordance**

1. Login as Akkodis admin.
2. Visit `/admin/branding` → Learning status card visible with at least one active pattern (if Task 7 was run).
3. Open any RFP → Re-run assessment → verdict + fit + win-probability shown; win-probability differs from fit because the active analytics boost applied.
4. Edit a risk; confirm it persists across reload.

- [ ] **Step 4: Merge phase 5 into long-lived branch**

```bash
git checkout feat/bid-assessment
git merge --no-ff feat/bid-assessment-phase-5-analytics \
  -m "Phase 5: analytics gated learning loop + admin visibility"
git push origin feat/bid-assessment
```

- [ ] **Step 5: Open PR for the long-lived branch**

```bash
gh pr create \
  --base master --head feat/bid-assessment \
  --title "Bid Assessment pivot (all 5 phases)" \
  --body "$(cat docs/superpowers/specs/2026-05-13-bid-assessment-design.md | head -50)"
```

Expected: PR URL.

Phase 5 done. Project complete.
