# Phase Plan Template

---

## Purpose

Use this template to create a phase plan document for a single phase of work within a larger project, aligned with greppable, checkmark‑first headings.

Consistency: The Master-Plan’s “Phases Overview” mirrors this phase’s major task headings exactly (numbers and titles). Keep task titles stable.

---

## Instructions

1. Copy the header structure and fill in phase metadata
2. Fill each section in order from top to bottom
3. Choose appropriate task complexity level based on the number of steps required
4. Follow formatting conventions throughout

---

## LLM Navigation & Grep Guide (For LLMs Only)

This section exists ONLY for LLMs. Do NOT modify.

### Grepping Tasks

- `grep -nE "^### \[ \] [0-9]+ " <phase-file>`

### Grepping Sub-tasks

- `grep -nE "^  - \[ \] [0-9]+\.[0-9]+ " <phase-file>`

### LLM RULES

- Do NOT invent tasks.
- Task titles MUST remain stable once created because the master plan mirrors them.
- Subtasks MUST use `- [ ] 1.1`, `- [ ] 1.2`, etc.
- If deeper structure exists, use `1.1.1` but keep it in bullets ONLY (never headings).

---

## Formatting Conventions

### Status Indicators (metadata, not headings)
- Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked

### Markdown Structure
- Checkmark headings (grep‑friendly): Use checkmarks on major task headings only — heading markers first (`###`), then `[ ]`. No trailing checkmarks. Do NOT manually toggle checkmarks to `[✅]` — `plan-sync` handles this automatically after reviewer approval.
- Phase title: `# Phase N: {Title}` (no checkmark).
- Major sections (no checkmarks): `## Detailed Objective`, `## Deliverables Snapshot`, `## Acceptance Gates`, `## Scope`, `## Interfaces & Dependencies`, `## Risks & Mitigations`, `## Decision Log`, `## References`, `## Tasks`.
- Task headings: `### [ ] 1 {Task}` for top-level tasks.
- Sub-tasks: Use `- [ ] 1.1 {Sub-task}` for sub-tasks, with plain numbering (no bold).
- **Horizontal rules**: Use `---` to separate major sections
- **Line breaks**: Add two trailing spaces at the end of a line for a line break within a paragraph, OR use a blank line to separate paragraphs/sections

### Task Formatting
- **Checkboxes**: Use `- [ ]` for trackable sub-task items
- **Numbering**: Use plain numbering for sub-tasks (e.g., `1.1`, `1.1.1`) without bold
- **Indentation**: Use 2 spaces per nesting level for bullets
- **Code elements**: Use backticks for file paths, commands, function names, code symbols
- **Sub-task style**: Use list checkboxes with two-space indent and plain numeric IDs (e.g., `  - [ ] 1.1 Sub-task description`)

### Numbering Rules (LLM MUST FOLLOW)

- Top-level tasks MUST use: `### [ ] 1 {Task}`
- Sub-tasks MUST use: `- [ ] 1.1 {Sub-task}`
- Optional deeper steps MUST use: `- [ ] 1.1.1 {Step}` (bullets only, NEVER headings)
- No numbering deeper than `1.1.1`
- Do not skip numbers

### LLM Rules for Tasks

- Tasks MUST come directly from the Detailed Objective and Scope.
- DO NOT create tasks out of thin air.
- Task numbering MUST remain stable (master plan mirrors these).
- Task titles MUST NOT be reworded once created.

### Example
```markdown
### [ ] 1 Create Directory Structure
Create the repository directory structure for the project.

  - [ ] 1.1 Create source code directories
  - [ ] 1.2 Create configuration directories
```

(Note: This example shows the canonical greppable pattern. The master plan will mirror only the `### [ ] N` and `- [ ] N.1` lines.)

---

## Template Structure Overview

Your phase plan will contain these sections in order:

1. **Header**: Phase number, name, status, dates, file path, related plans
2. **Detailed Objective**: 2-3 paragraphs describing what this phase accomplishes and success criteria
3. **Deliverables Snapshot**: 3-5 concrete outputs that will exist when complete
4. **Acceptance Gates**: 2-4 measurable criteria that define completion
5. **Scope**: What is included and excluded from this phase
6. **Interfaces & Dependencies**: Internal/external dependencies and artifacts created
7. **Risks & Mitigations**: Potential issues and how to address them
8. **Decision Log**: Track important decisions made during the phase
9. **References**: Links to related code, docs, or prior work
10. **Tasks**: Detailed work breakdown (choose complexity level)

---

## Section Formats

### 1. Header

