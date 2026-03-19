<!-- Updated on 2025-10-19: reorganized per master plan guidelines, fixed task formatting -->
<!--
WORKFLOW FOR CREATING THIS PLAN:

1. Choose project name (slug): e.g., "manifest_elimination"

2. Create folder structure:
   mkdir -p active_plans/{slug}/phases/

3. Create this master plan file:
   active_plans/{slug}/{slug}_master_plan.md

4. Fill these sections NOW (before writing phases):
   - Executive Summary
   - Detailed Objective
   - Architecture Overview
   - Current State
   - Desired State
   - Global Risks & Mitigations
   - Global Acceptance Gates
   - Quick Navigation (table only, leave status empty)

5. ADD temporary planning notes at top:
   ## Planning Notes (DELETE BEFORE REVIEW)
   - Phase 0: {what it does}
   - Phase 1: {what it does}
   - Phase 2: {what it does}

6. SKIP "Phases Overview" section (add placeholder):
   ## Phases Overview
   <!-- To be filled after phases complete -->

7. Create empty phase files with basic headers:
   active_plans/{slug}/phases/phase_0_{name}.md
   active_plans/{slug}/phases/phase_1_{name}.md
   (Copy structure from phase_plan_template.md)

8. Fill each phase file completely:
   - Can be done sequentially (one at a time)
   - Can be parallelized (one agent per phase if independent)

