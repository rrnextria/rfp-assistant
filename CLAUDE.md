# RFP Assistant — Claude Guide

## Project Overview

Model-agnostic RFP assistant that retrieves permission-scoped enterprise content and generates compliant, citation-backed answers. See `spec.md` for the full engineering specification.

## Orchestrator System

When asked to implement a plan, review a plan, or research a question, first read `how_to/guides/orchestrator.md` and follow its instructions.

## Maistro Orchestrator

The `how_to/` folder contains a portable orchestration system ("Maistro") that automates structured review loops between two LLMs. All commands go through the launcher:

```bash
./how_to/maistro <command>
```

No manual venv activation or PYTHONPATH needed — the launcher handles everything.

### Environment

```bash
./how_to/maistro doctor          # Verify all prerequisites
./how_to/maistro --setup-env     # Create/verify the isolated venv
./how_to/maistro --reset-env     # Delete and recreate the venv
```

### Key Rules

- Do NOT manually edit plan checkmarks for complex (multi-phase) plans — the system syncs them automatically
- Never pass `--model` to any CLI command — the default reviewer is pre-configured
- Use `--resume` after fixing review findings, never `--init` (which resets state)

### Usage Modes

#### Stepwise Mode (recommended for most work)

Run one mode at a time. **Re-read the relevant guide at the start of each new session** — context from prior sessions is not preserved.

#### Full Pipeline Mode

For end-to-end execution (research → plan → review → code → commit) in a single session, follow `how_to/guides/pipeline.md`.

### The Pipeline

Every non-trivial change follows this pipeline. In stepwise mode, **restart Claude between steps.** In pipeline mode, run all steps in a single session.

#### Step 1: Research (Optional)

Use when you need two LLMs to independently analyze a question before committing to an approach.

**Prompt:**
> Read `how_to/guides/orchestrator.md` and research this question:
> "Your question here"

Produces: `research/<slug>/synthesis.md`

**Detailed guide:** `how_to/guides/research.md`

#### Step 2: Draft the Plan

**Prompt (complex, multi-phase):**
> Read `how_to/templates/master_plan_template.md` and create a plan for [describe what you want].
> Save to `active_plans/<slug>/<slug>_master_plan.md`.

**Prompt (simple, 1-5 tasks):**
> Read `how_to/templates/simple_plan_template.md` and create a plan for [describe what you want].
> Save to `active_plans/<slug>.md`.

#### Step 3: Plan Review Loop

Submit the plan for structured review by Codex. Iterates until approved.

**Prompt:**
> Read `how_to/guides/orchestrator.md` and review this plan:
> `active_plans/<slug>/<slug>_master_plan.md`

**Detailed guide:** `how_to/guides/plan_review.md`

#### Step 4: Code Review Loop

Implement the approved plan task-by-task with Codex reviewing each task.

**Prompt:**
> Read `how_to/guides/orchestrator.md` and implement this plan:
> `active_plans/<slug>/<slug>_master_plan.md`

**Detailed guide:** `how_to/guides/code_review.md`

### Plan Management

```bash
./how_to/maistro plan-verify <plan-path>    # Validate plan syntax
./how_to/maistro plan-status <slug>         # Campaign progress summary
./how_to/maistro plan-show <slug>           # Task details
./how_to/maistro plan-sync <slug> ...       # Sync approval to checkmarks
./how_to/maistro plan-reconcile <slug>      # Detect/repair drift
```

### Roles

| Role | Who | What |
|------|-----|------|
| **Orchestrator + Coder** | Claude (you) | Drive the loop, write code, run CLI |
| **Reviewer** | Codex (gpt-5.4) | Reviews via `./how_to/maistro` subprocess |
| **Human** | The user | Gives prompts, watches, intervenes if needed |

The human never runs the orchestrator CLI. You do. Never change the reviewer model unless the human explicitly asks.

## Commit Workflow

Use the commit helper for all commits — it auto-generates `project_tree_structure.md` and pushes:

```bash
./how_to/commit.sh -m "your message"
```

Do not mention Claude or Anthropic in commit messages (enforced by the script).
