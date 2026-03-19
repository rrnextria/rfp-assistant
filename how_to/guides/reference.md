# Reference

## ORCH_META Protocol

Machine-readable verdict block placed in the first 50 lines of review `.md` files.

### Format

```
<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 9
-->
```

### Keys

| Key | Required | Values | Description |
|-----|----------|--------|-------------|
| `VERDICT` | Yes | `APPROVED`, `FIXES_REQUIRED` | Overall verdict |
| `BLOCKER` | Yes | integer | Must-fix issues |
| `MAJOR` | Yes | integer | Significant issues |
| `MINOR` | Yes | integer | Small improvements |
| `DECISIONS` | Yes | integer | Open architectural questions |
| `VERIFIED` | No | integer | Items reviewed and validated |

### Approval Logic

Approval requires ALL of:
- `VERDICT: APPROVED`
- `BLOCKER: 0`
- `MAJOR: 0`
- `MINOR: 0`
- `DECISIONS: 0`

**Fail-closed:** Missing block, malformed block, or missing file = not approved.

## Finding ID Conventions

Findings use severity-prefixed IDs for tracking across rounds.

| Prefix | Severity | Action Required |
|--------|----------|-----------------|
| `B` | Blocker | Must fix before approval |
| `M` | Major | Needs correction |
| `N` | Minor | Fix if easy |
| `D` | Decision | Must acknowledge |

Examples: `B1: Missing error handling`, `M3: Test coverage gap`, `D1: Redis vs in-memory cache`

IDs are stable across rounds. If B1 is fixed, the reviewer marks it as verified. If not, it persists.

## Artifact Naming

### Plan Mode (Simple)

```
reviews/{slug}_plan_review_round{R}.md
reviews/{slug}_plan_update_round{R}.md
```

### Plan Mode (Complex)

```
reviews/{slug}_phase_{P}_{label}_review_round{R}.md
reviews/{slug}_{slug}_master_plan_review_round{R}.md
```

### Code Mode

```
reviews/{slug}_phase_{P}_task_{T}_code_complete_round{R}.md
reviews/{slug}_phase_{P}_task_{T}_code_review_round{R}.md
reviews/{slug}_phase_{P}_task_{T}_coder_response_round{R}.md
```

### State Files

```
reviews/{slug}_orchestrator_state.json
reviews/{slug}_orchestrator_state.json.bak
reviews/{slug}_phase_{P}_task_{T}_state.json
```

## CLI Command Reference

All commands are invoked via `./how_to/maistro <command> [args] [options]`.

### plan

```
./how_to/maistro plan <plan_file> [options]
```

Run the plan review loop.

| Option | Default | Description |
|--------|---------|-------------|
| `--resume` | off | Resume from last checkpoint |
| `--dry-run` | off | Print prompt without invoking reviewer |
| `--init` | off | Initialize fresh state |
| `--max-rounds N` | 5 | Maximum review rounds |
| `--model MODEL` | gpt-5.4 | **Do not pass.** Pre-configured with high reasoning. Only override if user asks. |
| `--timeout SEC` | 1800 | Reviewer wall-clock timeout |
| `--idle-timeout SEC` | 600 | Kill reviewer after N seconds idle |
| `--skip-preflight` | off | Skip format validation |
| `--slug OVERRIDE` | auto | Override derived slug |
| `--mock-reviewer PATH` | none | Directory with mock review files |

### code

```
./how_to/maistro code <slug> <phase> <task> [options]
```

Run the code review loop.

| Option | Default | Description |
|--------|---------|-------------|
| `--resume` | off | Resume from last checkpoint |
| `--dry-run` | off | Print prompt without invoking reviewer |
| `--init` | off | Initialize fresh state |
| `--max-rounds N` | 5 | Maximum review rounds |
| `--model MODEL` | gpt-5.4 | **Do not pass.** Pre-configured with high reasoning. Only override if user asks. |
| `--timeout SEC` | 1800 | Reviewer wall-clock timeout |
| `--idle-timeout SEC` | 600 | Kill reviewer after N seconds idle |
| `--skip-preflight` | off | Skip format validation |
| `--plan-slug STR` | same as slug | Override plan directory slug |
| `--mock-reviewer PATH` | none | Directory with mock review files |

### status

```
./how_to/maistro status <slug> [phase] [task]
```

One-line status summary. With phase/task args, shows per-task detail.

### info

```
./how_to/maistro info <slug> [phase] [task]
```

Detailed progress with round counts and current state.

### history

```
./how_to/maistro history <slug> [phase] [task]
```

Round-by-round review history with verdicts and finding counts.

### validate

```
./how_to/maistro validate <slug>
```

Check state file integrity: plan file exists, stage values valid, round numbers consistent.

### postmortem

```
./how_to/maistro postmortem <slug> [options]
```

Generate campaign postmortem report.

| Option | Default | Description |
|--------|---------|-------------|
| `--skip-reflection` | off | Metrics only, skip LLM reflection |
| `--dry-run` | off | List artifacts without generating report |
| `--model MODEL` | gpt-5.4 | **Do not pass.** Pre-configured with high reasoning. Only override if user asks. |
| `--timeout SEC` | 1800 | Reflection wall-clock timeout |
| `--idle-timeout SEC` | 600 | Kill after N seconds idle |

## Postmortem Metrics

The postmortem command calculates:

- **Total tasks/stages reviewed**
- **Total rounds across all tasks**
- **First-round approval rate** — percentage of tasks approved on first review
- **Average rounds to approval** — mean rounds needed for approval
- **Finding totals** — blockers, majors, minors raised across all rounds
- **Finding resolution rate** — verified items / total findings
- **Per-mode averages** — separate stats for plan vs code reviews

## Further Documentation

For details on the evolution telemetry system, see:

- `docs/architecture.md` — Five-stage loop, repo layout, and data flow diagrams
- `docs/telemetry_schema.md` — SQLite table definitions and example queries
- `docs/evolution_log.md` — Evolution event log format and finding lifecycle
- `docs/tools.md` — Full CLI reference for both orchestrator and evolution commands
