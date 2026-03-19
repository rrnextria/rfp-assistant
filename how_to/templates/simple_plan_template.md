<!-- New on 2025-11-26 -->
# Simple Plan Template

Purpose: Single-file plan for small, tightly scoped work. This template is optimized for LLMs and tooling: it is highly structured, greppable, and strict about numbering and content placement.

---

## LLM Navigation & Grep Guide (For LLMs Only)

This section exists ONLY to help LLMs and tools navigate the plan after it has been generated.  
Humans may ignore it. LLMs MUST NOT change the patterns below.

### Section Headings (Top-Level)

The following headings are expected and should be unique:

- `## Objective`
- `## Current vs Desired`
- `## States & Modes` (optional)
- `## Scope`
- `## Policies & Contracts`
- `## Tasks`
- `## Acceptance Criteria`
- `## Risks & Mitigations`
- `## Validation`
- `## Artifacts Created`
- `## Interfaces & Dependencies`
- `## References`
- `## Decision Log` (optional)
- `## Reviewer Checklist`

Example greps (POSIX):

- Objective:
  - `grep -n "^## Objective$" <plan>`
- Current vs Desired:
  - `grep -n "^## Current vs Desired$" <plan>`
- Tasks:
  - `grep -n "^## Tasks$" <plan>`

### Tasks, Subtasks, and Leaf Steps

LLMs MUST emit tasks, subtasks, and leaf steps using these exact structural patterns.

- **Top-level tasks** (IDs: 1, 2, 3, ...):

  ```markdown
  ### [ ] 1 Task name...
  ```

  Grep pattern:

  ```bash
  grep -nE "^### \[ \] [0-9]+ " <plan>
  ```

- **Subtasks** (IDs: 1.1, 1.2, 2.1, ...):

  ```markdown
  #### [ ] 1.1 Subtask name...
  ```

  Grep pattern:

  ```bash
  grep -nE "^#### \[ \] [0-9]+\.[0-9]+ " <plan>
  ```

- **Leaf steps** (IDs: 1.1.1, 1.2.3, etc.):

  ```markdown
    - [ ] 1.1.1 Step description...
  ```

  (Two leading spaces, then `- [ ]`.)

  Grep pattern:

  ```bash
  grep -nE "^  - \[ \] [0-9]+\.[0-9]+\.[0-9]+ " <plan>
  ```

- **Specific item by ID** (examples):

  - Task 3:  
    `grep -n "^### \[ \] 3 " <plan>`
  - Subtask 3.2:  
    `grep -n "^#### \[ \] 3\.2 " <plan>`
  - Leaf step 3.2.7:  
    `grep -n "^  - \[ \] 3\.2\.7 " <plan>`

LLM RULES:

- NEVER use `### [ ]` for anything except top-level tasks.
- NEVER use `#### [ ]` for anything except subtasks.
- NEVER use numbered IDs in plain checklist items outside Tasks.
- ALWAYS use exactly two spaces before `- [ ]` for leaf steps.
- NEVER emit levels deeper than 1.1.1 (e.g., 1.1.1.1 is forbidden).

---

## Objective

State the single goal and success criteria (1–3 sentences).

- Describe **what** this plan will achieve, not how.
- Mention how success will be recognized at a high level (e.g., “dashboard launches in IDLE immediately after device selection, no text menu”).

---

## Current vs Desired

This section describes the current behavior and structure, then the desired future state.  
LLMs MUST keep analysis (here) separate from execution (in Tasks).

### Current Behavior

Describe the current behavior as experienced by the user or system, step-by-step.

- Use bullet points.
- Include the main flow(s) relevant to this plan (e.g., “device selection → text menu → dashboard only when Start chosen”).
- Avoid speculation or planned changes here; only describe what happens today.

### Current Structure

Describe the key technical structure related to this plan.

- Key files and modules, with paths (e.g., `tools/dashboard.py`).
- Key classes/functions/methods/endpoints.
- Approximate size or complexity if relevant (e.g., “1451-line file containing DashboardState enum and LiveDashboard class”).
- Entry points (e.g., CLI flags, scripts, commands).

### Baseline Snapshot

Provide a concise snapshot of the current state of the ecosystem around this work.

- Existing packages or directories.
- Known importers or call sites.
- Related subsystems that rely on this behavior.
- Any critical integrations.

### Invariants (MUST Remain True)

List conditions that MUST NOT be broken by this plan.

