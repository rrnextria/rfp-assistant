"""Campaign postmortem: artifact scanning, metrics calculation, and report generation.

Scans review artifacts for a given campaign slug, extracts ORCH_META data,
computes aggregate metrics (rounds to approval, finding rates, etc.), and
generates a structured markdown report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator_v3.approval import ReviewResult, Verdict, parse_orch_meta
from orchestrator_v3.config import OrchestratorSettings


# ── Filename parsing patterns ─────────────────────────────────────────
#
# Observed patterns (precedence order):
# (a) code-mode per-task:  {slug}_phase_{P}_task_{T}_code_review_round{R}.md
# (b) plan-mode phase:     {slug}_phase_{P}_{label}_review_round{R}.md
# (c) plan-mode master:    {slug}_{slug}_master_plan_review_round{R}.md
# (d) plan-mode fallback:  {slug}_{label}_review_round{R}.md

_RE_CODE_TASK = re.compile(
    r"^(?P<slug>.+?)_phase_(?P<phase>\d+)_task_(?P<task>\d+)_code_review_round(?P<round>\d+)\.md$"
)
_RE_PLAN_PHASE = re.compile(
    r"^(?P<slug>.+?)_phase_(?P<phase>\d+)_(?P<label>[a-z][a-z0-9_]+)_review_round(?P<round>\d+)\.md$"
)
_RE_PLAN_MASTER_SUFFIX = re.compile(
    r"^(?P<plan_slug>[a-z][a-z0-9_]*)_master_plan_review_round(?P<round>\d+)\.md$"
)
_RE_PLAN_LABEL = re.compile(
    r"^(?P<slug>.+?)_(?P<label>[a-z][a-z0-9_]+)_review_round(?P<round>\d+)\.md$"
)


@dataclass
class ArtifactScan:
    """Parsed data from a single review artifact."""

    path: Path
    phase: int | None
    task: int | None
    label: str | None
    round: int
    mode: str  # "code" or "plan"
    verdict: str | None  # "APPROVED", "FIXES_REQUIRED", or None
    blocker: int = 0
    major: int = 0
    minor: int = 0
    decisions: int = 0
    verified: int = 0


@dataclass
class CampaignScanResult:
    """All scanned artifacts for a campaign."""

    slug: str
    artifacts: list[ArtifactScan] = field(default_factory=list)


def _parse_filename(slug: str, filename: str) -> dict | None:
    """Parse artifact filename into structured data.

    Returns dict with keys: phase, task, label, round, mode.
    Returns None if the filename doesn't match the expected slug or patterns.
    """
    if not filename.startswith(slug + "_"):
        return None

    # (a) Code-mode per-task
    m = _RE_CODE_TASK.match(filename)
    if m and m.group("slug") == slug:
        return {
            "phase": int(m.group("phase")),
            "task": int(m.group("task")),
            "label": None,
            "round": int(m.group("round")),
            "mode": "code",
        }

    # (c) Plan-mode master plan (check before (b) to avoid label capture)
    # Strip the known slug prefix and match the suffix directly.
    # This avoids a backreference that breaks when --slug overrides
    # the artifact slug to differ from the plan directory slug.
    rest = filename[len(slug) + 1:]  # guaranteed by startswith check above
    m = _RE_PLAN_MASTER_SUFFIX.match(rest)
    if m:
        return {
            "phase": None,
            "task": None,
            "label": f"{m.group('plan_slug')}_master_plan",
            "round": int(m.group("round")),
            "mode": "plan",
        }

    # (b) Plan-mode phase stage
    m = _RE_PLAN_PHASE.match(filename)
    if m and m.group("slug") == slug:
        label = m.group("label")
        # Exclude "task_N_code" which is handled by pattern (a)
        if not label.startswith("task_"):
            return {
                "phase": int(m.group("phase")),
                "task": None,
                "label": f"phase_{m.group('phase')}_{label}",
                "round": int(m.group("round")),
                "mode": "plan",
            }

    # (d) Plan-mode fallback (label only)
    m = _RE_PLAN_LABEL.match(filename)
    if m and m.group("slug") == slug:
        return {
            "phase": None,
            "task": None,
            "label": m.group("label"),
            "round": int(m.group("round")),
            "mode": "plan",
        }

    return None


def scan_campaign_artifacts(
    slug: str, settings: OrchestratorSettings
) -> CampaignScanResult:
    """Find all review artifacts for a campaign and extract ORCH_META data.

    Scans ``reviews/`` for files matching ``{slug}_*_review_round*.md``,
    parses structured data from filenames and ORCH_META blocks.
    """
    result = CampaignScanResult(slug=slug)
    reviews_dir = settings.reviews_dir

    if not reviews_dir.exists():
        return result

    # Glob for all review round files for this slug
    pattern = f"{slug}_*_review_round*.md"
    artifact_files = sorted(reviews_dir.glob(pattern))

    for path in artifact_files:
        parsed = _parse_filename(slug, path.name)
        if parsed is None:
            continue

        # Extract ORCH_META
        orch = parse_orch_meta(path)

        scan = ArtifactScan(
            path=path,
            phase=parsed["phase"],
            task=parsed["task"],
            label=parsed["label"],
            round=parsed["round"],
            mode=parsed["mode"],
            verdict=orch.verdict.value if orch else None,
            blocker=orch.blocker if orch else 0,
            major=orch.major if orch else 0,
            minor=orch.minor if orch else 0,
            decisions=orch.decisions if orch else 0,
            verified=orch.verified if orch else 0,
        )
        result.artifacts.append(scan)

    return result


# ── Metrics calculation ───────────────────────────────────────────────


@dataclass
class RoundDetail:
    """Per-round metrics for a single review round."""

    round: int
    verdict: str | None
    blocker: int = 0
    major: int = 0
    minor: int = 0
    decisions: int = 0
    verified: int = 0


@dataclass
class TaskMetrics:
    """Metrics for a single task (or plan stage)."""

    phase: int | None
    task: int | None
    label: str | None
    mode: str
    rounds_to_approval: int | None  # None if not yet approved
    round_details: list[RoundDetail] = field(default_factory=list)


@dataclass
class CampaignMetrics:
    """Aggregate campaign metrics."""

    slug: str
    total_tasks: int = 0
    total_rounds: int = 0
    first_round_approvals: int = 0
    first_round_approval_rate: float = 0.0
    avg_rounds_to_approval: float = 0.0
    total_blockers: int = 0
    total_majors: int = 0
    total_minors: int = 0
    finding_resolution_rate: float = 0.0
    avg_rounds_by_mode: dict[str, float] = field(default_factory=dict)
    tasks_detail: list[TaskMetrics] = field(default_factory=list)


def _task_key(scan: ArtifactScan) -> tuple:
    """Group key for artifacts belonging to the same task/stage."""
    if scan.mode == "code" and scan.phase is not None and scan.task is not None:
        return ("code", scan.phase, scan.task, None)
    return ("plan", scan.phase, scan.task, scan.label)


def calculate_metrics(scan: CampaignScanResult) -> CampaignMetrics:
    """Compute aggregate metrics from scan results."""
    metrics = CampaignMetrics(slug=scan.slug)

    if not scan.artifacts:
        return metrics

    # Group artifacts by task/stage
    groups: dict[tuple, list[ArtifactScan]] = {}
    for art in scan.artifacts:
        key = _task_key(art)
        groups.setdefault(key, []).append(art)

    # Sort each group by round
    for arts in groups.values():
        arts.sort(key=lambda a: a.round)

    approved_tasks = []
    mode_rounds: dict[str, list[int]] = {}
    total_findings_raised = 0
    total_verified_final = 0

    def _sort_key(item):
        """Sort key handling None values (None sorts before integers)."""
        key = item[0]
        return tuple(
            (0, v) if v is not None else (-1, "")
            for v in key
        )

    for key, arts in sorted(groups.items(), key=_sort_key):
        mode, phase, task, label = key

        round_details = [
            RoundDetail(
                round=a.round,
                verdict=a.verdict,
                blocker=a.blocker,
                major=a.major,
                minor=a.minor,
                decisions=a.decisions,
                verified=a.verified,
            )
            for a in arts
        ]

        # Determine rounds to approval
        rounds_to_approval = None
        for a in arts:
            if a.verdict == Verdict.APPROVED.value:
                rounds_to_approval = a.round
                break

        tm = TaskMetrics(
            phase=phase,
            task=task,
            label=label,
            mode=mode,
            rounds_to_approval=rounds_to_approval,
            round_details=round_details,
        )
        metrics.tasks_detail.append(tm)

        # Aggregate
        metrics.total_rounds += len(arts)
        for a in arts:
            metrics.total_blockers += a.blocker
            metrics.total_majors += a.major
            metrics.total_minors += a.minor
            total_findings_raised += a.blocker + a.major + a.minor

        # Verified count from final round of this task
        total_verified_final += arts[-1].verified

        if rounds_to_approval is not None:
            approved_tasks.append(rounds_to_approval)
            if rounds_to_approval == 1:
                metrics.first_round_approvals += 1

        mode_rounds.setdefault(mode, [])
        if rounds_to_approval is not None:
            mode_rounds[mode].append(rounds_to_approval)

    metrics.total_tasks = len(groups)
    if metrics.total_tasks > 0:
        metrics.first_round_approval_rate = (
            metrics.first_round_approvals / metrics.total_tasks
        )
    if approved_tasks:
        metrics.avg_rounds_to_approval = sum(approved_tasks) / len(approved_tasks)

    for mode, rounds_list in mode_rounds.items():
        if rounds_list:
            metrics.avg_rounds_by_mode[mode] = sum(rounds_list) / len(rounds_list)

    if total_findings_raised > 0:
        metrics.finding_resolution_rate = min(
            1.0, total_verified_final / total_findings_raised
        )

    return metrics


# ── Report generation ─────────────────────────────────────────────────


def generate_report(
    metrics: CampaignMetrics, reflection: str | None = None
) -> str:
    """Generate a structured markdown postmortem report."""
    lines: list[str] = []

    lines.append(f"# Campaign Postmortem: {metrics.slug}")
    lines.append("")

    # Campaign Summary
    lines.append("## Campaign Summary")
    lines.append("")
    lines.append(f"- **Total tasks/stages:** {metrics.total_tasks}")
    lines.append(f"- **Total review rounds:** {metrics.total_rounds}")
    lines.append(
        f"- **First-round approval rate:** "
        f"{metrics.first_round_approvals}/{metrics.total_tasks} "
        f"({metrics.first_round_approval_rate:.0%})"
    )
    lines.append(
        f"- **Average rounds to approval:** {metrics.avg_rounds_to_approval:.1f}"
    )
    lines.append(f"- **Total blockers raised:** {metrics.total_blockers}")
    lines.append(f"- **Total majors raised:** {metrics.total_majors}")
    lines.append(f"- **Total minors raised:** {metrics.total_minors}")
    lines.append(
        f"- **Finding resolution rate:** {metrics.finding_resolution_rate:.0%}"
    )
    lines.append("")

    # Per-Task Breakdown
    lines.append("## Per-Task Breakdown")
    lines.append("")
    lines.append(
        "| Phase | Task | Label | Mode | Rounds | Approved | Verdicts |"
    )
    lines.append(
        "|-------|------|-------|------|--------|----------|----------|"
    )

    for tm in metrics.tasks_detail:
        phase_str = str(tm.phase) if tm.phase is not None else "—"
        task_str = str(tm.task) if tm.task is not None else "—"
        label_str = tm.label or "—"
        approved_str = (
            f"R{tm.rounds_to_approval}" if tm.rounds_to_approval else "N/A"
        )
        verdicts = " → ".join(
            (rd.verdict or "?") for rd in tm.round_details
        )
        lines.append(
            f"| {phase_str} | {task_str} | {label_str} | {tm.mode} "
            f"| {len(tm.round_details)} | {approved_str} | {verdicts} |"
        )

    lines.append("")

    # Metrics
    lines.append("## Metrics")
    lines.append("")
    if metrics.avg_rounds_by_mode:
        for mode, avg in sorted(metrics.avg_rounds_by_mode.items()):
            lines.append(
                f"- **Average rounds ({mode} mode):** {avg:.1f}"
            )
    lines.append("")

    # Evolutionary Reflection (optional)
    if reflection:
        lines.append("## Evolutionary Reflection")
        lines.append("")
        lines.append(reflection)
        lines.append("")

    return "\n".join(lines)


def write_report(
    slug: str, report_content: str, settings: OrchestratorSettings
) -> Path:
    """Write the postmortem report to reviews/{slug}_postmortem.md."""
    output_path = settings.reviews_dir / f"{slug}_postmortem.md"
    output_path.write_text(report_content)
    return output_path
