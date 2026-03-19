# Round Summaries Template

This template shows the format for round summary files that track the history of a single task's review cycles.

---

## File Location

```
reviews/{plan_slug}_phase_{N}_task_{M}_round_summaries.md
```

Example: `reviews/repo_restructure_phase_2_task_3_round_summaries.md`

---

## Template

```markdown
# Round Summaries: {plan_slug} — Phase {N}, Task {M}

## Round 1 — YYYY-MM-DD HH:MM

**Coder Artifact:** {plan_slug}_phase_{N}_task_{M}_code_complete_round1.md
**Review Artifact:** {plan_slug}_phase_{N}_task_{M}_code_review_round1.md
**Result:** {Approved | Needs fixes}
**Counts:** 🚫 Blocker X  ⚠️ Major Y  🛈 Minor Z  ❗ Decisions D  ✅ Verified V
**Summary:** {1-2 sentence summary of what happened}

---

## Round 2 — YYYY-MM-DD HH:MM

**Coder Artifact:** {plan_slug}_phase_{N}_task_{M}_coder_response_round1.md
**Review Artifact:** {plan_slug}_phase_{N}_task_{M}_code_review_round2.md
**Result:** {Approved | Needs fixes}
**Counts:** 🚫 Blocker X  ⚠️ Major Y  🛈 Minor Z  ❗ Decisions D  ✅ Verified V
**Summary:** {1-2 sentence summary of what happened}

---
```

---

## Example

```markdown
# Round Summaries: repo_restructure — Phase 2, Task 3

## Round 1 — 2026-01-08 10:15

**Coder Artifact:** repo_restructure_phase_2_task_3_code_complete_round1.md
**Review Artifact:** repo_restructure_phase_2_task_3_code_review_round1.md
**Result:** Needs fixes
**Counts:** 🚫 Blocker 1  ⚠️ Major 2  🛈 Minor 0  ❗ Decisions 0  ✅ Verified 5
**Summary:** Blocker: Missing subtask 3.5 (collator extraction). Major: Test skip condition incomplete for FlashAttention.

---

## Round 2 — 2026-01-08 10:45

**Coder Artifact:** repo_restructure_phase_2_task_3_coder_response_round1.md
**Review Artifact:** repo_restructure_phase_2_task_3_code_review_round2.md
**Result:** Needs fixes
**Counts:** 🚫 Blocker 0  ⚠️ Major 1  🛈 Minor 1  ❗ Decisions 0  ✅ Verified 7
**Summary:** Major issue fixed. New major: Import statement ordering. Minor: Docstring formatting.

---

## Round 3 — 2026-01-08 11:10

**Coder Artifact:** repo_restructure_phase_2_task_3_coder_response_round2.md
**Review Artifact:** repo_restructure_phase_2_task_3_code_review_round3.md
**Result:** Approved
**Counts:** 🚫 Blocker 0  ⚠️ Major 0  🛈 Minor 0  ❗ Decisions 0  ✅ Verified 9
**Summary:** All issues addressed. Implementation complete and verified.

---
```

---

## Greppable Patterns

```bash
# Find all round headers
grep -n "^## Round" reviews/*_round_summaries.md

# Find all results
grep -n "^\*\*Result:\*\*" reviews/*_round_summaries.md

# Find all blockers > 0
grep -n "Blocker [1-9]" reviews/*_round_summaries.md

# Count rounds per task
grep -c "^## Round" reviews/repo_restructure_phase_2_task_3_round_summaries.md
```

---

## Purpose

1. **Quick context** — Orchestrator reads this instead of full artifacts
2. **History tracking** — See how many rounds and what issues occurred
3. **Pattern detection** — Identify recurring issues across tasks
4. **Metrics** — Calculate average rounds, first-round pass rate, etc.

---

## Notes

- Each round is appended as it completes
- Never modify past entries
- Keep summaries brief (1-2 sentences max)
- Always include the Counts line for consistency
