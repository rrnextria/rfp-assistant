# Phase 6: Frontend (Next.js)

**Status:** Pending
**Planned Start:** 2026-04-25
**Target End:** 2026-05-05
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_6_frontend.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 5 | Next: Phase 7

---

## Detailed Objective

This phase delivers the Next.js frontend with all four pages and all components from spec §9: `/chat` (free-form Q&A), `/rfp/[id]` (RFP workspace with question list, editor, and approvals), `/admin/users` (user management), and `/admin/content` (document upload and approval). All pages authenticate via JWT stored in an HttpOnly cookie and call the backend REST API.

The UI implements the full chat experience with mode selection (`answer`, `draft`, `review`, `gap`), streaming answer display via SSE, and a citations panel that links back to source documents. The RFP workspace allows users to view questions, trigger generation, edit answers inline, and approve — matching the Phase 5 API capabilities.

This phase uses React Server Components where possible (page-level data fetching) and client components for interactive elements (ChatBox, Editor, streaming). The design system uses Tailwind CSS + shadcn/ui for accessible, consistent styling.

Success is defined as: a user can log in, ask a question in chat and see a streamed answer with citations, create an RFP, add questions, generate answers, and approve them — all through the browser with no direct API calls from the browser console.

---

## Deliverables Snapshot

1. Next.js 14 app in `frontend/` with TypeScript, Tailwind CSS, shadcn/ui, and a typed API client generated from the FastAPI OpenAPI spec.
2. `/chat` page: ChatBox, ModeSelector, streamed AnswerPane, CitationsPanel.
3. `/rfp/[id]` page: RFPQuestionList, inline Editor, answer versioning display, approve button (content_admin only).
4. `/admin/users` page: AdminTable for user list, create user form (system_admin only).
5. `/admin/content` page: document upload form (with metadata), document list with approval button (content_admin only).

---

## Acceptance Gates

- [ ] Gate 1: A user can log in via `/login`, receive an HttpOnly cookie, and reach `/chat` without an API error.
- [ ] Gate 2: Submitting a question in `/chat` streams the answer token-by-token via SSE; the CitationsPanel shows at least one citation with a snippet.
- [ ] Gate 3: `/rfp/[id]` renders all questions; clicking "Generate" for a question triggers generation and updates the answer pane on completion.
- [ ] Gate 4: `/admin/users` is only accessible to `system_admin`; `/admin/content` is only accessible to `content_admin`/`system_admin`; others are redirected to `/403`.
- [ ] Gate 5: `npm run build` and `npm run lint` pass with zero errors.

---

## Scope

- In Scope:
  1. Next.js 14 app router with TypeScript.
  2. Typed API client (`fetch`-based) matching all Phase 1–5 endpoints.
  3. Auth: login page, HttpOnly cookie via Next.js API route proxy, auth middleware for route protection.
  4. `/chat`, `/rfp/[id]`, `/admin/users`, `/admin/content` pages with all components from spec §9.
  5. Streaming SSE consumption for chat answers.
  6. Responsive layout (Tailwind) — desktop first, mobile-accessible.
- Out of Scope:
  1. Copilot/Teams frontend (Phase 7).
  2. RFP export to PDF/DOCX (post-MVP).
  3. Real-time collaboration / websockets (post-MVP).
  4. Mobile app (post-MVP).

---

## Interfaces & Dependencies

- Internal: All Phase 1–5 REST endpoints; SSE stream from `POST /ask?stream=true`.
- External: Next.js 14, React 18, TypeScript, Tailwind CSS, shadcn/ui, `eventsource-parser` (SSE client), `js-cookie` / HttpOnly cookie via Next.js route handler.
- Artifacts: `frontend/` directory with all pages and components; `frontend/lib/api.ts` typed API client.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| CORS issues between Next.js dev server and FastAPI | API calls blocked | Use Next.js `rewrites` in `next.config.js` to proxy `/api/*` to FastAPI in dev |
| SSE stream not consumed correctly in React | Streaming broken | Use `eventsource-parser` library; test with `curl` first then React |
| JWT in HttpOnly cookie not sent on API routes | Auth fails | Set `credentials: "include"` on all fetch calls; configure FastAPI CORS with `allow_credentials=True` |
| shadcn/ui component conflicts with Tailwind version | Build errors | Pin shadcn/ui and Tailwind to compatible versions per shadcn docs |

---

## Decision Log

