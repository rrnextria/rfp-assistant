# Phase 4: Frontend Timeline & Scorecard

**Status:** Pending
**Planned Start:** 2026-06-19
**Target End:** 2026-06-30
**Last Updated:** 2026-05-13 by Ravi (Engineer)
**File:** `active_plans/bid-assessment-pivot/phases/phase_4_frontend_timeline.md`
**Related:** Master Plan (`active_plans/bid-assessment-pivot/bid-assessment-pivot_master_plan.md`) | Prev: Phase 3 | Next: Phase 5

---

## Detailed Objective

Reshape the RFP workspace from a single-purpose Q&A page into a six-stage timeline container, and build the Assessment scorecard that consumes the endpoints landed in Phase 3. The existing answer-drafting and review behaviours are extracted (not rewritten) into `DraftStage.tsx` and `ReviewStage.tsx`, preserving every interaction the current `RFPWorkspace.tsx` already provides. New stage-specific components — `AssessmentScorecard`, `ScoreRollupHeader`, `ComplianceGrid`, `EligibilityPanel`, `RiskRegister`, `CoverageMatrix`, `ExecSummaryCard`, `BidDecisionForm`, `AssessmentHistoryMenu` — slot into the timeline frame.

The phase introduces `useAssessmentStream` for SSE consumption, drives the timeline state from server data (not UI state), and ensures locked stages render in greyed-out form with a "Complete <previous> to unlock" message — nothing is hidden. The `Decision` stage's `POST /rfps/{id}/bid-decision` call is what unlocks the `Draft` stage.

Success: A user can walk the whole stack from an Akkodis-seeded RFP through the timeline UI: upload (existing), extract (existing), assess (new — triggers, streams, renders scorecard), decide (new — form + persisted), draft (existing, now extracted), review (existing, now extracted) — all without console errors and with role gates respected.

---

## Deliverables Snapshot

1. `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` reshaped as a thin stage orchestrator that fetches RFP + latest assessment + decision and routes to the active stage.
2. `frontend/components/rfp/RFPTimeline.tsx` — left-rail stepper driven by server data.
3. `frontend/components/rfp/AssessmentScorecard.tsx` and 7 sub-components (`ScoreRollupHeader`, `ComplianceGrid`, `EligibilityPanel`, `RiskRegister`, `CoverageMatrix`, `ExecSummaryCard`, `AssessmentHistoryMenu`).
4. `frontend/components/rfp/BidDecisionForm.tsx`.
5. `frontend/components/rfp/DraftStage.tsx` and `ReviewStage.tsx` extracted from the existing workspace.
6. `frontend/lib/useAssessmentStream.ts` — SSE hook returning `{progress, currentAgent, error, isComplete, assessment}`.
7. New API client functions in `frontend/lib/api.ts`.
8. Component tests for the new scorecard components and the stream hook.

---

## Acceptance Gates

- [ ] Gate 1: Existing answer-drafting flow regression-free — the extracted `DraftStage.tsx` reproduces every interaction the current `RFPWorkspace.tsx` provides (verified by replaying the existing Q&A tests through the new mount point).
- [ ] Gate 2: Timeline state matches server data — Upload/Extract/Assess/Decision/Draft/Review locks correctly given fixture states (covered by Storybook-style fixture tests or equivalent).
- [ ] Gate 3: Triggering an assessment streams SSE progress events through `useAssessmentStream`; the scorecard renders fully once `isComplete=true`.
- [ ] Gate 4: `BidDecisionForm` submits and the `Draft` stage transitions from locked to unlocked.
- [ ] Gate 5: All scorecard components handle empty / partial / failed assessment states without console errors.
- [ ] Gate 6: Role gates respected — an `end_user` cannot see compliance-edit affordances; a `content_admin` can.

---

## Scope

- In Scope:
  1. Reshape `RFPWorkspace.tsx` into stage container.
  2. Build 9 new components under `frontend/components/rfp/`.
  3. Extract `DraftStage.tsx` and `ReviewStage.tsx` from existing workspace.
  4. Build `useAssessmentStream` hook.
  5. Add new API client functions.
  6. Component tests.
  7. No new dependencies beyond what's already in `frontend/package.json`.
- Out of Scope:
  1. PDF/DOCX export dialog (Phase 5 — but a stub button is OK in this phase if it points to Phase-5 work).
  2. Branding wiring (Phase 6).
  3. Drag-and-drop risk reordering.
  4. Inline edit-on-double-click.
  5. Real-time multi-user editing.
  6. Mobile-specific redesign.

---

