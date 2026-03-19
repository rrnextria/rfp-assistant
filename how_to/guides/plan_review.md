# Planner-Reviewer Guide

## Roles & Rules

| Role | Agent | What They Do |
|------|-------|--------------|
| **Orchestrator** | Claude (you) | Run the loop, manage state, invoke reviewer |
| **Planner** | Claude (you) | Update the plan based on review findings |
| **Reviewer** | Codex (gpt-5.4) | Review the plan, issue structured verdict |

**Mandatory Rules:**
- You (Claude) are ALWAYS the orchestrator and planner
- You NEVER review your own work — Codex does that
- Plans MUST follow the templates exactly (`how_to/templates/simple_plan_template.md` or `master_plan_template.md`)
- The plan file MUST exist in `active_plans/` before starting

---

## Prerequisites

Before entering this loop, you must have:

1. A plan file at `active_plans/<slug>.md` (or `active_plans/<slug>/<slug>_master_plan.md` for complex plans)
2. The plan MUST follow the template structure exactly
3. The plan is a DRAFT — this loop will refine it until approved

---

## The Loop

### Step 1: Initialize

```bash
# Simple plan
./how_to/maistro plan active_plans/<slug>.md --init

# Complex plan — submit the master plan file; the CLI reviews phases first, then master
./how_to/maistro plan active_plans/<slug>/<slug>_master_plan.md --init
# Never pass --model — the default reviewer is pre-configured
```

### Step 1.5: Verify Plan

Before submitting for review, run verification:
- **Phase-stage review:** `./how_to/maistro plan-verify <phase-file> --no-cross-file`
- **Master-stage review:** `./how_to/maistro plan-verify <master-plan>`

Fix any errors before proceeding. Warnings can be addressed in later rounds.

### Step 2: Review Cycle

The orchestrator sends the plan to the Codex reviewer. The reviewer returns a structured verdict.

**If `APPROVED` (all counts = 0):** Done. If you are running a full pipeline, proceed to the next pipeline step (Code Execution). Do NOT manually edit plan checkmarks.

**If `FIXES_REQUIRED`:** Continue to Step 3.

### Step 3: Address Findings

1. Read the review file in `reviews/`
2. Address findings by severity (blockers first):
   - **B (Blocker):** Must fix. Plan cannot proceed.
   - **M (Major):** Significant issue. Needs correction.
   - **N (Minor):** Small improvement. Fix if easy.
   - **D (Decision):** Architectural question. Must acknowledge.
3. Update the plan file directly
4. Create a response artifact explaining what you changed
5. Re-run `plan-verify` after your edits to catch formatting regressions

### Step 4: Resume

```bash
./how_to/maistro plan active_plans/<slug>.md --resume
# Use --resume, NOT --init (which resets all review progress)
```

Go back to Step 2.

---

## Plan Types

### Simple Plans

A single `.md` file in `active_plans/`. Use for small features with 1-5 tasks.

```
active_plans/add_logging.md
```

Template: `how_to/templates/simple_plan_template.md`

### Complex Plans

A directory with a master plan and phase files. Use for multi-phase projects.

```
active_plans/my_feature/
├── my_feature_master_plan.md
└── phases/
    ├── phase_0_setup.md
    ├── phase_1_core.md
    └── phase_2_testing.md
```

Templates:
- `how_to/templates/master_plan_template.md`
- `how_to/templates/phase_plan_template.md`

Complex plans are reviewed phase-by-phase, then the master plan last.

---

## Approval Criteria

The reviewer writes an `ORCH_META` block with counts. Approval requires ALL of:
- `VERDICT: APPROVED`
- `BLOCKER: 0`
- `MAJOR: 0`
- `MINOR: 0`
- `DECISIONS: 0`

---

## CLI Options

| Option | Default | Purpose |
|--------|---------|---------|
| `--init` | off | Initialize fresh state (first run). Errors if state exists — use `--force` to overwrite |
| `--force` | off | Allow `--init` to overwrite existing state |
| `--resume` | off | Resume from last checkpoint |
| `--max-rounds N` | 5 | Maximum review rounds |
| `--model MODEL` | gpt-5.4 | **DO NOT pass this flag.** The default model is pre-configured with high reasoning effort. Only use if the user explicitly asks for a different model. |
| `--dry-run` | off | Show prompt without invoking reviewer |
| `--skip-preflight` | off | Skip format validation checks |
| `--slug OVERRIDE` | auto | Override derived slug |

---

## Checking Progress

```bash
./how_to/maistro status <slug>     # One-line summary
./how_to/maistro info <slug>       # Detailed progress
./how_to/maistro history <slug>    # Round-by-round history
```

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| Plan | `active_plans/<slug>.md` |
| Review | `reviews/<slug>_plan_review_round{R}.md` |
| Response | `reviews/<slug>_plan_update_round{R}.md` |
| State | `reviews/<slug>_orchestrator_state.json` |