- D1: HttpOnly cookie (via Next.js API route proxy) over localStorage for JWT — prevents XSS token theft — Status: Closed — Date: 2026-03-18
- D2: Next.js `rewrites` for API proxying in dev — avoids CORS config complexity — Status: Closed — Date: 2026-03-18
- D3: shadcn/ui over a full component library — gives full control of component code without bundle bloat — Status: Closed — Date: 2026-03-18
- D4: React Server Components for page-level data fetching; client components only for interactivity — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §9 Frontend Pages and Components

### Destination Files (new files this phase creates)
- `frontend/app/` — Next.js app router pages
- `frontend/components/` — All spec §9 components
- `frontend/lib/api.ts` — Typed API client
- `frontend/middleware.ts` — Auth route protection

### Related Documentation (context only)
- `spec.md` — §9 Frontend, §6 API Contracts
- `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md` — Streaming SSE

---

## Tasks

### [✅] 1 Set Up Next.js Project and API Client
Bootstrap the frontend project with TypeScript, Tailwind, shadcn/ui, and a typed API client.

  - [✅] 1.1 Create Next.js 14 app in `frontend/` with TypeScript and Tailwind CSS (`npx create-next-app@latest`); install shadcn/ui (`npx shadcn@latest init`); configure `next.config.js` with API `rewrites` pointing `/api/*` to FastAPI
  - [✅] 1.2 Implement `frontend/lib/api.ts` typed API client — wrapper around `fetch` with base URL from env, automatic `Authorization` header injection, error handling; typed functions for all Phase 1–5 endpoints
  - [✅] 1.3 Implement auth middleware in `frontend/middleware.ts` — redirect unauthenticated users to `/login`; redirect non-admin roles away from `/admin/*`; implement `POST /auth/login` proxy route that sets HttpOnly cookie

### [✅] 2 Build Chat Page
Implement the `/chat` page with all interactive components and SSE streaming.

  - [✅] 2.1 Implement `ChatBox` component — textarea input, submit button, loading state; on submit calls `POST /ask` with `{question, mode, rfp_id}`
  - [✅] 2.2 Implement `ModeSelector` component — tab or dropdown selecting `answer | draft | review | gap`; passes selected mode to ChatBox
  - [✅] 2.3 Implement `AnswerPane` component — renders streamed answer text progressively by consuming the SSE stream via `eventsource-parser`; shows spinner while streaming
  - [✅] 2.4 Implement `CitationsPanel` component — renders list of `{chunk_id, doc_id, snippet}` citations returned with the answer; each citation shows snippet text and doc title

### [✅] 3 Build RFP Workspace Page
Implement `/rfp/[id]` with question list, answer editor, and approval workflow.

  - [✅] 3.1 Implement `RFPQuestionList` component — server component fetching questions + latest answers; renders each question with its answer (or "Not yet generated" placeholder) and a "Generate" button
  - [✅] 3.2 Implement `Editor` component — rich text editor (textarea for MVP) for editing answer text; on save calls `PATCH .../answers/{aid}` with optimistic version; shows version history toggle
  - [✅] 3.3 Implement approve button (visible to `content_admin`/`system_admin` only) — calls `POST .../approve`; updates UI to show approved badge

### [✅] 4 Build Admin Pages
Implement `/admin/users` and `/admin/content` for system and content admins.

  - [✅] 4.1 Implement `/admin/users` page — `AdminTable` component listing users with columns: email, role, teams; "Create User" button opens form calling `POST /users`; page protected to `system_admin` role
  - [✅] 4.2 Implement `/admin/content` page — document upload form (file input + metadata fields: product, region, industry, allowed_teams, allowed_roles); document list with status badges and "Approve" button (content_admin); calls `POST /documents` and `PATCH /documents/{id}/approve`
  - [✅] 4.3 Implement `/403` page and `/login` page; write E2E smoke test (`playwright` or `cypress`): login → chat → submit question → assert answer rendered


---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile rfp_assistant` if checkmarks appear stale.

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] Optional deeper tasks use `- [ ] N.1.1` and never headings.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.

### Traceability

- [ ] All tasks reflect Detailed Objective and Scope.
- [ ] Task titles match what will appear in the master plan.
- [ ] No invented tasks.

### Consistency

- [ ] Section ordering follows the template.
- [ ] All metadata fields are present in the Header.
- [ ] Deliverables Snapshot, Acceptance Gates, and Scope refer to real tasks.

### References

- [ ] Source, Destination, and Related Documentation sections appear.
