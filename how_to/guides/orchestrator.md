# Orchestrator System

> **New to Maistro?** Start with the [User Guide](workflow.md) for the full developer-facing walkthrough.

## Getting Started — Environment Bootstrap

**Every time you read this guide in a new repo, perform these checks first.**
Do not skip them. Do not just summarize. These are actions you must take.

### 1. Confirm git repository exists (HARD GATE)

Before doing anything else, check that you are inside a git repository:

```bash
git rev-parse --git-dir
```

- **If this succeeds:** Proceed to step 2.
- **If this fails:** **STOP and ask the human.** Do NOT run `git init`
  yourself. Ask them:
  > "This directory is not a git repository. Should I run `git init` to create
  > a new one, or do you need to clone an existing repo first?"

**Do not proceed past this step until a git repo exists.**

### 2. Ensure `how_to/` is deployed

If `how_to/orchestrator_v3/` does not exist in the current repo, copy the
entire `how_to/` folder from the human's OrchestratorV3 source. **Always copy
even if it already exists** — the human may have updated Maistro.

### 3. Create required directories

```bash
mkdir -p active_plans reviews research
touch reviews/.gitkeep
```

### 4. Verify the environment

```bash
./how_to/maistro doctor
```

This auto-creates the isolated venv at `how_to/.venv/` and installs
dependencies. No manual activation or pip install required. If `doctor` reports
issues, fix them before proceeding.

If you need explicit venv management:

```bash
./how_to/maistro --setup-env     # Create or verify the isolated venv
./how_to/maistro --reset-env     # Delete and recreate a broken venv
```

### 5. Update CLAUDE.md (if needed)

If the repo's `CLAUDE.md` doesn't have a Maistro section, read
`how_to/guides/claude_md_setup.md` and follow its instructions.

**If the human's ask was just to set up the environment** (e.g., "get ready for
Maistro", "set this up", "prepare for Maistro"), you are done after these steps
— report what you did. Otherwise, continue to the relevant mode below.

---

## What This Is

The `how_to/` folder contains a portable orchestration system that automates
structured review loops between two LLMs. It deploys identically into any repo.

**You (Claude) are the orchestrator.** The human gives you a short prompt. You
read this guide, understand the workflow, and drive the entire process — reading
plans, writing code, invoking the reviewer CLI, interpreting feedback, and
iterating until done. The human does not run CLI commands. You do.

---

## Fundamental Roles

| Role | Who | Rule |
|------|-----|------|
| **Orchestrator** | Claude (you) | Drive the loop, run CLI commands, manage state |
| **Coder / Planner** | Claude (you) | Write code or update plans based on review feedback |
| **Reviewer** | Codex (gpt-5.4) | Review your work via `orchestrator_v3` CLI (subprocess) |
| **Human** | The user | Gives you a prompt, watches, intervenes if needed |

**The human never runs the orchestrator CLI.** You do. That is the entire point
of this system — the human says "implement this plan" and you handle everything.

---

## Three Modes

### 1. Planner-Reviewer Loop

**When to use:** You have a draft plan that needs structured review before
implementation begins.

**What it does:**
- You submit a plan to Codex for review
- Codex returns a structured verdict (APPROVED or FIXES_REQUIRED with findings)
- You address the findings, update the plan, and resubmit
- Loop continues until Codex approves with zero findings

**What it does NOT do:**
- Write code — this is plan review only
- Implement anything — it refines the plan document
- Skip the review — every iteration goes through Codex

**Typical prompt from the human:**
> Read `how_to/guides/orchestrator.md` and review this plan:
> `active_plans/<slug>/<slug>_master_plan.md`

**Detailed guide:** [`how_to/guides/plan_review.md`](plan_review.md)

> **Key Rules:**
> - Do NOT review your own work — always submit to Codex
> - Use `--resume` after fixing findings, never `--init` (resets state)
> - Never pass `--model` — the default reviewer is pre-configured
> - Run `plan-verify` before submitting plans for review

---

### 2. Coder-Reviewer Loop

**When to use:** You have an approved plan and need to implement it task by task.

**What it does:**
- You read a task from the approved plan
- You write the code and create a code_complete artifact
- You submit it to Codex for review via the orchestrator CLI
- Codex returns a verdict; you fix issues and resubmit if needed
- Once approved, you move to the next task
- Repeat for every task across all phases