- Examples:
  - “Console mode behavior remains unchanged.”
  - “Existing JSON output format stays compatible.”
  - “All existing imports for LiveDashboard continue to work.”
- Invariants typically describe compatibility, stability, and guarantees for other systems.

### Desired Behavior

Describe the target behavior from the user/system perspective.

- Use bullet points.
- Mirror the structure of Current Behavior but in the new desired flow.
- Focus on visible behavior and experience, not implementation steps.

### Desired Technical Constraints

List explicit technical constraints that the Desired state must respect.

- Performance constraints (e.g., “IDLE CPU usage < 5%”).
- Compatibility constraints (e.g., “–json remains incompatible with –dashboard”).
- Architectural constraints (e.g., “auth enforced centrally at gateway”).
- Output routing rules (e.g., “stdout redirected only in RECORDING state”).

### Non-Goals

List what this plan explicitly will NOT do.

- Future phases that are out-of-scope.
- Refactors or changes that are intentionally not part of this plan.
- Avoid vague items; be specific about non-goals to prevent scope creep.

---

## States & Modes (Optional but Recommended)

Use this section when the behavior is stateful (UI states, system modes, etc.).

### States

List all relevant states and their characteristics.

- Example: IDLE, RECORDING, PAUSED.
- For each state, briefly describe:
  - What is visible.
  - What inputs are valid.
  - What outputs / side-effects occur.

### Modes / Entry Paths

List all modes or entry paths relevant to this plan.

- Examples:
  - Dashboard mode (–dashboard).
  - Console mode (no –dashboard).
  - JSON mode (–json –no-menu).
- Describe what this plan may change vs must preserve for each mode.

### State/Mode Invariants

List rules that MUST hold across states/modes.

- Example:
  - “Q in IDLE exits app; Q in RECORDING opens pause menu.”
  - “JSON mode remains incompatible with –dashboard.”
  - “Console mode keeps existing text menu flow.”

---

## Scope

Clearly define what is included and excluded from this plan.

### In Scope

- Bullet list of what this plan covers.
- Each item SHOULD map directly to at least one top-level Task (1, 2, 3, …).

### Out of Scope

- Bullet list of what is explicitly excluded.
- LLMs MUST NOT create tasks or steps for these items.

### Phase Boundary Rules

If this plan is a phase in a larger effort, define boundaries.

- This phase MUST NOT implement logic reserved for future phases.
- This phase MAY create scaffolding (files, stubs) for later phases, but no early implementation.
- Future phases should be referenced by name/number where relevant.

### Scaffolding Requirements

List any stubs or structural prep work that must be created for future phases.

- New packages/directories needed now.
- Stub files with docstrings only.
- Clear notes on which future phases will fill them in.

---

## Policies & Contracts

Define global rules that this plan must respect.

- CLI flag policies and compatibility rules.
- Output routing rules (stdout vs stderr, logging rules).
- Security policies (auth requirements, access controls).
- Performance contracts (latency, throughput, CPU/memory budgets).
- Resource lifecycle rules (when to allocate/tear down long-lived components).

---

## Tasks

Use checkmark headings for actionable work.  
Number tasks and subtasks for traceability.

- Top-level tasks: `1`, `2`, `3`, …
- Subtasks: `1.1`, `1.2`, `1.3`, …
- Leaf steps (only when needed): `1.1.1`, `1.1.2`, …

### Greppable Structure Example (LLM MUST FOLLOW EXACTLY)

```markdown
### [ ] 1 {Task Name}
Short description: {1–3 sentences describing the outcome for this task.}
Acceptance notes:
- {Measurable condition 1 for Task 1}
- {Measurable condition 2 for Task 1}

**Files:** {path/to/file_1.py}, {path/to/file_2.py}
**Setup:** {Inputs, outputs, or commands relevant to this task.}

#### [ ] 1.1 {Subtask Name}
  - [ ] 1.1.1 {Leaf step (only if needed)}
  - [ ] 1.1.2 {Leaf step (only if needed)}

#### [ ] 1.2 {Subtask Name}
  - [ ] 1.2.1 {Leaf step (only if needed)}
```

### Numbering Rules (LLM MUST FOLLOW)

