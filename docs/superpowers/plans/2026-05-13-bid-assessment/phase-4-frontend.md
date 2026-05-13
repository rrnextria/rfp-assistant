# Phase 4 — Frontend (Single-Page Workspace + Admin Pages + Branding)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this phase task-by-task.

**Goal:** Restructure the RFP workspace into a single-page layout (RFP header → scorecard → draft section); add admin pages for capabilities, snippets, past-proposals, contracts, branding; introduce a `BrandThemeProvider` that pulls tenant brand colours from `/tenants/me`; ship the `useAssessmentStream` SSE hook.

**Architecture:** Component-tree restructuring with extraction of the existing answer-draft UI into `DraftSection.tsx`. New shared `lib/useAssessmentStream.ts` hook owns the SSE connection. `BrandThemeProvider` wraps `ThemeProvider` and sets CSS vars from tenant brand JSONB. No new Next.js route segments — `/rfps/[id]` keeps the same path but rerenders as the single-page layout.

**Tech Stack:** Next.js 14 (App Router), React 18, Tailwind, TanStack Query already in repo, native EventSource for SSE.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `services/api-gateway/auth.py` | Add `/tenants/me` and `PATCH /tenants/me/brand` |
| Create | `frontend/lib/useAssessmentStream.ts` | SSE hook |
| Modify | `frontend/lib/api.ts` | Add `getTenant`, `runAssessment`, `getAssessmentLatest`, snippets, past-proposals, contracts, capabilities |
| Create | `frontend/components/branding/BrandThemeProvider.tsx` | Tenant brand fetcher + CSS-var setter |
| Modify | `frontend/app/layout.tsx` | Wrap with `BrandThemeProvider` |
| Rewrite | `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` | Single-page layout: header + scorecard + draft |
| Create | `frontend/components/rfp/RFPHeader.tsx` | RFP title/client/due-date/status |
| Create | `frontend/components/rfp/AssessmentScorecard.tsx` | Composite container for the 5 panels + progress strip |
| Create | `frontend/components/rfp/ScoreRollupHeader.tsx` | verdict + fit + win prob + re-run button |
| Create | `frontend/components/rfp/CompliancePanel.tsx` | List with snippet/citation chips |
| Create | `frontend/components/rfp/EligibilityPanel.tsx` | Bid-killer summary |
| Create | `frontend/components/rfp/BestFitMatrix.tsx` | Heat-map requirement × offering |
| Create | `frontend/components/rfp/RiskRegister.tsx` | Editable risks |
| Create | `frontend/components/rfp/ExecSummaryCard.tsx` | Markdown summary + Re-run prose |
| Create | `frontend/components/rfp/AssessmentHistoryMenu.tsx` | Version dropdown |
| Create | `frontend/components/rfp/DraftSection.tsx` | Extracted from current RFPWorkspace |
| Create | `frontend/app/(admin)/admin/capabilities/page.tsx` | 5-dimension admin |
| Create | `frontend/app/(admin)/admin/snippets/page.tsx` | Snippets CRUD |
| Create | `frontend/app/(admin)/admin/past-proposals/page.tsx` | Past-proposals CRUD + outcome |
| Create | `frontend/app/(admin)/admin/contracts/page.tsx` | Contracts CRUD |
| Create | `frontend/app/(admin)/admin/branding/page.tsx` | Brand colour + logo upload |
| Modify | `frontend/components/AppShell.tsx` | Use tenant `display_name` and logo from `/tenants/me`; demote `/ask` link |

---

## Tasks

### Task 1 — Branch

- [ ] **Step 1**

```bash
git checkout feat/bid-assessment
git checkout -b feat/bid-assessment-phase-4-frontend
cd frontend && npm install && cd -
```

---

### Task 2 — Gateway: `/tenants/me` + PATCH brand

**Files:**
- Modify: `services/api-gateway/auth.py`

- [ ] **Step 1: Add tenants router**

Append to `services/api-gateway/auth.py`:

