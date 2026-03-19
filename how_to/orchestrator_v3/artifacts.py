"""Artifact path resolution, plan type detection, and round scanning."""

from __future__ import annotations

import re
from pathlib import Path

from orchestrator_v3.config import Mode, OrchestratorSettings, PlanType


class ArtifactResolver:
    """Resolves file paths for review artifacts and detects plan structure.

    Centralizes all artifact naming conventions so that the loop, prompts,
    and CLI modules never construct file names directly.

    Args:
        slug: Project slug (e.g. ``"fp8_training"``).
        mode: Review mode (``PLAN`` or ``CODE``).
        phase: Phase number (code mode) or 0 (plan mode).
        task: Task number (code mode) or 1 (plan mode).
        settings: Orchestrator settings (provides ``reviews_dir``, ``active_plans_dir``).
        stage_label: Optional stage stem for complex plan stage-specific artifacts.
        plan_slug: Optional override for plan directory lookup (defaults to ``slug``).
    """

    def __init__(
        self,
        slug: str,
        mode: Mode,
        phase: int,
        task: int,
        settings: OrchestratorSettings,
        stage_label: str | None = None,
        plan_slug: str | None = None,
    ) -> None:
        self.slug = slug
        self.plan_slug = plan_slug or slug
        self.mode = mode if isinstance(mode, Mode) else Mode(mode)
        self.phase = phase
        self.task = task
        self.settings = settings
        self.stage_label = stage_label
        self.reviews_dir = settings.reviews_dir
        self.active_plans_dir = settings.active_plans_dir

    def review_path(self, round_num: int) -> Path:
        """Return the path for a review artifact for the given round."""
        if self.mode == Mode.CODE:
            name = (
                f"{self.slug}_phase_{self.phase}_task_{self.task}"
                f"_code_review_round{round_num}.md"
            )
        elif self.stage_label is not None:
            name = (
                f"{self.slug}_{self.stage_label}"
                f"_review_round{round_num}.md"
            )
        else:
            name = f"{self.slug}_plan_review_round{round_num}.md"
        return self.reviews_dir / name

    def response_path(self, round_num: int) -> Path:
        """Return the path for a coder/planner response artifact."""
        if self.mode == Mode.CODE:
            name = (
                f"{self.slug}_phase_{self.phase}_task_{self.task}"
                f"_coder_response_round{round_num}.md"
            )
        elif self.stage_label is not None:
            name = (
                f"{self.slug}_{self.stage_label}"
                f"_update_round{round_num}.md"
            )
        else:
            name = f"{self.slug}_plan_update_round{round_num}.md"
        return self.reviews_dir / name

    def complete_path(self, round_num: int) -> Path:
        """Return the path for a code_complete artifact (code mode only).

        Raises:
            ValueError: If called in plan mode.
        """
        if self.mode == Mode.PLAN:
            raise ValueError(
                "code_complete artifacts are only used in code mode"
            )
        return self.reviews_dir / (
            f"{self.slug}_phase_{self.phase}_task_{self.task}"
            f"_code_complete_round{round_num}.md"
        )

    def detect_plan_type(self) -> PlanType:
        """Detect whether the plan is simple or complex (has ``phases/`` dir)."""
        phases_dir = self.active_plans_dir / self.plan_slug / "phases"
        if phases_dir.is_dir():
            return PlanType.COMPLEX
        return PlanType.SIMPLE

    def get_review_stages(self) -> list[Path]:
        """Return ordered list of files to review (phases + master for complex plans)."""
        if self.detect_plan_type() == PlanType.SIMPLE:
            return [self.find_plan_file()]

        phases_dir = self.active_plans_dir / self.plan_slug / "phases"
        phase_files = list(phases_dir.glob("phase_*.md"))

        def _phase_sort_key(p: Path) -> int:
            m = re.search(r"phase_(\d+)_", p.name)
            return int(m.group(1)) if m else 0

        phase_files.sort(key=_phase_sort_key)
        master = self.find_plan_file()
        return phase_files + [master]

    def find_plan_file(self) -> Path:
        """Locate the plan file on disk (master plan or simple plan).

        Raises:
            FileNotFoundError: If no plan file is found.
        """
        if self.detect_plan_type() == PlanType.COMPLEX:
            path = (
                self.active_plans_dir
                / self.plan_slug
                / f"{self.plan_slug}_master_plan.md"
            )
            if path.exists():
                return path
            raise FileNotFoundError(
                f"Master plan not found: {path}"
            )

        # Simple plan: try two naming conventions
        path1 = self.active_plans_dir / f"{self.plan_slug}.md"
        if path1.exists():
            return path1

        path2 = (
            self.active_plans_dir / self.plan_slug / f"{self.plan_slug}_plan.md"
        )
        if path2.exists():
            return path2

        raise FileNotFoundError(
            f"Plan file not found. Tried:\n  {path1}\n  {path2}"
        )

    def scan_existing_rounds(self) -> tuple[int, int]:
        """Scan the reviews directory for the highest review and response round numbers.

        Returns:
            Tuple of ``(max_review_round, max_response_round)``.
        """
        if not self.reviews_dir.is_dir():
            return (0, 0)

        round_re = re.compile(r"_round(\d+)\.md$")

        if self.mode == Mode.CODE:
            review_pattern = (
                f"{self.slug}_phase_{self.phase}_task_{self.task}"
                f"_code_review_round*.md"
            )
            response_pattern = (
                f"{self.slug}_phase_{self.phase}_task_{self.task}"
                f"_coder_response_round*.md"
            )
        elif self.stage_label is not None:
            review_pattern = (
                f"{self.slug}_{self.stage_label}_review_round*.md"
            )
            response_pattern = (
                f"{self.slug}_{self.stage_label}_update_round*.md"
            )
        else:
            review_pattern = f"{self.slug}_plan_review_round*.md"
            response_pattern = f"{self.slug}_plan_update_round*.md"

        max_review = 0
        for f in self.reviews_dir.glob(review_pattern):
            m = round_re.search(f.name)
            if m:
                max_review = max(max_review, int(m.group(1)))

        max_response = 0
        for f in self.reviews_dir.glob(response_pattern):
            m = round_re.search(f.name)
            if m:
                max_response = max(max_response, int(m.group(1)))

        return (max_review, max_response)
