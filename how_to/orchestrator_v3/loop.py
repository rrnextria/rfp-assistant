"""Main orchestration loop for orchestrator_v3.

Ties together state, artifacts, approval, prompts, and reviewer modules
into a functioning review loop with pause/resume support.
"""

from __future__ import annotations

import hashlib
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from orchestrator_v3.approval import check_approved, parse_orch_meta
from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType, Status
from orchestrator_v3.plan_tool import verify_plan_syntax
from orchestrator_v3.preflight import run_code_preflight, run_plan_preflight
from orchestrator_v3.prompts import PromptBuilder
from orchestrator_v3.reviewer import ReviewerBase
from orchestrator_v3.state import CampaignManager, StateManager

logger = logging.getLogger(__name__)

ResumeAction = Literal["run_reviewer", "needs_response", "already_approved"]


class ReviewOutcome(Enum):
    """Result of a single review round."""

    APPROVED = "approved"
    NOT_APPROVED = "not_approved"
    REVIEWER_ERROR = "reviewer_error"
    PREFLIGHT_FAILED = "preflight_failed"


def determine_resume_point(
    artifact_resolver: ArtifactResolver,
    approval_checker=check_approved,
) -> tuple[int, ResumeAction]:
    """Scan filesystem to determine where to resume.

    Returns ``(round, action)`` where action is one of:
    - ``"run_reviewer"`` — ready to invoke reviewer for this round
    - ``"needs_response"`` — review exists but no response yet
    - ``"already_approved"`` — review exists and is approved
    """
    max_review, max_response = artifact_resolver.scan_existing_rounds()

    if max_review == 0:
        return (1, "run_reviewer")

    # Check the highest review round
    review_file = artifact_resolver.review_path(max_review)
    response_file = artifact_resolver.response_path(max_review)

    if response_file.exists():
        # Response written for highest review round — next round
        return (max_review + 1, "run_reviewer")

    # Review exists but no response
    if approval_checker(review_file):
        return (max_review, "already_approved")

    return (max_review, "needs_response")