```python
tenants_router = APIRouter(prefix="/tenants", tags=["tenants"])


@tenants_router.get("/me")
async def my_tenant(current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("SELECT id::text AS id, slug, display_name, brand, config "
             "FROM tenants WHERE id = :id"),
        {"id": current_user["tenant_id"]},
    )
    t = row.mappings().first()
    if not t:
        raise HTTPException(404, "Tenant not found")
    return dict(t)


class BrandPatch(BaseModel):
    logo_url: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    report_header: str | None = None
    report_footer: str | None = None


@tenants_router.patch("/me/brand")
async def patch_brand(req: BrandPatch,
                       current_user: dict = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user["role"] != "system_admin":
        raise HTTPException(403, "Forbidden")
    row = await db.execute(
        text("SELECT brand FROM tenants WHERE id = :id"),
        {"id": current_user["tenant_id"]},
    )
    current = dict((row.mappings().first() or {}).get("brand") or {})
    for k, v in req.model_dump(exclude_none=True).items():
        current[k] = v
    await db.execute(
        text("UPDATE tenants SET brand = :b::jsonb WHERE id = :id"),
        {"b": json.dumps(current), "id": current_user["tenant_id"]},
    )
    await db.commit()
    return {"brand": current}
```

Add `import json` at top of file if not present.

Wire it into `main.py`:

```python
from auth import tenants_router
app.include_router(tenants_router)
```

- [ ] **Step 2: Smoke test**

```bash
docker compose restart api-gateway
sleep 3
TOKEN=$(curl -s -X POST http://localhost:8011/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@akkodis.com","password":"changeme"}' | jq -r .access_token)
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8011/tenants/me | jq .
```

Expected: tenant JSON with `display_name=Akkodis` and a (possibly empty) `brand` object.

- [ ] **Step 3: Commit**

```bash
git add services/api-gateway/auth.py services/api-gateway/main.py
git commit -m "feat(gateway): /tenants/me and PATCH /tenants/me/brand"
```

---

### Task 3 — Frontend API client additions

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add API functions**

Append to `frontend/lib/api.ts`:

```ts
// --- tenant ---
export async function getTenant() {
  const r = await fetch(`${API_BASE}/tenants/me`, { credentials: "include" });
  if (!r.ok) throw new Error(`tenant fetch failed (${r.status})`);
  return r.json();
}

export async function patchBrand(brand: Record<string, string>) {
  const r = await fetch(`${API_BASE}/tenants/me/brand`, {
    method: "PATCH", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brand),
  });
  if (!r.ok) throw new Error(`brand patch failed`);
  return r.json();
}

// --- assessments ---
export async function runAssessment(rfpId: string) {
  const r = await fetch(`${API_BASE}/rfps/${rfpId}/assess`, {
    method: "POST", credentials: "include",
  });
  if (!r.ok) throw new Error(`assess failed (${r.status})`);
  return r.json();
}

export async function getAssessmentLatest(rfpId: string) {
  const r = await fetch(`${API_BASE}/rfps/${rfpId}/assessments/latest`, {
    credentials: "include",
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`assessment fetch failed (${r.status})`);
  return r.json();
}

export async function listAssessments(rfpId: string) {
  const r = await fetch(`${API_BASE}/rfps/${rfpId}/assessments`, { credentials: "include" });
  if (!r.ok) throw new Error(`list failed`);
  return r.json();
}

// --- capabilities ---
export async function getCapabilityProfile() {
  const r = await fetch(`${API_BASE}/capabilities/profile`, { credentials: "include" });
  if (!r.ok) throw new Error(`profile failed`);
  return r.json();
}

export async function createIndustry(name: string) {
  const r = await fetch(`${API_BASE}/capabilities/industries`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(`create industry failed`);
  return r.json();
}

export async function deleteIndustry(id: string) {
  const r = await fetch(`${API_BASE}/capabilities/industries/${id}`, {
    method: "DELETE", credentials: "include",
  });
  if (r.status !== 204) throw new Error(`delete failed`);
}

// (Mirror create/list/delete patterns for: geographies, certifications,
//  service-lines, snippets, past-proposals, contracts. Each follows the
//  same shape with the relevant fields per spec §6.)
```

