# Pipeline Meta Plan: {slug}

> **On context compaction, re-read this file and the guide for your current step.**

## Ask
{paste or summarize the user's original ask here}

## Slug
`{slug}`

## Plan Path
`{path to master plan if it exists, e.g. active_plans/<slug>/<slug>_master_plan.md}`

## Start Step
{step number to begin at — default 1, set higher if prior steps were done in a previous session}

## Status

| Step | Status | Notes |
|------|--------|-------|
| 1. Research | not_started | |
| 2. Draft Plan | not_started | |
| 3. Plan Review | not_started | |
| 4. Code Execution | not_started | |
| 5. Validate & Commit | not_started | |

Valid statuses: `not_started`, `done_prior`, `in_progress`, `done`, `blocked`

- `done_prior` = completed in a previous conversation (verify artifacts exist before proceeding)

## Current Position
Step: {start step number}
Phase: —
Task: —

## Rules (survive context compaction)
- Never pass `--model` to any CLI command
- Never manually edit plan checkmarks — auto-synced on approval
- Never review your own work — always submit to Codex
- Use `--resume` to continue loops, never `--init`
- Read the relevant guide before each step
- After completing each step, update this meta plan before proceeding

## Key Findings
{update as you progress — capture anything you'll need after context compaction}

## Decisions
{record any user decisions or clarifications that affect later steps}