9. Reconcile master plan:
   - Read each completed phase file
   - Extract task titles (### [ ] N) and first-level subtasks ONLY (- [ ] N.1, N.2, etc.)
   - Do NOT include: task descriptions, sub-sub-tasks (N.1.1), acceptance criteria
   - Fill "Phases Overview" section in master
   - Delete "Planning Notes" section

10. Verify master mirrors phases:
    for f in active_plans/{slug}/phases/*.md; do grep -E "^### \[.?\]" $f; done
    grep -E "^### \[.?\]" active_plans/{slug}/{slug}_master_plan.md

10.5. Run `./how_to/maistro plan-verify <master-plan>` — do not proceed to review until zero errors.
-->
# Master Plan Template

Purpose: Central index for complex, multi‑phase efforts. Keep this file concise and greppable. Phase details live in per‑phase files.

---

## LLM Navigation & Grep Guide (For LLMs Only)

This section exists ONLY for LLMs and tooling. Do NOT modify or remove.

### Grepping Phase Headings in the Master Plan

- `grep -n "^### Phase [0-9]\+:" <master>`

### Grepping Task Headings in Phase Files

- `grep -nE "^### \[ \] [0-9]+ " active_plans/{slug}/phases/phase_*.md`
- `grep -nE "^  - \[ \] [0-9]+\.[0-9]+ " active_plans/{slug}/phases/phase_*.md`

### Grepping Mirrored Tasks in the Master Plan (Phases Overview)

- `grep -nE "^### \[ \] [0-9]+ " <master>`
- `grep -nE "^  - \[ \] [0-9]+\.[0-9]+ " <master>`

### LLM RULES for the Master Plan

- Do NOT invent tasks.
- Do NOT modify task numbers or titles copied from phase files.
- Only include top-level tasks (`### [ ] N`) and first-level subtasks (`  - [ ] N.1`) in the master.
- Never include sub-sub-tasks (e.g., `1.1.1`) in the master plan.

---

## Required Sections (in order)
1. Executive Summary
2. Detailed Objective
3. Quick Navigation
4. Architecture Overview
5. Current State
6. Desired State
7. Global Risks & Mitigations
8. Global Acceptance Gates
9. Dependency Gates
10. Phases Overview
11. Decision Log
12. References

---

## Executive Summary
High‑level, non‑technical summary of what this program delivers; highlight current blockers (if any) and target outcome.

## Detailed Objective
Detailed narrative (multi‑paragraph) describing goals, constraints/assumptions, measurable outcomes, and the definition of success. Be explicit about what is in/out at the program level.

## Quick Navigation
| Phase | Focus | Status | File |
|---|---|---|---|
| 0 | {focus} | 🔄 | `active_plans/{slug}/phases/phase_0_{title}.md` |
| 1 | {focus} | 🔄 | `active_plans/{slug}/phases/phase_1_{title}.md` |
| 2 | {focus} | 🔄 | `active_plans/{slug}/phases/phase_2_{title}.md` |

## Architecture Overview
High‑level design and major components. Keep this at the system‑orientation level; deep details belong in phase files or separate design docs referenced below.

## Current State
Key facts about the repository and runtime today (paths, services, major gaps/constraints).

## Desired State
Target behaviors, capabilities, and architecture once all phases are complete.

(Note: Specific phase-level artifacts are defined in phase plans; the master plan tracks only high-level goals and phase documents.)

## Global Risks & Mitigations
Program‑level risks (cross‑phase) and how they are addressed.

| Risk | Impact | Mitigation |
|------|--------|-----------|
| {risk} | {impact} | {mitigation} |

## Global Acceptance Gates
Cross‑phase, measurable criteria required for the overall program to be considered complete.

- [ ] Gate 1: {measurable}
- [ ] Gate 2: {measurable}
- [ ] Gate 3: {measurable}

## Dependency Gates
Program‑level or phase‑to‑phase prerequisites that must be satisfied before proceeding.

- [ ] Dependency 1: {artifact or condition}
- [ ] Dependency 2: {artifact or condition}

## Phases Overview

**What to include:**
- Phase heading with file path: `### Phase N: {Title} — path/to/phase_file.md`
- Tasks subheading: `#### Tasks`
- All numbered task titles from the phase file: `### [ ] 1 {Task Name}`
- All first-level subtasks from the phase file: `  - [ ] 1.1 Sub-task description`

**What to exclude (these stay in the phase file only):**
- Detailed task descriptions
- Acceptance criteria
- Sub-sub-tasks (e.g., if phase has 1.1.1, don't include it here)
- Implementation notes

**Format:**
- Task title: `### [ ] 1 {Task Name}` (heading-level 3, numbered)
- First-level subtask: `  - [ ] 1.1 Description` (indented list, 2 spaces)
- Do NOT manually toggle checkmarks — `plan-sync` handles this automatically after task approval

### LLM RULES (For Phases Overview)

- Master plan MUST mirror tasks from the corresponding phase files verbatim.

**Include ONLY:**

- `### Phase N: {Title} — path/to/file.md` (H3)
- `#### Tasks`
- Top-level tasks: `### [ ] 1 {Task Name}`
- First-level subtasks: `  - [ ] 1.1 Sub-task description`

**DO NOT include:**

- Task descriptions
- Acceptance criteria
- Sub-sub-tasks (e.g., `1.1.1`)
- Any content not present in the phase file

- Do NOT manually toggle checkmarks. The `plan-sync` tool updates both master and phase files automatically after reviewer approval.

### Numbering Rules (Master Plan)

- Top-level mirrored tasks MUST use: `### [ ] 1`, `### [ ] 2`, etc.
- First-level subtasks MUST use: `  - [ ] 1.1`, `  - [ ] 1.2`, etc.
- NEVER include levels deeper than `1.1` in the master plan.
- NEVER skip numbers.
- NEVER reorder or renumber tasks unless phase files change.

### Phase 0: {Title} — `active_plans/{slug}/phases/phase_0_{title}.md`
#### Tasks
### [ ] 1 {Task Name}
  - [ ] 1.1 Sub-task description
  - [ ] 1.2 Sub-task description
### [ ] 2 {Task Name}
  - [ ] 2.1 Sub-task description
  - [ ] 2.2 Sub-task description

### Phase 1: {Title} — `active_plans/{slug}/phases/phase_1_{title}.md`
#### Tasks
### [ ] 1 {Task Name}
  - [ ] 1.1 Sub-task description
  - [ ] 1.2 Sub-task description
### [ ] 2 {Task Name}
  - [ ] 2.1 Sub-task description
  - [ ] 2.2 Sub-task description

<!-- Duplicate the Phase N block as needed for additional phases -->

## Decision Log
- D1: {decision} — Status: Open/Closed — Date: YYYY‑MM‑DD

## References

(Note: Reference structure intentionally matches the Simple Plan template for consistency across plan types.)

**Purpose:** Files listed here authorize the reviewer to read them to validate this plan's accuracy.

### Source Files (existing code/docs being modified)
- `path/to/existing_file.py` — Current implementation description
- `path/to/existing_guide.md` — Existing guide to consolidate

### Destination Files (new files this plan creates)
- `path/to/new_file.py` — New file description
- `path/to/new_guide.md` — New guide location

### Related Documentation (context only)
- `docs/SYSTEM_OVERVIEW.md` — Background reference
- `tests/` — Related tests

---

## Reviewer Checklist

Reviewers MUST verify all of the following:

### Structure & Numbering

- [ ] Required sections appear in the correct order.
- [ ] All mirrored tasks use correct patterns (`### [ ] N`, `  - [ ] N.1`).
- [ ] No `1.1.1` items appear in the master plan.

### Traceability

- [ ] Every task in the master appears in the corresponding phase file.
- [ ] No task exists in the master that is not in a phase file.
- [ ] Global Acceptance Gates map to real tasks or phases.

### Consistency

- [ ] Phase titles and file paths match actual files.
- [ ] No invented content appears in Phases Overview.
- [ ] Grammar, wording, and semantics of tasks match the corresponding phase files.

### References

- [ ] Source Files, Destination Files, and Related Documentation sections are present and formatted correctly.