- Use levels ONLY: `1` → `1.1` → `1.1.1`.
- NEVER create deeper levels (e.g., `1.1.1.1` is forbidden).
- NEVER skip numbers.
- NEVER bold or reformat numbering differently.
- Leaf steps MUST be atomic, checkable actions.
- Create leaf steps ONLY when a subtask has 2+ sequential internal actions that warrant separate verification.
- Leaf steps MUST use exactly two leading spaces followed by `- [ ]`.

### Task Description Rules

- Top-level tasks (`1`, `2`, …) MUST:
  - Describe the purpose and outcome (1–3 sentences).
  - Include measurable acceptance notes relevant to that task.
  - NOT contain low-level implementation detail directly.
- Subtasks (`1.1`, `1.2`, …) MUST:
  - Represent a cohesive unit of implementation work.
  - Typically map to specific files, modules, or phases.
- Leaf steps (`1.1.1`, `1.1.2`, …) MUST:
  - Represent atomic steps that can be individually checked off.
  - Be used sparingly and only when truly needed for clarity.

### Task Skeleton (For Real Content)

LLMs MUST follow this skeleton when creating actual tasks.

```markdown
### [ ] 1 {Task Name}

Short description: {1–3 sentences describing the high-level outcome for this task.}
Acceptance notes:
- {Measurable condition for Task 1}
- {Another measurable condition for Task 1}

**Files:** {path/to/file_1.py}, {path/to/file_2.py}
**Setup:** {Inputs, outputs, invariants, or commands relevant to this task.}
**Task Constraints:**
- {Constraint 1, e.g., “MUST preserve git history”}
- {Constraint 2, e.g., “MUST not change behavior in console mode”}

#### [ ] 1.1 {Subtask Name}

Implementation details:
- File(s): `{path/to/file_1.py}`, `{path/to/file_2.py}`
- Responsibility: {What this subtask accomplishes.}

  - [ ] 1.1.1 {Leaf step (only if needed)}
  - [ ] 1.1.2 {Leaf step (only if needed)}

#### [ ] 1.2 {Subtask Name}

Implementation details:
- File(s): `{path/to/other_file.py}`
- Responsibility: {Second distinct part of Task 1.}

  - [ ] 1.2.1 {Leaf step (only if needed)}
  - [ ] 1.2.2 {Leaf step (only if needed)}
```

Repeat the same pattern for Task 2, Task 3, etc., with IDs updated accordingly.

---

## Acceptance Criteria

List measurable criteria that define when the plan is considered complete.

### Global Criteria

- [ ] {Criterion 1 — maps to one or more top-level tasks}
- [ ] {Criterion 2 — maps to one or more top-level tasks}

Each criterion MUST be:

- Observable (via tests, logs, behavior, or artifacts).
- Traceable to at least one task.

### Mode/State-Specific Criteria (Optional)

Group criteria when multiple modes/states must be validated.

- **Dashboard Mode:**
  - [ ] {Criterion}
- **Console Mode:**
  - [ ] {Criterion}
- **JSON Mode:**
  - [ ] {Criterion}
- **IDLE State:**
  - [ ] {Criterion}
- **RECORDING State:**
  - [ ] {Criterion}
- **PAUSED State:**
  - [ ] {Criterion}

---

## Risks & Mitigations

List risks and how they will be mitigated.

- Risk: {Description}  
  Impact: {Low/Medium/High}  
  Mitigation: {How this risk is addressed (ideally referencing Task IDs and/or AC bullets).}

LLMs are encouraged to reference specific tasks and acceptance criteria when describing mitigations (e.g., “Mitigated by Task 3.2 and AC ‘Backend errors return to IDLE’”).

---

## Validation

Describe how success will be verified.

### Shared Commands (Optional)

List commonly used commands across tasks and validation.

- `python3 -c "from tools.dashboard import LiveDashboard, DashboardState"`
- `pytest tests/integration/test_example.py -v`
- `grep -r "from tools.dashboard" tools tests --include="*.py"`

### Automated Validation

List automated tests, scripts, or checks.

- Test suites to run (with exact commands).
- Static analysis or linters.
- Performance or load tests (if applicable).

### Manual Test Checklist

Define scenario-based manual tests.

1. **Scenario Name 1**
   - [ ] Step 1
   - [ ] Step 2
   - [ ] Step 3

2. **Scenario Name 2**
   - [ ] Step 1
   - [ ] Step 2

Manual scenarios should cover:
- Happy paths.
- Edge cases.
- Error handling flows.
- Cross-mode/state behaviors when relevant.

- Run `./how_to/maistro plan-verify <plan-file>` before requesting review. Do not proceed until zero errors.

