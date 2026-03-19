# Full Pipeline Guide

Run the entire orchestrator pipeline — research, plan, review, execute, commit —
in a single session. This guide is for Claude, not for humans.

---

## When to Use

The human says something like:

- "Run the full pipeline for this ask: ..."
- "Run the pipeline: ..."
- "Full pipeline: ..."
- "Get ready for Maistro" / "Set up for Maistro"
- Any request that involves reading this guide and preparing the repo

Or provides an ask that explicitly references research → plan → review → execute.

### Starting Mid-Pipeline

The pipeline supports starting from any step. The human may have completed
earlier steps in a previous conversation (e.g., research and draft plan done
interactively, now ready for plan review). Triggers:

- "Run the pipeline from step 3: `active_plans/<slug>/...`"
- "Start plan review for `<slug>`"
- "Start from plan review, then code, then commit: `<path-to-master-plan>`"
- "Resume pipeline at step 4 for `<slug>`"

When starting mid-pipeline:

1. **Still do Step 0** (environment bootstrap) — always required.
2. **Create the meta plan** — mark prior steps as `done_prior` in the status
   table. Copy any context the human provides (plan path, research path, key
   decisions) into the Key Findings and Decisions sections.
3. **Verify prior step outputs exist on disk** — read them to confirm they are
   valid before proceeding. For example, if starting at Step 3, verify the
   draft plan exists and passes `plan-verify`.
4. **Begin at the specified step** — follow the pipeline from that point
   forward through all remaining steps (unless the human says otherwise).

---

## Step 0: Environment Bootstrap (ALWAYS do this first)

**Every time you read this guide, you MUST perform these checks before doing
anything else.** Do not skip this section. Do not just summarize what you read.
These are actions you must take.

### 0a. Confirm git repository exists (HARD GATE)

Before doing anything else, check that the current working directory is inside
a git repository:

```bash
git rev-parse --git-dir
```

- **If this succeeds:** Proceed to step 0b.
- **If this fails:** **STOP and ask the human.** Do NOT run `git init`
  yourself. The human may need to clone an existing remote, or may be in the
  wrong directory. Ask them:
  > "This directory is not a git repository. Should I run `git init` to create
  > a new one, or do you need to clone an existing repo first?"

**Do not proceed past this step until a git repo exists.** Everything below
depends on it — `.gitignore` edits, doctor checks, and the pipeline itself all
require a working git repository.

### 0b. Deploy `how_to/` into the target repo

Check whether `how_to/orchestrator_v3/` exists in the **current working
directory**. If it does not — or if the human is working in a different repo
from where Maistro source lives — copy the entire `how_to/` folder:

```bash
# Copy from source (adjust source path to wherever the human's OrchestratorV3 lives)
cp -r /path/to/OrchestratorV3/how_to/ /path/to/target/repo/how_to/
```

**Always copy, even if `how_to/` already exists in the target.** The human may
have updated Maistro, and running an older version causes silent failures.

### 0c. Create required directories

```bash
mkdir -p active_plans reviews research
```

### 0d. Update `.gitignore`

Ensure the repo's `.gitignore` excludes review artifacts:

```
### Maistro Orchestrator ###
reviews/*.md
reviews/*.json
reviews/*.log
!reviews/.gitkeep
```

Create `reviews/.gitkeep` if it doesn't exist:

```bash
touch reviews/.gitkeep
```

### 0e. Verify the environment

```bash
./how_to/maistro doctor
```

This auto-creates the venv at `how_to/.venv/` and installs dependencies. If
`doctor` reports issues, fix them before proceeding.

### 0f. Update CLAUDE.md (if needed)

If the repo doesn't already have a Maistro section in its `CLAUDE.md`, read
`how_to/guides/claude_md_setup.md` and follow its instructions.

**Only after all of Step 0 is complete should you proceed.** If the human's ask
was just to set up the environment (e.g., "get ready for Maistro", "set this up"),
you are done — report what you did. If the ask includes a pipeline task, continue
to the meta plan and pipeline steps below.

---

## Before You Start a Pipeline: Create the Meta Plan

**This is mandatory.** Before doing any work, you MUST:

1. Read the meta plan template at `how_to/templates/pipeline_meta_plan_template.md`
2. Fill it in with the user's ask, a derived slug, and defaults
3. Save it to your internal planning tool (EnterPlanMode / plan tasks)

The meta plan is what keeps you on track when your context gets compacted.
Without it, you will lose your place in the pipeline. **Update the meta plan
status after completing each step.**

### Deriving the Slug

Create an appropriate pipeline slug from the ask. Use lowercase, underscores,
2-4 words that capture the essence. Examples:

- "Make all ports dynamic" → `dynamic_ports`
- "Add user authentication" → `user_auth`
- "Optimize Docker builds" → `docker_optimization`

---

## The Pipeline

```
Step 1: Research         → research/<slug>/synthesis.md
Step 2: Draft Plan       → active_plans/<slug>/
Step 3: Plan Review Loop → approved plan
Step 4: Code Execution   → working code, all tasks approved
Step 5: Validate & Commit → build passes, tests pass, docs updated, committed
```

### Step 1: Research

Run the orchestrator in research mode:

```bash
./how_to/maistro research "<research question derived from the ask>" --slug <slug> --max-rounds 10
```

- Derive a focused research question from the user's ask
- Default: 10 rounds (override if the user specifies differently)
- Read the detailed guide first: `how_to/guides/research.md`

