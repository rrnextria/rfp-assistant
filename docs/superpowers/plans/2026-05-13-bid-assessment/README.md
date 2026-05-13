# Bid Assessment Implementation Plan — Master Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase task-by-task. Each phase file uses checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition the existing RFP Assistant into a Bid Assessment product whose primary value is an AI-driven scorecard (compliance, eligibility, best-fit, risks) per RFP, while preserving the existing answer-drafting flow as a downstream feature.

**Spec:** `docs/superpowers/specs/2026-05-13-bid-assessment-design.md` (authoritative)

**Architecture:** Multi-tenant codebase, generic by design (Akkodis is the first tenant). Reuses the 11-service deployment topology; renames `portfolio-service` to `capability-service`; extends `orchestrator`, `rfp-service`, `content-service`, `retrieval-service`, `analytics-service`, `api-gateway`. Frontend single-page workspace replaces the current multi-screen RFP UI.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.x (async) + Alembic + pgvector + Postgres + Next.js 14 (App Router) + React + Tailwind.

---

## Phase order and dependencies

Execute phases sequentially. Each phase ends with a passing test suite, a working demo affordance, and a commit on the long-lived feature branch.

| # | Phase file | Demo affordance after completion |
|---|---|---|
| 1 | [`phase-1-capability-service.md`](./phase-1-capability-service.md) | `portfolio-service` is renamed; admin can edit 5-dim capability profile via `/capabilities/*` routes; legacy `/portfolio/*` is gone |
| 2 | [`phase-2-kb-extensions.md`](./phase-2-kb-extensions.md) | `documents.category` enum live; typed `past_proposals` + `contracts` tables with admin UI; snippets searchable; tag classification active |
| 3 | [`phase-3-bid-assessment-core.md`](./phase-3-bid-assessment-core.md) | `POST /rfps/{id}/assess` returns a full assessment; SSE streams progress; 5 agents run in parallel; child rows persisted |
| 4 | [`phase-4-frontend.md`](./phase-4-frontend.md) | RFP workspace shows scorecard + draft inline on a single page; admin pages live; branding theme provider active |
| 5 | [`phase-5-analytics.md`](./phase-5-analytics.md) | `analytics-service` aggregates past-proposal outcomes and emits gated boosts; `SummaryAgent` consumes them; admin "Learning status" card honest about cold start |

## Branching

Long-lived branch: `feat/bid-assessment` off `master`. One sub-branch per phase (e.g. `feat/bid-assessment-phase-1-capability-service`), merged into the long-lived branch when its demo affordance works. Merge to `master` only when all five phases pass end-to-end on the Akkodis seed.

## Testing strategy (applies to every phase)

- **Unit tests** for new pure functions / agents (stub LLM client; canned inputs/outputs).
- **Integration tests** for new endpoints (use the existing `httpx.ASGITransport` pattern in `services/*/tests/`).
- **Migration test** runs `scripts/test_workflows.py` after every migration: clean DB → `upgrade head` → `downgrade base` → `upgrade head`.
- **Tenancy leak test** seeded with two tenants asserts no cross-tenant row leaks (added in phase 3 once `bid_assessments` exists).
- **Frontend component tests** for new scorecard components + `useAssessmentStream` (phase 4).

## Out of scope across all phases (matches spec §2.2)

- PDF/DOCX export.
- Formal `bid_decisions` table; draft-stage gating.
- Tenant self-signup.
- Per-tenant Postgres schema.
- Background job queue.
- External KB connectors (SharePoint, Confluence, Salesforce).
- Automatic snippet generation.
- Multilingual content.
- Mobile-first UI.

## Resume-from-fail rule

If a phase fails midway, finish the in-flight task to a clean state (commit or revert), then re-enter the phase file at the next unchecked task. Never start phase N+1 with phase N tasks unfinished.

---

## Phase-1 quick start

```bash
git checkout master
git checkout -b feat/bid-assessment
git checkout -b feat/bid-assessment-phase-1-capability-service

# Then open phase-1-capability-service.md and work through tasks in order.
```