**Format:**
```markdown
# Phase N: [Phase Name]

**Status:** Pending | 🔄 In Progress | ✅ Completed | ⚠️ Blocked  
**Planned Start:** YYYY-MM-DD  
**Target End:** YYYY-MM-DD  
**Last Updated:** YYYY-MM-DD by [Your Name] ([Your Role])  
**File:** `active_plans/[project_name]/phases/phase_N_[phase_name].md`  
**Related:** Master Plan (`active_plans/[project_name]/[project_name]_master_plan.md`) | Prev: Phase N-1 | Next: Phase N+1

---
```

**Note:** Each metadata line ends with two trailing spaces for proper line breaks in markdown.

**Example:**
```markdown
# Phase 1: Repository Setup

**Status:** 🔄 In Progress  
**Planned Start:** 2025-10-20  
**Target End:** 2025-10-23  
**Last Updated:** 2025-10-19 by Alice Smith (Engineer)  
**File:** `active_plans/project_xyz/phases/phase_1_repository_setup.md`  
**Related:** Master Plan (`active_plans/project_xyz/project_xyz_master_plan.md`) | Prev: None | Next: Phase 2

---
```

---

### 2. Detailed Objective

**Format:**
```markdown
## Detailed Objective

[2-3 paragraphs describing:
- What this phase implements or accomplishes
- Why it's important to the overall project
- Key technical requirements or constraints
- Definition of success]
```

**Example:**
```markdown
## Detailed Objective

This phase establishes the repository structure for the project, creating a clean, modular layout optimized for development and deployment. It migrates existing code from a previous repository, ensuring all critical files are correctly placed and validated. The phase is critical to provide a foundation for subsequent development phases, enabling clean imports and dependency management. Success is defined by a fully functional repository with all directories created, files migrated, and imports validated without errors.
```

---

### 3. Deliverables Snapshot

**Format:**
```markdown
## Deliverables Snapshot

1. Deliverable description with specifics (module name, path, key features)
2. Deliverable description with specifics (API endpoints, CLI commands)
3. Deliverable description with specifics (documentation, schemas, configs)
```

**Example:**
```markdown
## Deliverables Snapshot

1. Repository structure: `src/` with subdirectories (`model/`, `utils/`, `inference/`).
2. Migrated files: `src/model/core.py` and `configs/config.json` from the previous repo.
3. Requirements file: `requirements.txt` with validated dependencies.
```

---

### 4. Acceptance Gates

**Format:**
```markdown
## Acceptance Gates

- [ ] Gate 1: Specific measurable criterion (tests, performance, output validation)
- [ ] Gate 2: Specific measurable criterion (integration, API behavior)
- [ ] Gate 3: Specific measurable criterion (documentation, deployment)
```

**Example:**
```markdown
## Acceptance Gates

- [ ] Gate 1: All directories (`src/model/`, `src/utils/`) created per specification.
- [ ] Gate 2: Legacy files migrated and imports resolve without errors.
- [ ] Gate 3: `requirements.txt` installs successfully in a fresh environment.
```

---

### 5. Scope

**Format:**
```markdown
## Scope

- In Scope:
  1. Feature or capability included
  2. Feature or capability included
  3. Feature or capability included
- Out of Scope:
  1. Feature deferred or excluded (with brief reason)
  2. Feature deferred or excluded (with brief reason)
  3. Feature deferred or excluded (with brief reason)
```

**Example:**
```markdown
## Scope

- In Scope:
  1. Directory structure creation.
  2. Migration of core model and config files.
  3. Validation of Python package imports.
- Out of Scope:
  1. Model refactoring (deferred to Phase 2).
  2. Performance optimization (future phase).
  3. Automated testing setup (Phase 3).
```

---

### 6. Interfaces & Dependencies

**Format:**
```markdown
## Interfaces & Dependencies

- Internal: List internal modules, utilities, or services this phase depends on
- External: List third-party libraries, APIs, or external services required
- Artifacts: List files, fixtures, configs, or documentation this phase creates
```

**Example:**
```markdown
## Interfaces & Dependencies

- Internal: None.
- External: `pathlib` for directory creation; `shutil` for file copying.
- Artifacts: `src/model/core.py`, `configs/config.json`, `requirements.txt`.
```

---

### 7. Risks & Mitigations

**Format:**
```markdown
## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| {risk} | {impact} | {mitigation} |
```

**Example:**
```markdown
## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Legacy file paths incorrect | Migration fails | Validate source paths before copying |
| Dependency conflicts | Setup fails | Test `requirements.txt` in isolated environment |
```

---

### 8. Decision Log

**Format:**
```markdown
## Decision Log

- D1: Decision description — Status: Open/Closed — Date: YYYY-MM-DD
- D2: Decision description — Status: Open/Closed — Date: YYYY-MM-DD
```

**Example:**
```markdown
## Decision Log

- D1: Use `src/`-based structure — Status: Closed — Date: 2025-10-19
- D2: Exclude training scripts from migration — Status: Closed — Date: 2025-10-19
```

