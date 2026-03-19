# Plan Tool Reference

Command reference for plan verification, progress tracking, and checkmark synchronization. All commands use the prefix: `./how_to/maistro`

---

## plan-verify

Validate plan structure, numbering, and cross-file consistency.

### Syntax
```bash
./how_to/maistro plan-verify <path> [--no-cross-file] [--json]
```
- `--no-cross-file` — skip master-vs-phase consistency checks (use for phase-stage reviews)
- `--json` — output results as JSON

### Example
```bash
./how_to/maistro plan-verify active_plans/plan_tool/phases/phase_1_core.md --no-cross-file
```

### Use Cases
- Run before submitting a plan for review to catch structural errors early
- Validate a master plan against its phase files after reconciliation

---

## plan-status

Show progress summary for a plan campaign.

### Syntax
```bash
./how_to/maistro plan-status <slug> [--json]
```

### Example
```bash
./how_to/maistro plan-status plan_tool
```

### Use Cases
- Check how many tasks are completed across all phases
- Get a quick overview of campaign progress at any time

---

## plan-show

Display the currently active task context from a plan.

### Syntax
```bash
./how_to/maistro plan-show <slug> [--current|--recent]
```
- `--current` — show the next uncompleted task (default)
- `--recent` — show the most recently completed task

### Example
```bash
./how_to/maistro plan-show plan_tool --current
```

### Use Cases
- Identify the next task to implement when resuming work
- Review what was last completed before picking up where you left off

---

## plan-sync

Sync a single approved task's checkmarks into plan files.

### Syntax
```bash
./how_to/maistro plan-sync <slug> <phase> <task> [--dry-run]
```
- `--dry-run` — show what would change without writing files

### Example
```bash
./how_to/maistro plan-sync plan_tool 1 3 --dry-run
```

### Use Cases
- Automatically called by `handle_approval()` after task approval — manual use is rarely needed
- Manually sync a task if the auto-trigger was skipped or failed

---

## plan-render-master

Regenerate the master plan's Phases Overview section from phase files.

### Syntax
```bash
./how_to/maistro plan-render-master <slug> [--dry-run]
```
- `--dry-run` — show the rendered output without writing the master file

### Example
```bash
./how_to/maistro plan-render-master plan_tool
```

### Use Cases
- Automatically called after `plan-sync` updates phase checkmarks — manual use is rarely needed
- Regenerate the master overview after manual edits to phase files

---

## plan-reconcile

Detect and repair drift between orchestrator state and plan checkmarks.

### Syntax
```bash
./how_to/maistro plan-reconcile <slug> [--apply] [--from-reviews]
```
- `--apply` — write corrections to plan files (without this flag, only reports drift)
- `--from-reviews` — scan review state files to determine which tasks were approved

### Example
```bash
./how_to/maistro plan-reconcile plan_tool --apply --from-reviews
```

### Use Cases
- Repair stale checkmarks when auto-trigger was interrupted or skipped
- Audit plan files for consistency after manual edits

---

## Auto-Trigger

`plan-sync` and `plan-render-master` are called automatically after each task approval in the coder-reviewer loop via `handle_approval()`. You do not need to run them manually during normal workflow. Manual usage is needed only for repair (`plan-reconcile --apply`) or ad-hoc queries (`plan-status`, `plan-show`).

---

## Troubleshooting

**Checkmarks stale after approval** — Run `./how_to/maistro plan-reconcile <slug> --apply --from-reviews` to detect and fix drift.

**Verification errors before review** — Fix the reported issues in the plan file, then re-run `plan-verify` until zero errors.

**Master overview out of date** — Run `./how_to/maistro plan-render-master <slug>` to regenerate the Phases Overview from phase files.