---

## Artifacts Created

List all new files, directories, schemas, or other artifacts produced by this plan.

- `{path/to/new_file.py}` — {Short description}
- `{path/to/new_directory/}` — {Short description}
- `{path/to/new_config.yaml}` — {Short description}

If no new artifacts are created (only modifications), state that explicitly.

---

## Interfaces & Dependencies

Describe how this work interacts with other parts of the system.

### Internal Dependencies

- Modules/classes/functions within the same codebase that this plan depends on or affects.

### External Dependencies

- External services, libraries, CLIs, or APIs that this plan depends on or affects.

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this plan's accuracy.

### Reviewer File Access Rules (LLM MUST FOLLOW)

- Reviewer MAY read **Source Files** (existing code/docs being modified).
- Reviewer MAY NOT read **Destination Files** yet (they do not exist until implemented).
- Reviewer MAY read **Related Documentation** for context only.
- Each Source File SHOULD include a short description of why it is relevant.

### Source Files (Existing Code/Docs Being Modified)

- `path/to/existing_file.py` — {Description of current implementation}
- `path/to/other_file.md` — {Description of current documentation}

### Destination Files (New Files This Plan Creates)

- `path/to/new_file.py` — {Description of new file}
- `path/to/new_guide.md` — {Description of new guide}

### Related Documentation (Context Only)

- `docs/SYSTEM_OVERVIEW.md` — Background architecture reference.
- `tests/` — Related tests or examples.

---

## Decision Log (Optional)

Use this section to record key decisions made during planning or implementation.

- D1.1: {Decision summary} — Status: {Open/Closed} — Date: {YYYY-MM-DD}
- D1.2: {Decision summary} — Status: {Open/Closed} — Date: {YYYY-MM-DD}

---

## Reviewer Checklist

Reviewers (human or LLM) MUST verify the following before accepting the plan as complete.

### Structure & Numbering

- [ ] Top-level tasks use only: `1`, `2`, `3`, …
- [ ] Subtasks use only: `1.1`, `1.2`, `2.1`, …
- [ ] Leaf steps use only: `1.1.1`, `1.1.2`, etc.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.
- [ ] Leaf steps appear only when a subtask has 2+ internal actions.
- [ ] Indentation rules for leaf steps are followed exactly (two spaces before `- [ ]`).

#### Example Showing Each Level

```markdown
### [ ] 1 Top-level Task
# Represents a major unit of work

#### [ ] 1.1 Subtask
# Represents a cohesive implementation piece

  - [ ] 1.1.1 Leaf Step
  # Represents an atomic checkable action

  - [ ] 1.1.2 Leaf Step

#### [ ] 1.2 Subtask
# Another cohesive unit

### [ ] 2 Another Top-level Task
```

### Traceability

- [ ] Every Task maps to at least one item in **Desired** and/or **Scope (In)**.
- [ ] No task exists that is not justified by Desired + In scope.
- [ ] Acceptance Criteria map back to top-level tasks (and, where appropriate, modes/states).
- [ ] Risks cite tasks and/or acceptance criteria where relevant.

### Content Discipline

- [ ] Objective states the outcome, not implementation details.
- [ ] Current vs Desired describes reality vs target without mixing implementation steps.
- [ ] Implementation details appear ONLY under Tasks (subtasks and leaf steps).
- [ ] Non-goals and invariants are clearly stated and respected by Tasks.
- [ ] Policies & Contracts are reflected in Tasks, AC, and Validation.

### Validation

- [ ] Validation references concrete artifacts (tests, commands, logs, screenshots).
- [ ] Manual Test Checklist covers key flows and edge cases.
- [ ] Shared Commands are consistent with Tasks and References.
- [ ] No vague instructions like “test manually” without specifics.

### References & File Access

- [ ] Source Files exist and their descriptions are accurate.
- [ ] Destination Files are described but not assumed to exist yet.
- [ ] Reviewer File Access Rules are followed (no reading Destination Files as if they already exist).
- [ ] Interfaces & Dependencies are consistent with Current vs Desired and Scope.

### Overall Consistency

- [ ] States & Modes (if present) align with Tasks and Acceptance Criteria.
- [ ] Policies & Contracts are not contradicted anywhere in the plan.
- [ ] Artifacts Created are consistent with Destination Files and Tasks.
- [ ] Decision Log (if used) does not contradict other sections.
