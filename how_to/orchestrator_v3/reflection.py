"""Evolutionary reflection: structured LLM analysis of campaign review patterns.

Builds a reflection prompt from campaign metrics and failing artifact contents,
invokes the reviewer backend, and returns the reflection text for inclusion in
the postmortem report.
"""

from __future__ import annotations

import logging
from pathlib import Path

from orchestrator_v3.postmortem import CampaignMetrics, CampaignScanResult
from orchestrator_v3.reviewer import ReviewerBase

logger = logging.getLogger(__name__)


def select_failing_artifacts(scan: CampaignScanResult) -> dict[str, str]:
    """Select artifact contents from non-approved rounds.

    Returns a dict mapping artifact path (relative name) to file content.
    Only includes artifacts where ``verdict != "APPROVED"`` to fit within
    the LLM context window.
    """
    result: dict[str, str] = {}
    for art in scan.artifacts:
        if art.verdict != "APPROVED" and art.path.exists():
            try:
                result[art.path.name] = art.path.read_text()
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Skipping unreadable artifact %s: %s", art.path.name, exc)
    return result


def build_reflection_prompt(
    metrics: CampaignMetrics,
    artifact_contents: dict[str, str],
) -> str:
    """Build a structured reflection prompt for LLM analysis.

    The prompt instructs the LLM to analyze campaign patterns and produce
    actionable recommendations for improving author guidance and preflight
    checks.
    """
    lines: list[str] = []

    lines.append("# Evolutionary Reflection — Campaign Analysis")
    lines.append("")
    lines.append(
        "You are analyzing the review history of a coder-reviewer campaign "
        "to identify patterns and propose improvements. Your output will be "
        "appended to the campaign's postmortem report."
    )
    lines.append("")

    # Campaign metrics context
    lines.append("## Campaign Metrics")
    lines.append("")
    lines.append(f"- Slug: {metrics.slug}")
    lines.append(f"- Total tasks: {metrics.total_tasks}")
    lines.append(f"- Total rounds: {metrics.total_rounds}")
    lines.append(
        f"- First-round approval rate: "
        f"{metrics.first_round_approvals}/{metrics.total_tasks} "
        f"({metrics.first_round_approval_rate:.0%})"
    )
    lines.append(
        f"- Average rounds to approval: {metrics.avg_rounds_to_approval:.1f}"
    )
    lines.append(f"- Total blockers: {metrics.total_blockers}")
    lines.append(f"- Total majors: {metrics.total_majors}")
    lines.append(f"- Total minors: {metrics.total_minors}")
    lines.append("")

    # Per-task summary
    lines.append("## Per-Task Summary")
    lines.append("")
    for tm in metrics.tasks_detail:
        if tm.phase is not None and tm.task is not None:
            task_id = f"Phase {tm.phase}, Task {tm.task}"
        elif tm.label:
            task_id = tm.label
        else:
            task_id = "Unknown"
        approved_str = f"R{tm.rounds_to_approval}" if tm.rounds_to_approval else "not approved"
        lines.append(f"- **{task_id}** ({tm.mode}): {approved_str}")
        for rd in tm.round_details:
            findings = []
            if rd.blocker:
                findings.append(f"{rd.blocker}B")
            if rd.major:
                findings.append(f"{rd.major}M")
            if rd.minor:
                findings.append(f"{rd.minor}m")
            finding_str = ", ".join(findings) if findings else "clean"
            lines.append(
                f"  - Round {rd.round}: {rd.verdict or '?'} ({finding_str})"
            )
    lines.append("")

    # Artifact contents (failing rounds only)
    if artifact_contents:
        lines.append("## Review Artifacts (Non-Approved Rounds)")
        lines.append("")
        for name, content in sorted(artifact_contents.items()):
            lines.append(f"### {name}")
            lines.append("")
            lines.append("~~~markdown")
            lines.append(content)
            lines.append("~~~")
            lines.append("")

    # Instructions
    lines.append("## Your Task")
    lines.append("")
    lines.append(
        "Analyze the campaign metrics and review artifacts above. "
        "Produce a structured reflection with the following sections:"
    )
    lines.append("")
    lines.append("### 1. Pattern Identification")
    lines.append(
        "Identify recurring patterns in reviewer feedback. What types of "
        "issues appear most frequently? Reference at least 2 specific "
        "finding IDs (e.g., B1, M1, N2) from the artifacts."
    )
    lines.append("")
    lines.append("### 2. Root Cause Classification")
    lines.append(
        "Classify the root causes of reviewer findings into categories: "
        "format issues, missing content, logic errors, test gaps, "
        "specification ambiguity. Count how many findings fall into each."
    )
    lines.append("")
    lines.append("### 3. Guidance Recommendations")
    lines.append(
        "Propose at least 3 specific additions to the author guidance "
        "checklists (printed in the waiting banner). For each recommendation, "
        "provide the exact text that should be added to the checklist."
    )
    lines.append("")
    lines.append("### 4. Preflight Recommendations")
    lines.append(
        "Propose at least 2 specific additions to the preflight validation "
        "checks. For each recommendation, describe: what the check should "
        "verify, what error message it should produce, and whether it applies "
        "to code mode, plan mode, or both."
    )
    lines.append("")
    lines.append("### 5. Reviewer Consistency")
    lines.append(
        "Flag any reviewer inconsistencies or false positives you observe. "
        "Did the reviewer contradict itself across rounds? Did it raise "
        "findings that were already addressed? Were severity classifications "
        "appropriate?"
    )
    lines.append("")

    return "\n".join(lines)


def _extract_reflection_from_log(log_path: Path) -> str | None:
    """Extract reflection sections from Codex stdout log.

    When Codex outputs to stdout instead of writing to a file, the
    reflection content is captured in the log.  We find the last
    occurrence of the first section heading (which is the actual output,
    not the prompt echo) and return everything from there.
    """
    content = log_path.read_text()
    marker = "## 1. Pattern Identification"
    idx = content.rfind(marker)
    if idx < 0:
        return None
    text = content[idx:].strip()
    # Remove trailing Codex metadata (e.g., "tokens used\n1234")
    for suffix in ("tokens used",):
        pos = text.rfind(suffix)
        if pos > 0:
            text = text[:pos].strip()
    return text if text else None


def run_reflection(
    prompt: str,
    output_path: Path,
    reviewer: ReviewerBase,
) -> str | None:
    """Invoke the LLM to generate the evolutionary reflection.

    Uses the same reviewer backend interface. Returns the reflection text
    on success, or None on failure.  Falls back to extracting from the
    log file when Codex outputs to stdout instead of writing to a file.
    """
    log_path = output_path.with_suffix(".log")

    success = reviewer.run_review(
        prompt=prompt,
        review_file=output_path,
        log_file=log_path,
    )

    if not success:
        return None

    # Prefer the review file if Codex wrote it directly
    if output_path.exists():
        return output_path.read_text()

    # Fall back to extracting reflection from stdout log
    if log_path.exists():
        logger.info("Review file not created; extracting from log: %s", log_path)
        return _extract_reflection_from_log(log_path)

    return None