For every other endpoint in spec §6, repeat the same pattern: `getX`, `createX`, `patchX`, `deleteX`. Keep the file tidy by grouping by resource.

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend-api): add tenant, assessments, capability profile, snippet helpers"
```

---

### Task 4 — `useAssessmentStream` hook

**Files:**
- Create: `frontend/lib/useAssessmentStream.ts`

- [ ] **Step 1: Implement**

```ts
import { useEffect, useState } from "react";

export type StreamState = {
  isStreaming: boolean;
  isComplete: boolean;
  stage: string;
  pct: number;
  error: string | null;
};

export function useAssessmentStream(rfpId: string, opened: boolean) {
  const [state, setState] = useState<StreamState>({
    isStreaming: false,
    isComplete: false,
    stage: "",
    pct: 0,
    error: null,
  });

  useEffect(() => {
    if (!opened || !rfpId) return;
    const url = `${process.env.NEXT_PUBLIC_API_URL}/rfps/${rfpId}/assess?stream=true`;
    const es = new EventSource(url, { withCredentials: true });
    setState((s) => ({ ...s, isStreaming: true, error: null }));
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.event === "stage") {
          setState((s) => ({ ...s, stage: data.stage, pct: data.pct ?? s.pct }));
        }
        if (data.event === "complete") {
          setState((s) => ({ ...s, isComplete: true, isStreaming: false, pct: 100 }));
          es.close();
        }
        if (data.event === "error") {
          setState((s) => ({ ...s, error: data.code || "stream error" }));
        }
        if (data.event === "close") es.close();
      } catch {
        /* malformed event line; ignore */
      }
    };
    es.onerror = () => {
      setState((s) => ({ ...s, error: "connection lost", isStreaming: false }));
      es.close();
    };
    return () => es.close();
  }, [rfpId, opened]);

  return state;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/useAssessmentStream.ts
git commit -m "feat(frontend): useAssessmentStream SSE hook"
```

---

### Task 5 — BrandThemeProvider

**Files:**
- Create: `frontend/components/branding/BrandThemeProvider.tsx`
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: Component**

```tsx
"use client";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTenant } from "@/lib/api";

export function BrandThemeProvider({ children }: { children: React.ReactNode }) {
  const { data } = useQuery({ queryKey: ["tenant", "me"], queryFn: getTenant });
  useEffect(() => {
    const brand = (data?.brand as Record<string, string> | undefined) ?? {};
    const root = document.documentElement;
    if (brand.primary_color) root.style.setProperty("--brand-primary", brand.primary_color);
    if (brand.accent_color) root.style.setProperty("--brand-accent", brand.accent_color);
  }, [data]);
  return <>{children}</>;
}
```

- [ ] **Step 2: Wrap layout**

In `frontend/app/layout.tsx`, wrap the existing tree:

```tsx
import { BrandThemeProvider } from "@/components/branding/BrandThemeProvider";

// ... inside <body>:
<BrandThemeProvider>
  {/* existing providers / shell */}
</BrandThemeProvider>
```

- [ ] **Step 3: Confirm visual**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 8
# Open http://localhost:3000 manually. Confirm no hydration errors in console.
kill $DEV_PID
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/branding/BrandThemeProvider.tsx frontend/app/layout.tsx
git commit -m "feat(frontend): BrandThemeProvider sets brand CSS vars from /tenants/me"
```

---

### Task 6 — Scorecard sub-components

**Files:**
- Create: `frontend/components/rfp/ScoreRollupHeader.tsx`
- Create: `frontend/components/rfp/CompliancePanel.tsx`
- Create: `frontend/components/rfp/EligibilityPanel.tsx`
- Create: `frontend/components/rfp/BestFitMatrix.tsx`
- Create: `frontend/components/rfp/RiskRegister.tsx`
- Create: `frontend/components/rfp/ExecSummaryCard.tsx`
- Create: `frontend/components/rfp/AssessmentHistoryMenu.tsx`

- [ ] **Step 1: ScoreRollupHeader**