**What it does NOT do:**
- Review your own code — Codex always reviews
- Skip tasks — every task goes through the loop
- Work without a plan — you must have an approved plan first

**Typical prompt from the human:**
> Read `how_to/guides/orchestrator.md` and implement this plan:
> `active_plans/<slug>/<slug>_master_plan.md` using the coder-reviewer loop

**Detailed guide:** [`how_to/guides/code_review.md`](code_review.md)

> **Key Rules:**
> - Do NOT review your own code — always submit to Codex
> - Do NOT edit plan checkmarks — auto-synced on approval for complex (multi-phase) plans
> - Use `--resume` after fixes, never `--init`; never pass `--model`
> - Move to the next task automatically after approval — do not wait for the human

---

### 3. Research Mode (Dual-Model Deliberation)

**When to use:** The human has a complex question that benefits from two
independent perspectives converging toward an answer.

**What it does:**
- Two LLMs (Claude Opus + Codex) independently analyze a question
- They cross-review each other's work
- They iterate toward convergence with machine-readable agreement scores
- A final synthesis captures agreement, disagreement, and recommendations

**What it does NOT do:**
- Write or modify code in the repo
- Produce a plan — it produces a research synthesis
- Replace planning or code review — it is for open-ended questions only

**Typical prompt from the human:**
> Read `how_to/guides/orchestrator.md` and research this question:
> "What are the tradeoffs between approach X and approach Y?"

**Detailed guide:** [`how_to/guides/research.md`](research.md)

> **Key Rules:**
> - Never pass `--model` — the default reviewer is pre-configured
> - Do NOT write or modify repo code in research mode

---

## Do's and Don'ts

> **Note:** These rules are also stated inline at each mode description above.
> This section serves as a quick-reference index.

### Do

- **Read the detailed sub-guide** before starting any mode
- **Run all CLI commands yourself** — the human should not have to
- **Follow the templates exactly** — plan and code artifacts have required structure
- **Address every finding by severity** — blockers first, then major, minor, decisions
- **Use `--resume`** after fixing issues, not `--init` (which resets state)
- **Check progress** with `status`, `info`, `history` commands when resuming
- **Use `doctor`** to diagnose environment issues before debugging manually
- **Let the venv manage itself** — the orchestrator auto-creates `how_to/.venv/` on first run; never activate it manually
- **Move to the next task automatically** after approval — don't wait for the human
- **Report back to the human** at natural milestones (task approved, phase complete, errors)
- **Use the default reviewer model** — never pass `--model` unless the human explicitly asks you to change it. The default is always correct.
- **Run plan-verify before submitting plans for review** — the reviewer will reject malformed plans; catch errors early

### Don't

- **Don't review your own work** — that is what Codex is for
- **Don't tell the human to run commands** — you are the orchestrator
- **Don't skip the review loop** — every artifact goes through Codex
- **Don't start coding without an approved plan** (for coder-reviewer mode)
- **Don't use `--init` on resume** — it overwrites existing state (the CLI will error; use `--init --force` only if you truly need to reset)
- **Don't ignore preflight failures** — fix the artifact format first
- **Don't inflate or fabricate code artifacts** — the reviewer will catch it
- **Don't stop after one task** — continue through all tasks in the plan unless blocked
- **Don't change the reviewer model** — the default model is set by the system. Do not override it with `--model` unless the human explicitly tells you to use a different model
- **Don't manually edit plan checkmarks for complex (multi-phase) plans** — the system automatically syncs them after task approval. For simple plans, update checkmarks manually after approval. Use `plan-reconcile` if checkmarks are stale

---

## Deciding Which Mode to Use

| Situation | Mode | Guide |
|-----------|------|-------|
| "Review this plan" | Planner-Reviewer | [plan_review.md](plan_review.md) |
| "Implement this plan" | Coder-Reviewer | [code_review.md](code_review.md) |
| "Research this question" | Research | [research.md](research.md) |
| "Create a plan for X then implement it" | Planner-Reviewer, then Coder-Reviewer | Both guides |
| "What are the tradeoffs of X vs Y?" | Research | [research.md](research.md) |
| "Run the full pipeline for X" / "Get ready for Maistro" | Pipeline | [pipeline.md](pipeline.md) |