**Output:** `research/<slug>/synthesis.md`

**Gate:** After research completes, read the synthesis. If there are unresolved
questions or critical ambiguities that would block plan creation, STOP and ask
the user for clarification. If the synthesis is clear and actionable, proceed
to Step 2.

**Update meta plan:** Mark Step 1 complete, note any key findings.

### Step 2: Draft Plan

Create a multi-phase plan from the research synthesis:

1. Read the research synthesis at `research/<slug>/synthesis.md`
2. Read the master plan template at `how_to/templates/master_plan_template.md`
3. Read the phase plan template at `how_to/templates/phase_plan_template.md`
4. Create the plan directory and files in `active_plans/<slug>/`
5. Include unit and integration tests in appropriate tasks
6. The **last task of the last phase** must always be: build verification,
   test suite, documentation updates, and commit

Structure:
```
active_plans/<slug>/
├── <slug>_master_plan.md
└── phases/
    ├── phase_0_<name>.md
    ├── phase_1_<name>.md
    └── ...
```

Follow the master plan mirroring rules exactly — task titles in the master plan
must be copied verbatim from phase files.

**No gate here.** Once the draft plan is complete, proceed directly to Step 3.

**Update meta plan:** Mark Step 2 complete.

### Step 3: Plan Review Loop

Run the orchestrator in planner-reviewer mode:

```bash
./how_to/maistro plan active_plans/<slug>/<slug>_master_plan.md --init --max-rounds 30
```

- Default: up to 30 rounds (override if the user specifies differently)
- Read the detailed guide first: `how_to/guides/plan_review.md`
- Address all findings from the reviewer, update the plan, resume with `--resume`
- Continue until `VERDICT: APPROVED` with all counts at zero

> **Critical Rules for this step:**
> - Never pass `--model` to any command — the default reviewer is pre-configured
> - Use `--resume` after fixing findings, never `--init` (which resets review state)
> - Do NOT manually edit plan checkmarks — `plan-sync` handles this automatically
> - Do NOT review your own work — always submit to Codex

**Once the plan is approved with zero findings, proceed directly to Step 4.**

**Update meta plan:** Mark Step 3 complete.

### Step 4: Code Execution

Run the orchestrator in coder-reviewer mode, task by task:

```bash
./how_to/maistro code <slug> <phase> <task> --init
```

- Read the detailed guide first: `how_to/guides/code_review.md`
- Work through every task in every phase sequentially
- After each task is approved, move to the next automatically
- If a task gets fixes requested, address findings and `--resume`

> **Critical Rules for this step:**
> - Never pass `--model` to any command — the default reviewer is pre-configured
> - Use `--resume` after fixing findings, never `--init` (which resets review state)
> - Do NOT manually edit plan checkmarks — `plan-sync` handles this automatically
> - Do NOT review your own code or create files outside the plan's scope — submit to Codex

**Once all tasks in all phases are approved, proceed to Step 5.**

**Update meta plan:** Update current phase/task as you progress.

### Step 5: Validate & Commit

Before committing, verify everything works:

1. **Build:** Run the project's build command and confirm it succeeds
2. **Tests:** Run all test suites and confirm they pass
3. **Docs:** Ensure all documentation is updated to reflect changes
4. **Commit:** Use `./commit.sh` (NEVER raw `git add`/`git commit`/`git push`):
   ```bash
   ./commit.sh -m 'Subject line' -m '' -m 'Body line 1' -m 'Body line 2'
   ```
   `commit.sh` auto-generates `project_tree_structure.md`, stages all changes,
   commits, and pushes. Do NOT include "anthropic" or "claude" in the commit
   message — the script rejects these strings.

**Update meta plan:** Mark Step 5 complete. Pipeline finished.

---

## Defaults

| Parameter | Default | Override |
|-----------|---------|----------|
| Research rounds | 10 | User specifies in ask |
| Plan review rounds | 30 | User specifies in ask |
| Plan type | Complex (master + phases) | Use simple if < 6 tasks |

---

## Context Compaction Survival

When your context gets compacted mid-pipeline:

1. **Re-read your meta plan** at `active_plans/<slug>/meta_plan.md` — it tells
   you exactly where you are, what step you are on, and what decisions were made
2. **Re-read the guide for your current step** — e.g., if you are on Step 3,
   re-read `how_to/guides/plan_review.md`
3. **Read the relevant artifacts on disk** — research synthesis, plan files,
   review state files
4. **Resume from the current step** — do not restart from the beginning
5. **Check orchestrator state** if mid-loop:
   ```bash
   ./how_to/maistro status <slug>
   ```

The meta plan is your single source of truth for pipeline progress. If it says
you are on Step 4, Phase 2, Task 3 — that is where you resume. Do not re-read
earlier steps or re-do completed work.

---

## Error Recovery

- **Research fails to converge:** Report the synthesis as-is, proceed to draft
  plan with caveats noted
- **Plan review stuck in a loop:** After 30 rounds, stop and report to user
- **Code review stuck:** After 10 rounds on a single task, stop and report
- **Build fails at Step 5:** Fix the issues, re-run tests, then commit
- **Unresolvable blocker at any step:** Stop and ask the user

## Related Documentation

- `docs/architecture.md` — System architecture and data flow
- `docs/tools.md` — Full CLI reference for `finding-diff`, `spin-watch`, and other tools
