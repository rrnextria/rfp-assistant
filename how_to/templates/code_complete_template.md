# Code Complete Artifact Template

> **If your context was compacted, remember:**
> - Do NOT edit plan checkmarks — auto-synced on approval for complex (multi-phase) plans
> - Do NOT review your own code — submit to Codex via the CLI
> - Use `--resume` to continue after fixes, never `--init`
> - Never pass `--model` to any CLI command

This template shows the exact format required for code_complete artifacts to ensure they are greppable and automation-friendly.

---

## Artifact Naming

```
reviews/{plan_slug}_phase_{N}_task_{M}_code_complete_round{R}.md
```

Example: `reviews/repo_restructure_phase_1_task_2_code_complete_round1.md`

---

## Required Sections

### Header (copy and fill in)

```markdown
# Code Complete: {plan_slug} — Phase {N}, Task {M} (Round {R})

**Plan:** {plan_slug}
**Phase:** {N} ({phase_name})
**Task:** {M} ({task_name})
**Round:** {R}
**Date:** YYYY-MM-DD
**Coder:** Claude (Opus 4.6)
Task Type: {Implementation|Verification}

---

## Summary

{1-3 sentences describing what was implemented/verified}

---
```

### Task Type (REQUIRED)

The `Task Type:` line tells the lint script what kind of task this is:

| Type | When to Use | Lint Requirements |
|------|-------------|-------------------|
| `Implementation` | Task involves writing/modifying code | Requires `File:` lines and `~~~diff` blocks |
| `Verification` | Task only runs commands to verify things work | Skips `File:`/`~~~diff`, still requires `Test:` lines |

**Examples:**
- "Create config.yaml file" → `Task Type: Implementation`
- "Update imports in module" → `Task Type: Implementation`
- "Integration test monitoring CLI" → `Task Type: Verification`
- "Verify all acceptance gates pass" → `Task Type: Verification`

**Important:** The `Task Type:` line must be at the start of a line (no leading spaces) for the lint script to detect it.

### Files Modified Section

**CRITICAL:** Use exactly this format for each file. NO markdown prefix on "File:".

```markdown
## Files Modified

File: path/to/file.py

~~~diff
@@ -10,5 +10,8 @@
 existing line
 existing line
+added line 1
+added line 2
+added line 3
 existing line
 existing line
~~~

File: path/to/another_file.py

~~~diff
@@ -25,3 +25,5 @@
 context line
-removed line
+replacement line
 context line
~~~
```

**Format Rules:**
- `File:` must be at start of line (NO `###` prefix, NO markdown heading)
- Use `~~~diff` fences (NOT ` ```diff `)
- Include `@@ line,count @@` headers for context
- Use `+` for additions, `-` for removals, space for context

### Large File Exception (>10KB or binary files)

For large files where full diffs are impractical, use hash verification instead:

```markdown
File: path/to/large_file.json

**Large file ({size} bytes) — hash verification used instead of full diff:**

~~~
Source:      path/to/source_file.json
Destination: path/to/destination_file.json
SHA-256:     {hash} (both files)
Verified:    cmp -s source destination && echo "MATCH" → MATCH
~~~
```

This format is acceptable for:
- Files larger than 10KB
- Binary files
- Copy operations where byte-identical verification is the key evidence

### Test Results Section

```markdown
## Test Results

Test: pytest tests/unit/test_example.py -v

~~~
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.0.2
collected 5 items

tests/unit/test_example.py::test_function_one PASSED
tests/unit/test_example.py::test_function_two PASSED
tests/unit/test_example.py::test_edge_case PASSED

============================== 5 passed in 0.03s ===============================
~~~

**Result:** PASS
```

**Format Rules:**
- `Test:` must be at start of line
- Include the exact command run
- Use `~~~` fences for output (NOT ` ``` `)
- End with `**Result:** PASS` or `**Result:** FAIL`

### Task Completion Checklist

```markdown
## Task Completion Checklist

- [x] {subtask_number} {subtask_description}
- [x] {subtask_number} {subtask_description}
- [x] {subtask_number} {subtask_description}
```

### Referenced Files Section

```markdown
## Referenced Files

- `path/to/plan_file.md:{line_range}` — Task requirements
- `path/to/source_file.py` — Modified source
- `path/to/test_file.py` — Test file
```

---

## Complete Example