If the human says "implement" or "build" with a plan reference, use coder-reviewer.
If the human says "review" or "refine" a plan, use planner-reviewer.
If the human asks an open-ended question, use research.
If the human says "run the pipeline", "full pipeline", or "get ready for Maistro", use the pipeline guide.

---

## Quick Reference: CLI Commands

All commands use the prefix: `./how_to/maistro`

### Plan Review
```bash
# Start
./how_to/maistro plan active_plans/<slug>.md --init

# Resume after fixing findings
./how_to/maistro plan active_plans/<slug>.md --resume
```

### Code Review
```bash
# Start task (phase P, task T)
./how_to/maistro code <slug> <phase> <task> --init

# Resume after fixing findings
./how_to/maistro code <slug> <phase> <task> --resume
```

### Research
```bash
./how_to/maistro research "your question here" --slug <name>
```

### Environment & Setup
```bash
# Check environment health
./how_to/maistro doctor

# Create or verify the isolated venv
./how_to/maistro --setup-env

# Reset a broken venv
./how_to/maistro --reset-env
```

### Status & Progress
```bash
./how_to/maistro status <slug> [phase] [task]
./how_to/maistro info <slug> [phase] [task]
./how_to/maistro history <slug> [phase] [task]
```

### Plan Tool
```bash
# Verify plan syntax
./how_to/maistro plan-verify <path> [--no-cross-file] [--json]

# Progress summary
./how_to/maistro plan-status <slug> [--json]

# Show active task context
./how_to/maistro plan-show <slug> [--current|--recent]

# Sync approved task to plan checkmarks
./how_to/maistro plan-sync <slug> <phase> <task> [--dry-run]

# Regenerate master overview from phase files
./how_to/maistro plan-render-master <slug> [--dry-run]

# Detect and repair drift between state and plan
./how_to/maistro plan-reconcile <slug> [--apply] [--from-reviews]
```

> **IMPORTANT — Model and Reasoning Effort:**
> The default reviewer model (`gpt-5.4`) and reasoning effort (`high`) are
> pre-configured in the system. **Never pass `--model` to any command.**
> The only exception is if the human explicitly tells you to use a different
> model. If you see `--model` in the CLI help, ignore it — it exists only
> for the rare case when the human overrides it manually.

---

## File Layout

```
how_to/
├── guides/
│   ├── orchestrator.md          # This file — start here
│   ├── plan_review.md           # Planner-reviewer detailed guide
│   ├── code_review.md           # Coder-reviewer detailed guide
│   ├── research.md              # Research mode detailed guide
│   ├── plan_tool.md             # Plan tool command reference
│   ├── setup.md                 # Environment setup
│   ├── workflow.md              # General workflow guide
│   └── reference.md             # Reference documentation
├── orchestrator_v3/             # The orchestrator engine (Python)
│   ├── __main__.py              # Bootstrap gate (auto-creates venv)
│   ├── bootstrap.py             # Venv creation and management
│   ├── cli.py                   # CLI entry point (plan, code, research, doctor)
│   ├── config.py                # Settings and enums
│   ├── env_checks.py            # Environment validation (preflight + doctor)
│   ├── loop.py                  # Main review loop
│   ├── research.py              # Research mode engine
│   ├── reviewer.py              # Codex subprocess runner
│   ├── plan_tool.py             # Plan verification, status, sync
│   ├── state.py                 # Atomic state persistence
│   └── tests/                   # Test suite
├── templates/                   # Plan and code artifact templates
├── check_env.sh                 # Environment verification
└── create_env.sh                # Environment setup script
```

---

## For Repo Owners

To enable this system in a new repo, add this to the repo's `CLAUDE.md`:

```markdown
## Orchestrator System
When asked to implement a plan, review a plan, or research a question,
first read `how_to/guides/orchestrator.md` and follow its instructions.
```

That single line is all that's needed. The guides handle the rest.

---

## Manual Invocation (Advanced)

If you cannot use the launcher script, the orchestrator can also be invoked directly:

```bash
PYTHONPATH=how_to python3.12 -m orchestrator_v3 <command>
```

This requires manually setting PYTHONPATH and choosing the correct Python version.