```tsx
"use client";
type Props = {
  verdict: "bid" | "no_bid" | "review" | null;
  fitScore: number | null;
  winProbability: number | null;
  onRerun: () => void;
  isStreaming: boolean;
};
export function ScoreRollupHeader({ verdict, fitScore, winProbability, onRerun, isStreaming }: Props) {
  const verdictColor =
    verdict === "bid" ? "text-emerald-600" :
    verdict === "no_bid" ? "text-rose-600" :
    "text-amber-600";
  return (
    <div className="flex items-center justify-between p-4 border rounded bg-white">
      <div>
        <div className={`text-2xl font-semibold ${verdictColor}`}>
          {verdict ? verdict.toUpperCase() : "—"}
        </div>
        <div className="text-sm text-gray-600">AI recommendation</div>
      </div>
      <div className="flex gap-8">
        <Metric label="Fit score" value={fitScore} />
        <Metric label="Win probability" value={winProbability} />
      </div>
      <button onClick={onRerun} disabled={isStreaming}
              className="px-4 py-2 rounded bg-[var(--brand-primary,#2563eb)] text-white">
        {isStreaming ? "Running…" : "Re-run"}
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <div className="text-2xl font-mono">
        {value == null ? "—" : `${Math.round(value * 100)}%`}
      </div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
```

- [ ] **Step 2: CompliancePanel**

```tsx
"use client";
import { useMemo } from "react";

type Item = {
  id: string;
  label: string;
  category: string;
  mandatory: boolean;
  status: "pass" | "fail" | "partial" | "unknown";
  evidence: { kind?: string; ref_id?: string; excerpt?: string };
};

export function CompliancePanel({ items }: { items: Item[] }) {
  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, partial: 0, unknown: 0 };
    items.forEach((i) => (c[i.status] += 1));
    return c;
  }, [items]);
  return (
    <section className="p-4 border rounded">
      <header className="flex justify-between items-baseline mb-2">
        <h3 className="font-semibold">Compliance</h3>
        <span className="text-xs text-gray-600">
          {counts.pass} pass · {counts.fail} fail · {counts.partial} partial · {counts.unknown} unknown
        </span>
      </header>
      <ul className="divide-y">
        {items.map((i) => (
          <li key={i.id} className="py-2 flex items-start gap-3">
            <Pill status={i.status} />
            <div className="flex-1">
              <div className="text-sm">{i.label}{i.mandatory && <span className="text-rose-600 ml-1">★</span>}</div>
              {i.evidence?.kind === "snippet" && (
                <span className="inline-block mt-1 text-xs px-2 py-0.5 bg-violet-100 text-violet-800 rounded">
                  Suggested corporate response · {i.evidence.excerpt?.slice(0, 60)}…
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Pill({ status }: { status: string }) {
  const cls = status === "pass" ? "bg-emerald-100 text-emerald-800"
            : status === "fail" ? "bg-rose-100 text-rose-800"
            : status === "partial" ? "bg-amber-100 text-amber-800"
            : "bg-gray-100 text-gray-800";
  return <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>{status}</span>;
}
```

- [ ] **Step 3: EligibilityPanel, BestFitMatrix, RiskRegister, ExecSummaryCard, AssessmentHistoryMenu**

Implement each with the same pattern: small typed component, no hidden state, no fetching internally (parent passes data). Show:

- **EligibilityPanel** — list of `{label, kind, expected, actual, status}` with the same pill colours.
- **BestFitMatrix** — table with rows = requirements, columns = top matched offering, cell value = `match_score` rendered as a 0-100 bar.
- **RiskRegister** — list with `severity × likelihood` chip, inline edit on title/description (PATCH `/rfps/{id}/assessments/{aid}/risks/{rid}`), "Add risk" button (POST).
- **ExecSummaryCard** — renders the markdown `summary` via `react-markdown` (already in `package.json`; verify with `grep react-markdown frontend/package.json`); fallback to `<pre>` if not.
- **AssessmentHistoryMenu** — dropdown showing version list, fetched via `listAssessments(rfpId)`. Selecting a version reloads `getAssessmentLatest`-style view but for that version.