## Interfaces & Dependencies

- Internal: existing components (`AnswerPane`, `CitationsPanel`, `ChatBox`, `ModeSelector`), existing `frontend/lib/api.ts`, existing `frontend/components/AppShell.tsx`.
- External: Tailwind (existing), React 18 (existing), `EventSource` (browser native), no new packages.
- Artifacts: see Deliverables Snapshot.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Extraction of Draft/Review loses subtle existing behaviours | Q&A flow regresses | Extract via move-not-rewrite; rerun existing Q&A tests pointed at the new mount. |
| SSE connection drops mid-stream | UI shows half-complete state | `useAssessmentStream` auto-reconnects on `error` and on completion refetches `/assessments/latest` for authoritative state. |
| Heat-map CoverageMatrix struggles with hundreds of requirements × dozens of offerings | Performance issue | Virtualised rendering only past 50×20; below that, plain DOM is fine. |
| RiskRegister allows ad-hoc add/edit/delete during in-flight assessment | UI/DB race condition | All mutations require `If-Match: <bid_assessments.version>`; the form refreshes version on 409 with a toast. |
| Locked-stage messaging is unclear | Users wonder why Draft is greyed | Each locked stage shows "Complete <previous> to unlock" text + a one-line explainer. |

---

## Decision Log

- D1: Extract `DraftStage.tsx` + `ReviewStage.tsx` rather than refactor in place — Status: Closed — Date: 2026-05-13
- D2: Timeline state is server-derived, not client state — Status: Closed — Date: 2026-05-13
- D3: Locked stages stay visible (greyed-out), not hidden — Status: Closed — Date: 2026-05-13
- D4: Single SSE hook owned by `AssessmentScorecard` — Status: Closed — Date: 2026-05-13
- D5: No new npm dependencies in this phase — Status: Closed — Date: 2026-05-13

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy.

### Source Files
- `frontend/app/(app)/rfps/[id]/RFPWorkspace.tsx` — to be reshaped
- `frontend/components/AnswerPane.tsx` — used inside DraftStage
- `frontend/components/CitationsPanel.tsx` — used inside DraftStage
- `frontend/components/ChatBox.tsx` — used inside DraftStage
- `frontend/components/ModeSelector.tsx` — used inside DraftStage
- `frontend/lib/api.ts` — gains new client functions
- `frontend/app/(app)/rfps/page.tsx` — RFP list (may show new "Assessed" status badge)
- `frontend/components/AppShell.tsx` — admin nav already extended in earlier phases

### Destination Files
- `frontend/components/rfp/RFPTimeline.tsx`
- `frontend/components/rfp/AssessmentScorecard.tsx`
- `frontend/components/rfp/ScoreRollupHeader.tsx`
- `frontend/components/rfp/ComplianceGrid.tsx`
- `frontend/components/rfp/EligibilityPanel.tsx`
- `frontend/components/rfp/RiskRegister.tsx`
- `frontend/components/rfp/CoverageMatrix.tsx`
- `frontend/components/rfp/ExecSummaryCard.tsx`
- `frontend/components/rfp/AssessmentHistoryMenu.tsx`
- `frontend/components/rfp/BidDecisionForm.tsx`
- `frontend/components/rfp/DraftStage.tsx` (extracted)
- `frontend/components/rfp/ReviewStage.tsx` (extracted)
- `frontend/lib/useAssessmentStream.ts`

### Related Documentation
- `docs/superpowers/specs/2026-05-13-bid-assessment-pivot-design.md` §7

---

## Tasks

### [ ] 1 Extract Draft and Review stages from RFPWorkspace
Move existing Q&A logic into `DraftStage.tsx` and approval logic into `ReviewStage.tsx`.

  - [ ] 1.1 Read current `RFPWorkspace.tsx`; identify Q&A vs approval responsibilities
  - [ ] 1.2 Create `frontend/components/rfp/DraftStage.tsx` containing the AnswerPane / ChatBox / CitationsPanel / ModeSelector composition
  - [ ] 1.3 Create `frontend/components/rfp/ReviewStage.tsx` containing the approval flow
  - [ ] 1.4 Rerun existing Q&A tests against the new mount point; fix paths/imports until green
  - [ ] 1.5 Ensure no behavioural change visible to a logged-in user mid-flow