```markdown
# Code Complete: repo_restructure — Phase 1, Task 2 (Round 1)

**Plan:** repo_restructure
**Phase:** 1 (Configuration & Shell Scripts)
**Task:** 2 (Create training.yaml with operator-tunable defaults)
**Round:** 1
**Date:** 2026-01-07
**Coder:** Claude (Opus 4.6)
Task Type: Implementation

---

## Summary

Created `configs/training.yaml` with operator-tunable training parameters extracted from the `TrainConfig` dataclass in `src/pretrain_ddp/training/trainer.py`. Includes batch_size, learning_rate, warmup_steps, and other configurable knobs with documentation comments.

---

## Files Modified

File: configs/training.yaml

~~~diff
@@ -0,0 +1,25 @@
+# Training Configuration
+# NOTE: This file is not consumed by training code (reference/template only)
+# Values extracted from TrainConfig dataclass in src/pretrain_ddp/training/trainer.py
+
+# Batch and learning parameters
+batch_size: 32
+learning_rate: 0.0001
+warmup_steps: 1000
+max_steps: 100000
+
+# Data loading
+num_workers: 4
+prefetch_factor: 2
+
+# Training schedule
+gradient_accumulation_steps: 1
+eval_steps: 500
+save_steps: 1000
+val_split: 0.1
~~~

---

## Test Results

Test: test -f configs/training.yaml && echo "File exists"

~~~
File exists
~~~

**Result:** PASS

---

## Task Completion Checklist

- [x] 2.1 Read TrainConfig dataclass from `src/pretrain_ddp/training/trainer.py`
- [x] 2.2 Create `configs/training.yaml` with specified fields
- [x] 2.3 Add comments documenting each parameter and its default value
- [x] 2.4 Add header comment noting this is reference/template only (not consumed by training code)

---

## Referenced Files

- `active_plans/repo_restructure/phases/phase_1_config_and_scripts.md:170-181` — Task 2 requirements
- `src/pretrain_ddp/training/trainer.py` — Source for TrainConfig defaults
- `configs/training.yaml` — Created file
```

---

## Pre-Submission Checklist (MANDATORY)

Before creating the code_complete artifact, the Coder MUST verify each item:

```markdown
## Pre-Submission Checklist

- [ ] **Subtasks:** Re-read plan and verify ALL numbered subtasks (e.g., 4.1, 4.5, 4.8) are implemented
- [ ] **Extract vs Create:** If plan says "extract from X", verified code is copied from X (not newly created)
- [ ] **No Placeholders:** All SHA-256 hashes, line numbers, and outputs are real (run actual commands)
- [ ] **Runtime Dependencies:** For tests, identified ALL runtime deps (CUDA, FlashAttention, etc.) and added appropriate skip conditions
- [ ] **Imports Verified:** All imports in new/modified files are valid (run `python -c "import module"`)
- [ ] **Tests Pass Locally:** Ran `pytest path/to/tests` and verified results before submission
```

**Why This Matters:**
- Phase 2 data shows 70% of first-round blockers were catchable by this checklist
- Missing subtasks (Task 4.5) → caught by "Subtasks" check
- Wrong implementation approach (Task 3 collators) → caught by "Extract vs Create" check
- Placeholder hashes (Task 2) → caught by "No Placeholders" check
- Missing skip conditions (Task 5) → caught by "Runtime Dependencies" check

**Include this checklist in every code_complete artifact, filled in with [x] marks.**

---

## Greppable Patterns

These patterns allow automation to parse artifacts:

```bash
# Find all file change sections
grep -n "^File: " reviews/*_code_complete_*.md

# Find all diff blocks
grep -n "^~~~diff" reviews/*_code_complete_*.md

# Find all test invocations
grep -n "^Test: " reviews/*_code_complete_*.md
```

---

## Common Mistakes to Avoid

1. **Wrong:** `### File: path/to/file.py` — Don't use markdown heading
   **Right:** `File: path/to/file.py`

2. **Wrong:** ` ```diff ` — Don't use backticks
   **Right:** `~~~diff`

3. **Wrong:** `~~~python` for showing changes — Don't use language blocks for diffs
   **Right:** `~~~diff` with +/- prefixes

4. **Wrong:** Omitting `@@ line,count @@` headers
   **Right:** Include context headers for each hunk

5. **Wrong:** `### Test: command` — Don't use markdown heading
   **Right:** `Test: command`