Each file: ~60–120 lines of React. No business logic that the backend doesn't already enforce.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/rfp/
git commit -m "feat(frontend): scorecard sub-components"
```

---

### Task 7 — AssessmentScorecard composite

**Files:**
- Create: `frontend/components/rfp/AssessmentScorecard.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAssessmentStream } from "@/lib/useAssessmentStream";
import {
  getAssessmentLatest,
  listAssessments,
  runAssessment,
} from "@/lib/api";
import { ScoreRollupHeader } from "./ScoreRollupHeader";
import { CompliancePanel } from "./CompliancePanel";
import { EligibilityPanel } from "./EligibilityPanel";
import { BestFitMatrix } from "./BestFitMatrix";
import { RiskRegister } from "./RiskRegister";
import { ExecSummaryCard } from "./ExecSummaryCard";
import { AssessmentHistoryMenu } from "./AssessmentHistoryMenu";

const STAGES = ["started", "parallel_done", "risk_done", "complete"];

export function AssessmentScorecard({ rfpId }: { rfpId: string }) {
  const qc = useQueryClient();
  const [openedStream, setOpenedStream] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["assessment", rfpId, "latest"],
    queryFn: () => getAssessmentLatest(rfpId),
  });
  const stream = useAssessmentStream(rfpId, openedStream);

  useEffect(() => {
    if (stream.isComplete) {
      qc.invalidateQueries({ queryKey: ["assessment", rfpId, "latest"] });
      setOpenedStream(false);
    }
  }, [stream.isComplete]);

  async function onRerun() {
    await runAssessment(rfpId);
    setOpenedStream(true);
  }

  if (isLoading) return <div>Loading…</div>;

  const head = data?.head;
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Bid assessment</h2>
        <AssessmentHistoryMenu rfpId={rfpId} />
      </div>

      {!head && !openedStream && (
        <div className="p-6 border rounded bg-gray-50 text-center">
          <button onClick={onRerun}
                  className="px-4 py-2 rounded bg-[var(--brand-primary,#2563eb)] text-white">
            Run assessment
          </button>
        </div>
      )}

      {openedStream && (
        <ProgressStrip stage={stream.stage} pct={stream.pct} error={stream.error} />
      )}

      {head && (
        <>
          <ScoreRollupHeader
            verdict={head.verdict}
            fitScore={head.fit_score}
            winProbability={head.win_probability}
            onRerun={onRerun}
            isStreaming={openedStream}
          />
          <div className="grid grid-cols-2 gap-4">
            <CompliancePanel items={data.compliance ?? []} />
            <EligibilityPanel items={data.eligibility ?? []} />
          </div>
          <BestFitMatrix matches={data.best_fit ?? []} />
          <RiskRegister assessmentId={head.id} risks={data.risks ?? []} />
          <ExecSummaryCard markdown={head.summary ?? ""} />
        </>
      )}
    </section>
  );
}

