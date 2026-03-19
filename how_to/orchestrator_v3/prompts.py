"""Prompt building for orchestrator_v3 plan and code review modes.

Generates structured text prompts sent to Codex (the reviewer) for both
plan review and code review modes.  Each prompt includes ORCH_META format
instructions with a complete literal example block (safe because the
orchestrator uses structured ``.md`` parsing, not grep on ``.log`` files), finding ID
conventions, and prior-round context for multi-round convergence.
"""

from __future__ import annotations

from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode


class PromptBuilder:
    """Builds reviewer prompts for plan and code review modes."""

    def __init__(
        self,
        artifact_resolver: ArtifactResolver,
        mode: Mode,
        slug: str,
        model: str = "gpt-5.4",
    ) -> None:
        """Initialize with an artifact resolver, mode, slug, and model name."""
        self._ar = artifact_resolver
        self.mode = mode if isinstance(mode, Mode) else Mode(mode)
        self.slug = slug
        self.model = model

    # ------------------------------------------------------------------
    # Shared instruction blocks (Task 1)
    # ------------------------------------------------------------------

    def _orch_meta_instructions(self) -> str:
        return """\
MACHINE-READABLE VERDICT (REQUIRED — place at line 1 of your review file):

You MUST start your review file with an ORCH_META block.  This is an HTML
comment that encodes your verdict and severity counts for automated parsing.

Place it at the VERY START of the file, before any other content.  Do NOT
put it inside a markdown code fence.

APPROVED example (all counts must be 0):

<!-- ORCH_META
VERDICT: APPROVED
BLOCKER: 0
MAJOR: 0
MINOR: 0
DECISIONS: 0
VERIFIED: 9
-->

FIXES_REQUIRED example:

<!-- ORCH_META
VERDICT: FIXES_REQUIRED
BLOCKER: 1
MAJOR: 2
MINOR: 1
DECISIONS: 0
VERIFIED: 5
-->

Rules:
- VERDICT is APPROVED or FIXES_REQUIRED (no other values).
- Counts are non-negative integers.
- VERDICT=APPROVED requires BLOCKER, MAJOR, MINOR, and DECISIONS to all be 0.
- The closing tag is --> on its own line.
- VERIFIED is the count of previously-raised findings confirmed as resolved."""

    def _finding_id_instructions(self) -> str:
        return """\
FINDING IDS (REQUIRED):

Assign a stable ID to each finding using these prefixes:
- B1, B2, ... for blockers
- M1, M2, ... for majors
- N1, N2, ... for minors
- D1, D2, ... for decisions

IDs must be unique within the review, sequential per severity, and stable
across rounds (the same finding keeps the same ID).  Reference findings
by ID in prose (e.g., "B1: Missing null check in parse_config")."""

    def _prior_round_tracking_instructions(self, round_num: int) -> str:
        if round_num <= 1:
            return ""
        return """\
PRIOR-ROUND TRACKING (REQUIRED for round {round}):

Read the prior round's review and response files (listed in PRIOR ROUND
CONTEXT below).  For each finding from the prior round, mark it as:
- RESOLVED — fix verified, no longer an issue
- STILL_OPEN — not adequately addressed
- WONTFIX — acknowledged but intentionally not addressed (requires justification)
- NEW — newly discovered this round

List the status of every prior finding explicitly (e.g., "B1: RESOLVED").
Only create new findings for genuinely new issues.

ORCH_META counts must reflect the CURRENT round only: count STILL_OPEN +
NEW findings.  WONTFIX findings are excluded from severity counts.  Do NOT
use historical cumulative counts.""".format(round=round_num)

    # ------------------------------------------------------------------
    # Plan mode prompts (Task 2)
    # ------------------------------------------------------------------

    def build_simple_plan_prompt(
        self, round_num: int, plan_file: str, context: str
    ) -> str:
        """Build a reviewer prompt for a simple (single-file) plan review."""
        review_out = self._ar.review_path(round_num)
        parts = [
            f"You are the Plan Reviewer. Read and follow how_to/guides/plan_review.md exactly.",
            "",
            f"TASK: Review the plan file.",
            "",
            f"PLAN FILE TO REVIEW: {plan_file}",
            "",
            self._orch_meta_instructions(),
            "",
            self._finding_id_instructions(),
            "",
            self._prior_round_tracking_instructions(round_num),
            "",
            context,
            "",
            f"Write your review to: {review_out}",
            "",
            "Check against the Plan Review Checklist in how_to/guides/plan_review.md.",
            "DO NOT offer to fix or update the plan. Review-only.",
        ]
        return "\n".join(p for p in parts if p is not None).strip()

    def build_phase_review_prompt(
        self,
        round_num: int,
        phase_file: str,
        master_file: str,
        context: str,
    ) -> str:
        """Build a reviewer prompt for a single phase of a complex plan."""
        review_out = self._ar.review_path(round_num)
        parts = [
            f"You are the Plan Reviewer. Read and follow how_to/guides/plan_review.md exactly.",
            "",
            f"TASK: Review the phase plan file.",
            "",
            "CONTEXT FILES (read these first):",
            f"- Master Plan: {master_file} (context only — do NOT review it now)",
            f"- Phase Plan: {phase_file} (THIS is the review target)",
            "",
            self._orch_meta_instructions(),
            "",
            self._finding_id_instructions(),
            "",
            self._prior_round_tracking_instructions(round_num),
            "",
            context,
            "",
            "PHASE REVIEW FOCUS:",
            "- Detailed objectives present and specific",
            "- All tasks have subtasks with specific implementation details",
            "- Acceptance gates measurable and testable",
            "- Scope clearly defined (in-scope and out-of-scope)",
            "- Risks and mitigations present",
            "- References list real, existing files",
            "- No placeholder or template text remains",
            "",
            f"Write your review to: {review_out}",
            "",
            "Check against the Plan Review Checklist in how_to/guides/plan_review.md.",
            "DO NOT offer to fix or update the plan. Review-only.",
        ]
        return "\n".join(p for p in parts if p is not None).strip()

    def build_master_review_prompt(
        self,
        round_num: int,
        master_file: str,
        approved_phases: list[str],
        context: str,
    ) -> str:
        """Build a reviewer prompt for the master plan (after all phases approved)."""
        review_out = self._ar.review_path(round_num)
        phase_list = "\n".join(f"  - {p} (APPROVED)" for p in approved_phases)
        parts = [
            f"You are the Plan Reviewer. Read and follow how_to/guides/plan_review.md exactly.",
            "",
            f"TASK: Review the master plan (all phase files already approved).",
            "",
            f"MASTER PLAN TO REVIEW: {master_file}",
            "",
            "APPROVED PHASE FILES:",
            phase_list,
            "",
            self._orch_meta_instructions(),
            "",
            self._finding_id_instructions(),
            "",
            self._prior_round_tracking_instructions(round_num),
            "",
            context,
            "",
            "MASTER REVIEW FOCUS:",
            "- Template structure followed correctly",
            "- Phases Overview mirrors phase files exactly",
            "- Global Acceptance Gates measurable",
            "- Dependency Gates testable",
            "- Cross-phase consistency",
            "- References list real files",
            "- Decision Log complete",
            "",
            f"Write your review to: {review_out}",
            "",
            "Check against the Plan Review Checklist in how_to/guides/plan_review.md.",
            "DO NOT offer to fix or update the plan. Review-only.",
        ]
        return "\n".join(p for p in parts if p is not None).strip()

    # ------------------------------------------------------------------
    # Code mode prompt (Task 3)
    # ------------------------------------------------------------------

    def build_code_prompt(
        self,
        round_num: int,
        phase: int,
        task: int,
        plan_file: str,
        phase_file: str | None,
    ) -> str:
        """Build a reviewer prompt for a code review round."""
        review_out = self._ar.review_path(round_num)
        code_artifact = self._ar.complete_path(round_num)

        prior_context = self.build_code_context(round_num)

        context_lines = [
            "CONTEXT FILES (read these first to understand the task requirements):",
        ]
        if phase_file is not None:
            context_lines.append(f"- Master Plan: {plan_file}")
            context_lines.append(f"- Phase Plan: {phase_file}")
        else:
            context_lines.append(f"- Plan: {plan_file}")
        context_lines.append("- Coder-Reviewer Guidelines: how_to/guides/code_review.md")

        parts = [
            "You are the Code Reviewer. Read and follow how_to/guides/code_review.md exactly.",
            "",
            f"TASK: Review the code implementation for Phase {phase}, Task {task}.",
            "",
            "\n".join(context_lines),
            "",
            f"CODE ARTIFACT TO REVIEW: {code_artifact}",
            "",
            self._orch_meta_instructions(),
            "",
            self._finding_id_instructions(),
            "",
            self._prior_round_tracking_instructions(round_num),
            "",
            prior_context,
            "",
            f"Write your review to: {review_out}",
            "",
            "ENHANCED VERIFICATION CHECKLIST:",
            "- Subtask Completeness: Read the phase plan and verify ALL numbered subtasks are implemented.",
            "- Extract vs Create: If the plan says 'extract from X', verify the code actually comes from file X.",
            "- SHA-256 Hashes: If artifact contains hashes, verify they are real 64-char hex (not placeholders).",
            "- Test Skip Conditions: For tests requiring optional deps, verify skip conditions check ALL required deps.",
            "- Import Verification: Check that all imports in new files are valid and available.",
            "",
            "DO NOT offer to fix or update code. Review-only.",
        ]
        return "\n".join(p for p in parts if p is not None).strip()

    # ------------------------------------------------------------------
    # Prior-round context (Task 4)
    # ------------------------------------------------------------------

    def build_plan_context(self, round_num: int) -> str:
        """Build prior-round context block for plan review (empty for round 1)."""
        if round_num <= 1:
            return ""
        prev = round_num - 1
        review = self._ar.review_path(prev)
        response = self._ar.response_path(prev)
        return (
            "PRIOR ROUND CONTEXT (read these files before reviewing):\n"
            f"- Prior review (round {prev}): {review}\n"
            f"- Planner update (round {prev}): {response}\n"
            "\n"
            "Open and read these files before writing your review. "
            "Reuse finding IDs from the prior review. "
            "Mark each prior finding as RESOLVED, STILL_OPEN, or NEW."
        )

    def build_code_context(self, round_num: int) -> str:
        """Build prior-round context block for code review (empty for round 1)."""
        if round_num <= 1:
            return ""
        prev = round_num - 1
        review = self._ar.review_path(prev)
        response = self._ar.response_path(prev)
        return (
            "PRIOR ROUND CONTEXT (read these files before reviewing):\n"
            f"- Prior review (round {prev}): {review}\n"
            f"- Coder response (round {prev}): {response}\n"
            "\n"
            "Open and read these files before writing your review. "
            "Reuse finding IDs from the prior review. "
            "Mark each prior finding as RESOLVED, STILL_OPEN, or NEW."
        )