---

### 9. References

(Note: Reference structure aligned with Simple Plan and Master Plan templates.)

**Format:**
```markdown
## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `path/to/existing_file.py` — Current implementation description

### Destination Files (new files this phase creates)
- `path/to/new_file.py` — New file description

### Related Documentation (context only)
- `docs/SYSTEM_OVERVIEW.md` — Background reference
- `tests/` — Related tests
```

**Example:**
```markdown
## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files
- `source_repo/core.py` — Current model implementation

### Destination Files
- `src/model/core.py` — Migrated model file
- `configs/config.json` — Migrated configuration file

### Related Documentation
- See `how_to/guides/reference.md` — Grep-friendly checkmark headings and validation
- `docs/project_setup.md` — Setup guide
```

---

### 10. Tasks

> **When editing tasks:** Preserve existing task numbers and titles verbatim — the master plan mirrors them. Do NOT manually toggle checkmarks; `plan-sync` handles this after approval.

**Format:**
```markdown
## Tasks
```

Choose complexity level based on your work breakdown:

---

## Task Complexity Guide

### Simple Tasks (1-3 steps, straightforward execution)

Use when the task is straightforward with minimal or no sub-tasks.

**Format:**
```markdown
### [ ] 1 {Task Name}
Brief description of what this task accomplishes.

  - [ ] 1.1 Sub-task description
  - [ ] 1.2 Sub-task description
```

**Example:**
```markdown
### [ ] 1 Create Requirements File
Create a requirements file listing project dependencies.

  - [ ] 1.1 Generate `requirements.txt` from Poetry lock file
  - [ ] 1.2 Validate installation in a fresh environment
```

**Single-Task Example (No Sub-Tasks):**
```markdown
### [ ] 1 Initialize Git Repository
Initialize a new git repository for the project.
```

---

### Medium Complexity (4-8 steps, needs logical grouping)

Use when steps naturally cluster into logical sub-tasks.

**Format:**
```markdown
### [ ] 1 {Task Name}
Brief description.

  - [ ] 1.1 Sub-task description
  - [ ] 1.2 Sub-task description
  - [ ] 1.3 Sub-task description

### [ ] 2 {Task Name}
Brief description.

  - [ ] 2.1 Sub-task description
  - [ ] 2.2 Sub-task description
```

**Example:**
```markdown
### [ ] 1 Create Directory Structure
Create the repository directory structure for the project.

  - [ ] 1.1 Create source code directories (`src/model/`, `src/utils/`)
  - [ ] 1.2 Create configuration directories (`configs/`)
  - [ ] 1.3 Verify directory structure with script

### [ ] 2 Migrate Files
Migrate core files from the previous repository.

  - [ ] 2.1 Copy `core.py` to `src/model/core.py`
  - [ ] 2.2 Copy `config.json` to `configs/config.json`
  - [ ] 2.3 Validate copied files
```

---

### High Complexity (8+ steps, multiple sub-tasks)

Use when you need a detailed breakdown with multiple sub-tasks.

**Format:**
```markdown
### [ ] 1 {Task Name}
Brief description.

  - [ ] 1.1 Sub-task description
  - [ ] 1.2 Sub-task description
  - [ ] 1.3 Sub-task description

### [ ] 2 {Task Name}
Brief description.

  - [ ] 2.1 Sub-task description
  - [ ] 2.2 Sub-task description
  - [ ] 2.3 Sub-task description
```

**Example:**
```markdown
### [ ] 1 Implement Model Refactoring
Refactor the model to support new interface requirements.

  - [ ] 1.1 Rename class to `NewModel`
  - [ ] 1.2 Implement `encode()` method
  - [ ] 1.3 Implement `decode()` method
  - [ ] 1.4 Validate method signatures

### [ ] 2 Write Unit Tests
Create tests to validate refactored model.

  - [ ] 2.1 Create test file structure
  - [ ] 2.2 Write shape validation tests
  - [ ] 2.3 Write numerical equivalence tests
  - [ ] 2.4 Run tests and verify coverage
```

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile <slug>` if checkmarks appear stale.

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] Optional deeper tasks use `- [ ] N.1.1` and never headings.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.

### Traceability

- [ ] All tasks reflect Detailed Objective and Scope.
- [ ] Task titles match what will appear in the master plan.
- [ ] No invented tasks.

### Consistency

- [ ] Section ordering follows the template.
- [ ] All metadata fields are present in the Header.
- [ ] Deliverables Snapshot, Acceptance Gates, and Scope refer to real tasks.

### References

- [ ] Source, Destination, and Related Documentation sections appear.

## End of Template

When creating a phase plan, copy the sections above and fill them with your specific content. Choose the appropriate task complexity level for your work breakdown.