function ProgressStrip({ stage, pct, error }: { stage: string; pct: number; error: string | null }) {
  return (
    <div className="p-3 border rounded bg-blue-50">
      <div className="flex justify-between text-xs mb-1">
        <span>Stage: {stage}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 bg-blue-100 rounded">
        <div className="h-2 bg-blue-500 rounded" style={{ width: `${pct}%` }} />
      </div>
      {error && <div className="text-rose-600 text-xs mt-1">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/rfp/AssessmentScorecard.tsx
git commit -m "feat(frontend): AssessmentScorecard composite + progress strip"
```

---

### Task 8 — Single-page RFPWorkspace + DraftSection extraction

**Files:**
- Create: `frontend/components/rfp/DraftSection.tsx`
- Create: `frontend/components/rfp/RFPHeader.tsx`
- Rewrite: `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx`

- [ ] **Step 1: Extract DraftSection**

Read the existing `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx`. Identify the JSX that drives answer drafting (question list, answer pane, citations). Move that JSX into a new `frontend/components/rfp/DraftSection.tsx`, exposing it as:

```tsx
"use client";
export function DraftSection({ rfpId }: { rfpId: string }) {
  // copy of the existing draft-flow JSX, parameterised on rfpId
  return <div>{/* … existing JSX … */}</div>;
}
```

If the previous `RFPWorkspace.tsx` already passes data via props, refactor to fetch within `DraftSection` so it stands alone.

- [ ] **Step 2: RFPHeader**

```tsx
"use client";
type Props = {
  title: string;
  client?: string | null;
  dueDate?: string | null;
  status?: string | null;
};
export function RFPHeader(p: Props) {
  return (
    <header className="p-4 border-b">
      <h1 className="text-xl font-semibold">{p.title}</h1>
      <div className="text-sm text-gray-600 mt-1">
        {p.client && <span>Client: {p.client} · </span>}
        {p.dueDate && <span>Due: {p.dueDate} · </span>}
        {p.status && <span>Status: {p.status}</span>}
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Rewrite RFPWorkspace.tsx**

```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { getRfp } from "@/lib/api"; // adjust to actual existing function
import { RFPHeader } from "@/components/rfp/RFPHeader";
import { AssessmentScorecard } from "@/components/rfp/AssessmentScorecard";
import { DraftSection } from "@/components/rfp/DraftSection";

export function RFPWorkspace({ rfpId }: { rfpId: string }) {
  const { data: rfp } = useQuery({ queryKey: ["rfp", rfpId],
                                    queryFn: () => getRfp(rfpId) });
  if (!rfp) return <div className="p-8">Loading…</div>;
  return (
    <main className="max-w-6xl mx-auto p-4 space-y-6">
      <RFPHeader title={rfp.title} client={rfp.client_name}
                   dueDate={rfp.due_date} status={rfp.status} />
      <AssessmentScorecard rfpId={rfpId} />
      <DraftSection rfpId={rfpId} />
    </main>
  );
}
```

- [ ] **Step 4: Verify dev render**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 8
# Open http://localhost:3000 and click into any RFP. Confirm the page
# shows: RFP header → scorecard area (with "Run assessment" if none) →
# Draft section below.
kill $DEV_PID
```

- [ ] **Step 5: Commit**

```bash
git add frontend/components/rfp/DraftSection.tsx \
         frontend/components/rfp/RFPHeader.tsx \
         frontend/app/\(app\)/rfps/\[id\]/RFPWorkspace.tsx
git commit -m "feat(frontend): single-page RFP workspace (header + scorecard + draft)"
```

---

### Task 9 — Admin: Capabilities page

**Files:**
- Create: `frontend/app/(admin)/admin/capabilities/page.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  getCapabilityProfile, createIndustry, deleteIndustry,
  // and similarly: createGeography, deleteGeography, createCertification,
  // deleteCertification, createServiceLine, deleteServiceLine
} from "@/lib/api";

export default function CapabilitiesPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["capabilities", "profile"],
                                queryFn: getCapabilityProfile });
  const [newIndustry, setNewIndustry] = useState("");
  const addIndustry = useMutation({
    mutationFn: () => createIndustry(newIndustry),
    onSuccess: () => { setNewIndustry(""); qc.invalidateQueries({ queryKey: ["capabilities","profile"] }); },
  });
  // Mirror the same shape for geographies, certifications, service_lines.

  return (
    <div className="p-6 max-w-5xl">
      <h1 className="text-xl font-semibold mb-4">Capability profile</h1>
      <Section title="Industries">
        <ul>{(data?.industries ?? []).map((i: any) => (
          <li key={i.id} className="flex justify-between py-1">
            <span>{i.name}</span>
            <button onClick={() => deleteIndustry(i.id).then(() =>
              qc.invalidateQueries({ queryKey: ["capabilities","profile"] }))}
                    className="text-rose-600 text-sm">Delete</button>
          </li>))}</ul>
        <div className="mt-2 flex gap-2">
          <input value={newIndustry} onChange={e => setNewIndustry(e.target.value)}
                 placeholder="New industry" className="border rounded px-2 py-1" />
          <button onClick={() => addIndustry.mutate()}
                  className="px-3 py-1 bg-blue-600 text-white rounded">Add</button>
        </div>
      </Section>
      {/* Geographies, Certifications, Service lines follow same shape */}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6 p-4 border rounded">
      <h2 className="font-semibold mb-2">{title}</h2>
      {children}
    </section>
  );
}
```

- [ ] **Step 2: Verify**

`npm run dev`, log in as `system_admin`, visit `/admin/capabilities`. Confirm CRUD works for industries.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(admin\)/admin/capabilities/
git commit -m "feat(frontend-admin): capability profile editor"
```

---

### Task 10 — Admin: Snippets page

**Files:**
- Create: `frontend/app/(admin)/admin/snippets/page.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listSnippets, createSnippet, patchSnippet, deleteSnippet } from "@/lib/api";

export default function SnippetsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["snippets"], queryFn: () => listSnippets() });
  const [draft, setDraft] = useState({ title: "", body: "", topic_tags: "" });

  const add = useMutation({
    mutationFn: () => createSnippet({ title: draft.title, body: draft.body,
      topic_tags: draft.topic_tags.split(",").map(s => s.trim()).filter(Boolean) }),
    onSuccess: () => { setDraft({ title: "", body: "", topic_tags: "" });
                        qc.invalidateQueries({ queryKey: ["snippets"] }); },
  });

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-semibold mb-4">Snippet library</h1>
      <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }}
            className="space-y-2 mb-6">
        <input value={draft.title} onChange={e => setDraft({...draft, title: e.target.value})}
               placeholder="Title" className="border rounded px-2 py-1 w-full" />
        <textarea value={draft.body} onChange={e => setDraft({...draft, body: e.target.value})}
                   placeholder="Body" className="border rounded px-2 py-1 w-full h-24" />
        <input value={draft.topic_tags} onChange={e => setDraft({...draft, topic_tags: e.target.value})}
               placeholder="Comma-separated tags (gdpr, soc2)" className="border rounded px-2 py-1 w-full" />
        <button type="submit" className="px-3 py-1 bg-blue-600 text-white rounded">Add snippet</button>
      </form>
      <ul className="divide-y">
        {(data ?? []).map((s: any) => (
          <li key={s.id} className="py-3">
            <div className="flex justify-between">
              <strong>{s.title}</strong>
              <button onClick={() => deleteSnippet(s.id).then(() =>
                qc.invalidateQueries({ queryKey: ["snippets"] }))}
                       className="text-rose-600 text-sm">Archive</button>
            </div>
            <div className="text-sm text-gray-700 mt-1">{s.body.slice(0, 200)}…</div>
            <div className="text-xs mt-1 text-gray-500">
              tags: {(s.metadata?.topic_tags ?? []).join(", ")} · v{s.metadata?.version} · {s.status}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/\(admin\)/admin/snippets/
git commit -m "feat(frontend-admin): snippet library CRUD page"
```

---

### Task 11 — Admin: Past-proposals + Contracts + Branding

**Files:**
- Create: `frontend/app/(admin)/admin/past-proposals/page.tsx`
- Create: `frontend/app/(admin)/admin/contracts/page.tsx`
- Create: `frontend/app/(admin)/admin/branding/page.tsx`

- [ ] **Step 1: PastProposalsPage** — table of past_proposals with columns (Title, Client, Submitted, Outcome) plus an "Edit outcome" inline action (calls PATCH `/past-proposals/{id}` with `outcome` + `outcome_reason`). New-record form requires title, body, client_name, submitted_at; defaults `outcome=pending`.

- [ ] **Step 2: ContractsPage** — table with (Client, Effective, Expires, Value); new-record form: title, body, client_name, effective_date, expires_at, value.

- [ ] **Step 3: BrandingPage** — two colour pickers (`primary_color`, `accent_color`), a logo URL input, and a save button that calls `patchBrand`. Show a live preview swatch.

Each page mirrors the Snippet page's shape: TanStack Query for fetch, useMutation for writes, simple Tailwind form.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 8
# Login as system_admin and click through /admin/{capabilities,snippets,past-proposals,contracts,branding}.
# Confirm each loads and CRUD works.
kill $DEV_PID
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(admin\)/admin/past-proposals/ \
         frontend/app/\(admin\)/admin/contracts/ \
         frontend/app/\(admin\)/admin/branding/
git commit -m "feat(frontend-admin): past-proposals, contracts, branding pages"
```

---

### Task 12 — AppShell tenant branding + nav demotion

**Files:**
- Modify: `frontend/components/AppShell.tsx`

- [ ] **Step 1: Fetch tenant in AppShell**

In `frontend/components/AppShell.tsx`, add:

```tsx
import { useQuery } from "@tanstack/react-query";
import { getTenant } from "@/lib/api";

// inside the component:
const { data: tenant } = useQuery({ queryKey: ["tenant", "me"], queryFn: getTenant });
```

Use `tenant?.display_name` as the app title (fallback to the existing app_name setting) and `tenant?.brand?.logo_url` for the brand logo. Demote the `/ask` link in the sidebar — keep it but move it below `/rfps` and `/admin/*`.

- [ ] **Step 2: Confirm**

`npm run dev`, log in. Sidebar title and logo should reflect tenant. `/rfps` should be the primary nav item.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/AppShell.tsx
git commit -m "feat(frontend): AppShell uses tenant display_name + logo; demotes /ask"
```

---

### Task 13 — Component tests

**Files:**
- Create: `frontend/components/rfp/__tests__/ScoreRollupHeader.test.tsx`
- Create: `frontend/components/rfp/__tests__/CompliancePanel.test.tsx`
- Create: `frontend/lib/__tests__/useAssessmentStream.test.tsx`

- [ ] **Step 1: ScoreRollupHeader test**

```tsx
import { render, screen } from "@testing-library/react";
import { ScoreRollupHeader } from "../ScoreRollupHeader";

test("renders verdict and percentages", () => {
  render(<ScoreRollupHeader verdict="bid" fitScore={0.83} winProbability={0.55}
                              onRerun={() => {}} isStreaming={false} />);
  expect(screen.getByText("BID")).toBeInTheDocument();
  expect(screen.getByText("83%")).toBeInTheDocument();
  expect(screen.getByText("55%")).toBeInTheDocument();
});
```

- [ ] **Step 2: CompliancePanel summary line**

```tsx
import { render, screen } from "@testing-library/react";
import { CompliancePanel } from "../CompliancePanel";

const items = [
  { id: "1", label: "SOC 2", category: "security", mandatory: true,
    status: "pass" as const, evidence: { kind: "snippet", excerpt: "We hold SOC 2 ..." } },
  { id: "2", label: "GDPR", category: "privacy", mandatory: false,
    status: "fail" as const, evidence: {} },
];

test("counts and snippet pill render", () => {
  render(<CompliancePanel items={items} />);
  expect(screen.getByText(/1 pass · 1 fail/)).toBeInTheDocument();
  expect(screen.getByText(/Suggested corporate response/)).toBeInTheDocument();
});
```

- [ ] **Step 3: useAssessmentStream test (using EventSource polyfill)**

```tsx
import { renderHook, act } from "@testing-library/react";
import { useAssessmentStream } from "../useAssessmentStream";

class MockES {
  static instance: MockES;
  onmessage: any = null; onerror: any = null;
  constructor() { MockES.instance = this; }
  close() {}
}
beforeEach(() => { (global as any).EventSource = MockES; });

test("processes complete event", () => {
  const { result } = renderHook(() => useAssessmentStream("rfp-1", true));
  act(() => {
    MockES.instance.onmessage({ data: JSON.stringify({ event: "complete", assessment_id: "a-1" }) } as any);
  });
  expect(result.current.isComplete).toBe(true);
});
```

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npm test -- --run && cd -
```

Expected: green (assumes Vitest or Jest is configured — verify via `grep -l '"test"' frontend/package.json`).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/rfp/__tests__/ frontend/lib/__tests__/
git commit -m "test(frontend): scorecard + stream hook component tests"
```

---

### Task 14 — Merge phase 4

- [ ] **Step 1: Full sweep**

```bash
cd frontend && npm test -- --run && npm run typecheck && npm run build && cd -
```

Expected: green build.

- [ ] **Step 2: Merge**

```bash
git checkout feat/bid-assessment
git merge --no-ff feat/bid-assessment-phase-4-frontend \
  -m "Phase 4: single-page workspace + admin pages + branding"
git push origin feat/bid-assessment
```

Phase 4 done.