class OrchestratorLoop:
    """Main orchestration engine tying all modules together."""

    def __init__(
        self,
        state_manager: StateManager,
        artifact_resolver: ArtifactResolver,
        prompt_builder: PromptBuilder,
        reviewer: ReviewerBase,
        display: Any,
        settings: OrchestratorSettings,
        campaign_manager: CampaignManager | None = None,
        skip_preflight: bool = False,
    ) -> None:
        self.state_manager = state_manager
        self.artifact_resolver = artifact_resolver
        self.prompt_builder = prompt_builder
        self.reviewer = reviewer
        self.display = display
        self.settings = settings
        self.campaign_manager = campaign_manager
        self.skip_preflight = skip_preflight
        _initial_state = state_manager.load()
        self.mode = Mode(_initial_state.mode)
        self._phase_file: str | None = None
        self._stage_label: str | None = None
        self._max_rounds: int = 10
        self._expected_stage: int = getattr(_initial_state, "current_stage", 0)

    def run(
        self,
        start_round: int = 1,
        max_rounds: int = 10,
        dry_run: bool = False,
        resume: bool = False,
        skip_preflight: bool | None = None,
    ) -> int:
        """Main entry point. Returns 0 on success/pause, 1 on error."""
        if skip_preflight is not None:
            self.skip_preflight = skip_preflight
        if resume:
            resume_result = self.handle_resume()
            if resume_result is None:
                # Check if handle_approval advanced a complex plan stage
                state = self.state_manager.load()
                if (
                    self.mode == Mode.PLAN
                    and state.plan_type == PlanType.COMPLEX.value
                    and state.status == Status.NEEDS_REVIEW.value
                ):
                    return self._run_complex_plan(1, max_rounds, state)
                return 0
            start_round = resume_result

        if dry_run:
            prompt = self._build_prompt(start_round)
            self.display.print_dry_run(prompt)
            return 0

        state = self.state_manager.load()

        # Complex plan mode: outer stage loop
        if self.mode == Mode.PLAN and state.plan_type == PlanType.COMPLEX.value:
            return self._run_complex_plan(start_round, max_rounds, state)

        # Code mode and simple plan mode: single round loop
        return self._run_round_loop(start_round, max_rounds)

    def _run_complex_plan(self, start_round, max_rounds, state) -> int:
        """Outer stage loop for complex plan mode."""
        for stage_idx in range(state.current_stage, state.total_stages):
            stage_file = state.stage_files[stage_idx] if stage_idx < len(state.stage_files) else None
            stage_label = Path(stage_file).stem if stage_file else f"stage_{stage_idx}"
            self._stage_label = stage_label
            self.display.print_stage_header(stage_idx, state.total_stages, stage_label, stage_file)

            # Create stage-specific ArtifactResolver and sync to PromptBuilder.
            # Complex plan artifacts are scoped by stage_label (not phase/task),
            # so use plan-mode defaults (phase=0, task=1) instead of copying
            # vestigial state values. (Fix for D7 / subtask 7.2)
            self._expected_stage = stage_idx
            self.artifact_resolver = ArtifactResolver(
                slug=self.artifact_resolver.slug,
                mode=self.mode,
                phase=0,
                task=1,
                settings=self.settings,
                stage_label=stage_label,
            )
            self.prompt_builder._ar = self.artifact_resolver

            round_start = start_round if stage_idx == state.current_stage else 1
            result = self._run_round_loop(round_start, max_rounds)
            if result != 0:
                return result

            # handle_approval() advances stage or sets APPROVED;
            # handle_pause() sets NEEDS_RESPONSE
            loaded = self.state_manager.load()
            if loaded.status == Status.NEEDS_RESPONSE.value:
                return 0
            if loaded.status == Status.APPROVED.value:
                return 0
            # NEEDS_REVIEW: handle_approval advanced to next stage — continue

        return 0

    def _run_round_loop(self, start_round: int, max_rounds: int) -> int:
        """Inner round loop. Returns 0 on success/pause, 1 on error."""
        self._max_rounds = max_rounds
        for round_num in range(start_round, max_rounds + 1):
            outcome = self.run_review_round(round_num)

            if outcome == ReviewOutcome.APPROVED:
                self.handle_approval(round_num)
                return 0

            if outcome == ReviewOutcome.PREFLIGHT_FAILED:
                # Preflight already printed failure report and set state;
                # do NOT call handle_pause() (no review file to reference).
                return 0

            if outcome == ReviewOutcome.NOT_APPROVED:
                # If this was the last allowed round, exit 1 (max rounds)
                if round_num >= max_rounds:
                    self.display.print_max_rounds_banner(max_rounds, self.mode.value, self._stage_label)
                    return 1
                self.handle_pause(round_num)
                return 0

            if outcome == ReviewOutcome.REVIEWER_ERROR:
                self.display.print_retry_banner()
                return 1

        # Max rounds exhausted (no rounds ran — shouldn't happen with valid inputs)
        self.display.print_max_rounds_banner(max_rounds, self.mode.value, self._stage_label)
        return 1

    def run_review_round(self, round_num: int) -> ReviewOutcome:
        """Execute a single review round."""
        self.display.print_round_header(round_num, self._max_rounds, self._stage_label)

        # Verify code artifact integrity (code mode)
        if self.mode == Mode.CODE:
            if not self.verify_code_artifact(round_num):
                logger.warning("Code artifact verification failed")
                return ReviewOutcome.REVIEWER_ERROR

        # Preflight validation (before invoking reviewer)
        if not self.skip_preflight:
            preflight_outcome = self._run_preflight(round_num)
            if preflight_outcome is not None:
                return preflight_outcome

        # Plan structure verification (plan mode only)
        if not self.skip_preflight and self.mode == Mode.PLAN:
            verification_outcome = self._run_plan_verification(round_num)
            if verification_outcome is not None:
                return verification_outcome

        prompt = self._build_prompt(round_num)
        review_file = self.artifact_resolver.review_path(round_num)
        log_file = Path(str(review_file) + ".log")

        # Update state
        self.state_manager.update(
            status=Status.NEEDS_REVIEW, current_round=round_num
        )

        # Run reviewer
        success = self.reviewer.run_review(prompt, review_file, log_file)

        if not success:
            return ReviewOutcome.REVIEWER_ERROR

        # Verify review file and ORCH_META
        result = parse_orch_meta(review_file)
        if result is None:
            logger.warning(
                "Reviewer completed but review file is missing "
                "or lacks valid ORCH_META block: %s",
                review_file,
            )
            return ReviewOutcome.NOT_APPROVED

        # Record round
        is_approved = check_approved(review_file)
        self.state_manager.record_round(
            round_num=round_num,
            action="review",
            outcome="approved" if is_approved else "fixes_required",
            artifact_path=str(review_file),
            verdict=result.verdict.value,
            blocker=result.blocker,
            major=result.major,
            minor=result.minor,
            stage_label=self._stage_label,
        )

        if is_approved:
            return ReviewOutcome.APPROVED
        return ReviewOutcome.NOT_APPROVED

    def handle_approval(self, round_num: int) -> None:
        """Handle approved review — advance state appropriately."""
        state = self.state_manager.load()

        if self.mode == Mode.CODE:
            self.display.print_approved_banner(mode="code", round=round_num)
            if self.campaign_manager is not None:
                # Pass expected phase/task from artifact resolver for validation
                self.campaign_manager.advance_task(
                    expected_phase=self.artifact_resolver.phase,
                    expected_task=self.artifact_resolver.task,
                )
                # Auto-trigger: sync plan checkmarks after successful advance
                try:
                    plan_type = self.artifact_resolver.detect_plan_type()
                    if plan_type == PlanType.COMPLEX:
                        from orchestrator_v3.plan_tool import (
                            plan_render_master,
                            plan_sync,
                        )

                        plan_sync(
                            slug=self.artifact_resolver.slug,
                            phase=self.artifact_resolver.phase,
                            task=self.artifact_resolver.task,
                            settings=self.settings,
                        )
                        plan_render_master(
                            slug=self.artifact_resolver.slug,
                            settings=self.settings,
                        )
                except Exception as e:
                    logger.warning("Plan sync failed (non-fatal): %s", e)
            else:
                self.state_manager.update(status=Status.APPROVED)
        elif state.plan_type == PlanType.COMPLEX.value:
            # Complex plan mode: advance stage (with idempotent guard)
            self.display.print_approved_banner(mode="plan", round=round_num)
            expected = getattr(self, "_expected_stage", state.current_stage)
            if state.current_stage != expected:
                # Stage already advanced past what we approved — skip (7.3)
                return
            if state.current_stage + 1 < state.total_stages:
                self.state_manager.update(
                    current_stage=state.current_stage + 1,
                    current_round=1,
                    status=Status.NEEDS_REVIEW,
                )
            else:
                self.state_manager.update(status=Status.APPROVED)
        else:
            # Simple plan mode
            self.display.print_approved_banner(mode="plan", round=round_num)
            self.state_manager.update(status=Status.APPROVED)

    def handle_pause(self, round_num: int) -> None:
        """Handle not-approved review — pause for user response."""
        self.display.print_waiting_banner(
            mode=self.mode.value,
            round=round_num,
            review_file=str(self.artifact_resolver.review_path(round_num)),
            response_file=str(self.artifact_resolver.response_path(round_num)),
            stage_label=self._stage_label,
        )
        self.state_manager.update(
            status=Status.NEEDS_RESPONSE, current_round=round_num
        )

    def handle_resume(self) -> int | None:
        """Handle --resume flag. Returns start round or None (already handled)."""
        # For complex plans, create a stage-specific resolver so resume
        # scans only the current stage's artifacts (7.5).
        state = self.state_manager.load()
        if (
            self.mode == Mode.PLAN
            and state.plan_type == PlanType.COMPLEX.value
            and state.current_stage < len(state.stage_files)
        ):
            stage_file = state.stage_files[state.current_stage]
            stage_label = Path(stage_file).stem
            resolver = ArtifactResolver(
                slug=self.artifact_resolver.slug,
                mode=self.mode,
                phase=0,
                task=1,
                settings=self.settings,
                stage_label=stage_label,
            )
        else:
            resolver = self.artifact_resolver

        round_num, action = determine_resume_point(resolver)

        if action == "already_approved":
            self.handle_approval(round_num)
            return None

        if action == "needs_response":
            self.display.print_waiting_banner(
                mode=self.mode.value,
                round=round_num,
                review_file=str(self.artifact_resolver.review_path(round_num)),
                response_file=str(self.artifact_resolver.response_path(round_num)),
                stage_label=self._stage_label,
            )
            return None

        # action == "run_reviewer"
        return round_num

    def _run_preflight(self, round_num: int) -> ReviewOutcome | None:
        """Run preflight validation on the current artifact.

        Returns ``ReviewOutcome.PREFLIGHT_FAILED`` if checks fail (loop should
        pause without printing the generic waiting banner), or ``None`` if
        checks pass (proceed to reviewer).

        For code mode, validates ``code_complete_round{R}.md`` for the current
        round.  For plan mode, validates the planner update from the *previous*
        round (``response_path(round_num - 1)``).  Round 1 in plan mode has no
        prior update to validate, so preflight is skipped.
        """
        if self.mode == Mode.CODE:
            artifact = self.artifact_resolver.complete_path(round_num)
            if round_num > 1:
                result = run_code_preflight(
                    artifact,
                    check_findings=True,
                    response_path=self.artifact_resolver.response_path(
                        round_num - 1,
                    ),
                    review_path=self.artifact_resolver.review_path(
                        round_num - 1,
                    ),
                )
            else:
                result = run_code_preflight(artifact)
        else:
            # Plan mode: round 1 reviews the original plan — no update to
            # validate.  For round > 1, validate the planner's update from
            # the previous round.
            if round_num <= 1:
                return None
            artifact = self.artifact_resolver.response_path(round_num - 1)
            result = run_plan_preflight(artifact)

        if not result.passed:
            self.display.print_preflight_failure(result)
            self.state_manager.update(
                status=Status.NEEDS_RESPONSE, current_round=round_num
            )
            return ReviewOutcome.PREFLIGHT_FAILED
        return None

    def _run_plan_verification(self, round_num: int) -> ReviewOutcome | None:
        """Run structural plan verification before invoking the reviewer.

        Only called in plan mode (code-mode verification happens at CLI entry
        points only).  Determines the target file and ``check_cross_file``
        flag from the current loop state:

        - Complex plan, phase stage: current phase file, ``check_cross_file=False``
        - Complex plan, master stage (last stage): master plan, ``check_cross_file=True``
        - Simple plan: ``state.plan_file``, ``check_cross_file=False``

        Returns ``ReviewOutcome.PREFLIGHT_FAILED`` on errors (blocking), or
        ``None`` on success (proceed to reviewer).  Warnings are logged to
        stderr but do not block.
        """
        state = self.state_manager.load()

        if state.plan_type == PlanType.COMPLEX.value:
            stage_idx = state.current_stage
            stage_files = state.stage_files
            # Last stage is the master plan
            if stage_idx == len(stage_files) - 1:
                target = Path(stage_files[-1])
                check_cross_file = True
            else:
                target = Path(stage_files[stage_idx])
                check_cross_file = False
        else:
            # Simple plan
            target = Path(state.plan_file)
            check_cross_file = False

        result = verify_plan_syntax(
            target, settings=self.settings, check_cross_file=check_cross_file
        )

        if not result.passed:
            self.display.print_verification_failure(result)
            self.state_manager.update(
                status=Status.NEEDS_RESPONSE, current_round=round_num
            )
            return ReviewOutcome.PREFLIGHT_FAILED

        # Log warnings to stderr if any
        if result.warnings > 0:
            import sys
            for issue in result.issues:
                if issue.severity == "warning":
                    line_info = f" (line {issue.line_number})" if issue.line_number else ""
                    print(
                        f"Plan verification warning{line_info}: {issue.message}",
                        file=sys.stderr,
                    )

        return None

    def verify_code_artifact(self, round_num: int) -> bool:
        """Verify code_complete artifact exists for the current round.

        Each round has its own ``code_complete_round{R}.md`` artifact.
        """
        artifact = self.artifact_resolver.complete_path(round_num)
        if not artifact.exists():
            logger.error("Code artifact not found: %s", artifact)
            return False

        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.state_manager.update(code_artifact_hash=digest)
        return True

    def _build_prompt(self, round_num: int) -> str:
        """Build the appropriate prompt based on mode and plan type."""
        state = self.state_manager.load()

        if self.mode == Mode.CODE:
            # Use resolver (CLI-selected) phase/task, NOT state (which may drift)
            phase_file = self._phase_file
            return self.prompt_builder.build_code_prompt(
                round_num=round_num,
                phase=self.artifact_resolver.phase,
                task=self.artifact_resolver.task,
                plan_file=state.plan_file,
                phase_file=phase_file,
            )

        # Plan mode
        if state.plan_type == PlanType.COMPLEX.value:
            # Complex plan: use stage-appropriate prompt
            stage_idx = state.current_stage
            stage_files = state.stage_files

            if stage_idx < len(stage_files):
                stage_file = stage_files[stage_idx]
                # Last stage is the master plan
                if stage_idx == len(stage_files) - 1:
                    # Master plan review
                    approved = stage_files[:-1]
                    context = self.prompt_builder.build_plan_context(round_num)
                    return self.prompt_builder.build_master_review_prompt(
                        round_num=round_num,
                        master_file=stage_file,
                        approved_phases=approved,
                        context=context,
                    )
                else:
                    # Phase review
                    master_file = stage_files[-1] if stage_files else state.plan_file
                    context = self.prompt_builder.build_plan_context(round_num)
                    return self.prompt_builder.build_phase_review_prompt(
                        round_num=round_num,
                        phase_file=stage_file,
                        master_file=master_file,
                        context=context,
                    )

        # Simple plan mode
        context = self.prompt_builder.build_plan_context(round_num)
        return self.prompt_builder.build_simple_plan_prompt(
            round_num=round_num,
            plan_file=state.plan_file,
            context=context,
        )