### [ ] 2 Reshape RFPWorkspace as stage container
RFPWorkspace.tsx now fetches RFP + latest assessment + latest decision and routes to the active stage.

  - [ ] 2.1 Fetch on mount: `/rfps/{id}`, `/rfps/{id}/assessments/latest`, `/rfps/{id}/bid-decision`
  - [ ] 2.2 Compute timeline state from the fetched data
  - [ ] 2.3 Render `<RFPTimeline />` left rail + active stage component right pane
  - [ ] 2.4 Manage the SSE connection lifecycle when the user is on the Assess stage
  - [ ] 2.5 Pass refresh callbacks downstream so stages can request a state re-fetch

### [ ] 3 Build RFPTimeline component
Left-rail stepper driven by server-derived state.

  - [ ] 3.1 Six stage labels with status indicators (`✓ done`, `◉ active`, `○ unlocked`, `─ locked`)
  - [ ] 3.2 Locked stages render greyed-out with "Complete <previous> to unlock" tooltip
  - [ ] 3.3 Active stage highlighted; clicking switches active stage if allowed
  - [ ] 3.4 Accessible: ARIA labels per step; tab-navigable

### [ ] 4 Build AssessmentScorecard and sub-components
Main container for the Assess stage; orchestrates score rollup + 5 detail panels + history.

  - [ ] 4.1 `AssessmentScorecard.tsx` — owns the SSE connection via `useAssessmentStream`
  - [ ] 4.2 `ScoreRollupHeader.tsx` — shows fit_score, win_probability, AI verdict, human decision (when present)
  - [ ] 4.3 `ComplianceGrid.tsx` — sortable grid: requirement | status | evidence | citations | "edit" (content_admin+)
  - [ ] 4.4 `EligibilityPanel.tsx` — big visual pass/fail per check at top of scorecard
  - [ ] 4.5 `RiskRegister.tsx` — editable table; add / edit / delete with confirmation
  - [ ] 4.6 `CoverageMatrix.tsx` — heat-map (requirements rows × offerings columns), virtualised past 50×20
  - [ ] 4.7 `ExecSummaryCard.tsx` — rendered markdown of summary; "regenerate" button (calls `POST /rfps/{id}/assess` for new version)
  - [ ] 4.8 `AssessmentHistoryMenu.tsx` — dropdown listing past versions, selecting one loads it

### [ ] 5 Build BidDecisionForm
Form to record a human bid decision.

  - [ ] 5.1 Verdict radio: `BID`, `NO-BID`, `REVIEW`
  - [ ] 5.2 Rationale textarea (required)
  - [ ] 5.3 Conditions list (dynamic add/remove)
  - [ ] 5.4 Submit calls `POST /rfps/{id}/bid-decision`; on success, triggers RFPWorkspace state refresh (which unlocks Draft)

### [ ] 6 Implement useAssessmentStream hook
SSE consumption with progress, error, completion.

  - [ ] 6.1 `frontend/lib/useAssessmentStream.ts` opens `EventSource` on `/rfps/{rfpId}/assess?stream=true`
  - [ ] 6.2 Maintains state `{progress, currentAgent, error, isComplete, assessment}`
  - [ ] 6.3 On `pipeline_complete`, fetches `/rfps/{id}/assessments/latest` for authoritative state
  - [ ] 6.4 Auto-reconnect once on transient error; surface persistent error to caller
  - [ ] 6.5 Closes on unmount; cleans up the EventSource
  - [ ] 6.6 Unit test using a mock EventSource

### [ ] 7 Add API client functions
Extend `frontend/lib/api.ts` with the new endpoints.

  - [ ] 7.1 `startAssessment(rfpId)`, `getAssessment(rfpId, assessmentId)`, `getLatestAssessment(rfpId)`, `listAssessments(rfpId)`
  - [ ] 7.2 `patchComplianceItem`, `patchRisk`, `addRisk`, `deleteRisk` — with `If-Match` header support
  - [ ] 7.3 `postBidDecision(rfpId, body)`, `getBidDecision(rfpId)`
  - [ ] 7.4 Snippet client functions (if not already added in Phase 2)
  - [ ] 7.5 All functions reuse the existing fetch helper with JWT injection

### [ ] 8 Component tests
Cover the SSE hook and the scorecard components.

  - [ ] 8.1 `useAssessmentStream` — mock EventSource, exercise progress/error/complete paths
  - [ ] 8.2 `RFPTimeline` — render fixture states (all-locked, mid-flow, all-done)
  - [ ] 8.3 `ComplianceGrid` — empty / partial / full fixture data
  - [ ] 8.4 `BidDecisionForm` — submit validation, error path, success path
  - [ ] 8.5 `RiskRegister` — add/edit/delete with optimistic-lock 409 handling

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile <slug>` if checkmarks appear stale.

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
