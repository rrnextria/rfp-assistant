# Coder-Reviewer Guide

## Roles & Rules

| Role | Agent | What They Do |
|------|-------|--------------|
| **Orchestrator** | Claude (you) | Run the loop, manage state, invoke reviewer |
| **Coder** | Claude (you) | Implement code, respond to review findings |
| **Reviewer** | Codex (gpt-5.4) | Review the code, issue structured verdict |

**Mandatory Rules:**
- You (Claude) are ALWAYS the orchestrator and coder
- You NEVER review your own work — Codex does that
- You MUST have an approved plan before entering this loop
- Code artifacts MUST follow the template (`how_to/templates/code_complete_template.md`)

---

## Prerequisites

Before entering this loop, you must have:

1. An **approved plan** at `active_plans/<slug>.md` (simple) or `active_plans/<slug>/<slug>_master_plan.md` (complex)
2. Know which **phase** and **task** you are implementing (from the plan)

## Slug Convention

The `<slug>` argument in all CLI commands **must match** the plan's directory or filename:

| Plan Type | Plan Location | Slug |
|-----------|--------------|------|
| Simple | `active_plans/add_logging.md` | `add_logging` |
| Complex | `active_plans/stream_lifecycle_hardening/` | `stream_lifecycle_hardening` |

The orchestrator uses the slug to locate plans, artifacts, and state files. If the slug doesn't match, the CLI won't find the plan.

---

## The Loop

### Step 1: Implement the Code

> **Reminders:**
> - Do NOT edit plan checkmarks — the system auto-syncs them on approval
> - Do NOT review your own code — proceed to creating the artifact and submitting to Codex
> - Do NOT create files outside the plan's scope
> - If resuming after fixes, use `--resume` (NOT `--init`, which resets state)
> - Never pass `--model` to any CLI command

1. Read the task from the approved plan
2. Write the code to implement the task
3. Create a `code_complete` artifact describing your implementation

The artifact must include:
- `File:` headings for each modified file
- `~~~diff` or `~~~python` fenced blocks showing changes
- `Test:` or `Verify:` lines describing validation steps
- Minimum 50 lines

Template: `how_to/templates/code_complete_template.md`

### Step 2: Initialize

```bash
./how_to/maistro code <slug> <phase> <task> --init
```

Example: `./how_to/maistro code my_feature 0 1 --init`

### Step 3: Review Cycle

The orchestrator sends the code artifact to the Codex reviewer. The reviewer returns a structured verdict.

**If `APPROVED` (all counts = 0):** Task done. Move immediately to the next task in the plan — do not wait for the human. Do NOT edit plan checkmarks (auto-synced). Only modify files within the plan's scope.

**If `FIXES_REQUIRED`:** Continue to Step 4.

### Step 4: Address Findings

1. Read the review file in `reviews/`
2. Address findings by severity (blockers first):
   - **B (Blocker):** Must fix. Code cannot proceed.
   - **M (Major):** Significant issue. Needs correction.
   - **N (Minor):** Small improvement. Fix if easy.
   - **D (Decision):** Architectural question. Must acknowledge.
3. Fix the code
4. Update the code_complete artifact or create a response artifact

### Step 5: Resume

```bash
./how_to/maistro code <slug> <phase> <task> --resume
```

Go back to Step 3.

---

## Preflight Checks

The orchestrator runs automated checks before sending to the reviewer:

1. **artifact_exists** — file exists and is non-empty
2. **code_file_headings** — contains `File:` headings
3. **code_diff_fences** — contains diff/code fenced blocks
4. **code_test_lines** — contains test/verify lines
5. **minimum_size** — at least 50 lines

Skip with `--skip-preflight` if needed.

---

## Multi-Task Execution

For each task in the plan:

1. Implement the task
2. Run the coder-reviewer loop until approved
3. Move to the next task

```bash
# Task 1
./how_to/maistro code my_feature 0 1 --init
# ... loop until approved ...

# Task 2
./how_to/maistro code my_feature 0 2 --init
# ... loop until approved ...
```

For complex (multi-phase) plans, the system automatically syncs plan checkmarks via the auto-trigger in `handle_approval()` after each task approval. For these plans, you do NOT need to manually update checkmarks in plan files. For simple (single-file) plans, update checkmarks manually after approval.

To check campaign progress at any time, run: `./how_to/maistro plan-status <slug>`

---

## Multi-Round Convergence

Most tasks converge in 1-3 rounds. If you reach 5+ rounds:

- Re-read the plan requirements carefully
- Check if the reviewer is flagging the same issues repeatedly
- Consider whether the task scope is too large
- Use `./how_to/maistro history <slug> <phase> <task>` to see the pattern

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
| `--skip-preflight` | off | Skip format validation |
| `--plan-slug STR` | same as slug | Override plan directory slug |

---

## Checking Progress

```bash
./how_to/maistro status <slug> <phase> <task>   # One-line summary
./how_to/maistro info <slug> <phase> <task>     # Detailed progress
./how_to/maistro history <slug> <phase> <task>  # Round-by-round history
```

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| Code Complete | `reviews/<slug>_phase_{P}_task_{T}_code_complete_round{R}.md` |
| Review | `reviews/<slug>_phase_{P}_task_{T}_code_review_round{R}.md` |
| Response | `reviews/<slug>_phase_{P}_task_{T}_coder_response_round{R}.md` |
| Task State | `reviews/<slug>_phase_{P}_task_{T}_state.json` |
