"""Terminal display module for orchestrator_v3.

Provides ANSI-colored output functions for banners, status, info,
and history.  Respects the NO_COLOR environment variable convention.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator_v3.config import OrchestratorSettings
    from orchestrator_v3.state import OrchestratorState

# ── ANSI constants (NO_COLOR support) ────────────────────────────────

if os.environ.get("NO_COLOR") is not None:
    BOLD = GREEN = RED = YELLOW = CYAN = DIM = RESET = ""
else:
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    RESET = "\033[0m"

_STATUS_COLOR = {
    "approved": GREEN,
    "complete": GREEN,
    "needs_response": YELLOW,
    "needs_review": CYAN,
    "error": RED,
}


# ── Banner functions (called by OrchestratorLoop) ────────────────────

def print_header(mode: str, slug: str, settings: "OrchestratorSettings") -> None:
    """Print the session header banner with mode, slug, and settings."""
    border = "=" * 50
    title = f"=== {mode.upper()} MODE: {slug} ==="
    print(border)
    print(f"{BOLD}{CYAN}{title}{RESET}")
    print(f"  Max Rounds: {settings.default_max_rounds}")
    print(f"  Model: {settings.default_model}")
    print(f"  Reviews Dir: {settings.reviews_dir}")
    print(border)


def print_round_header(round_num: int, max_rounds: int = 0, stage_label: str | None = None) -> None:
    """Print a round separator with round number and optional stage label."""
    label = f"--- ROUND {round_num} of {max_rounds} ---" if max_rounds else f"--- ROUND {round_num} ---"
    if stage_label:
        label += f" [{stage_label}]"
    print(f"\n{BOLD}{YELLOW}{label}{RESET}")


def print_approved_banner(mode: str = "", round: int = 0, plan_type: str | None = None, **kwargs) -> None:
    """Print a green approval banner with mode and round number."""
    label = "PLAN STAGE APPROVED" if plan_type else (
        "PLAN APPROVED" if mode == "plan" else "CODE APPROVED"
    )
    border = "*" * 40
    print(f"\n{GREEN}{BOLD}{border}")
    print(f"  {label} (round {round})")
    print(f"{border}{RESET}\n")


def print_waiting_banner(
    mode: str,
    round: int,
    review_file: str,
    response_file: str,
    plan_type: str | None = None,
    stage_label: str | None = None,
    **kwargs,
) -> None:
    """Print a pause banner with instructions for the coder/planner response."""
    header = f"PAUSED — {mode.upper()} review round {round}"
    if stage_label:
        header += f" [{stage_label}]"
    action = "coder response" if mode == "code" else "planner update"
    print(f"\n{YELLOW}{BOLD}{header}{RESET}")
    print(f"{YELLOW}  Read the review:{RESET}")
    print(f"    {review_file}")
    print(f"{YELLOW}  Create your {action}:{RESET}")
    print(f"    {response_file}")
    print(f"{YELLOW}  Then re-run with --resume{RESET}")

    # Author guidance checklist
    if mode == "code":
        _print_code_guidance()
    else:
        _print_plan_guidance()
    print()


def _print_code_guidance() -> None:
    """Print code-mode author guidance checklist."""
    print(f"\n{CYAN}{BOLD}  Author Checklist (code artifact):{RESET}")
    print(f"{CYAN}    [ ] File: headings for each modified file (no ### prefix){RESET}")
    print(f"{CYAN}    [ ] ~~~diff fenced blocks with real unified diffs{RESET}")
    print(f"{CYAN}    [ ] Test: lines showing verification commands and results{RESET}")
    print(f"{CYAN}    [ ] Summary section describing what was implemented{RESET}")
    print(f"{CYAN}    [ ] SHA-256 hash verification for large/binary files{RESET}")
    print(f"{CYAN}    [ ] Task completion checklist with [x] marks{RESET}")


def _print_plan_guidance() -> None:
    """Print plan-mode author guidance checklist."""
    print(f"\n{CYAN}{BOLD}  Author Checklist (plan artifact):{RESET}")
    print(f"{CYAN}    [ ] Address each finding by ID (B1, M1, N1, etc.){RESET}")
    print(f"{CYAN}    [ ] Section headings present and properly formatted{RESET}")
    print(f"{CYAN}    [ ] Subtask numbering follows N.1, N.2 pattern{RESET}")
    print(f"{CYAN}    [ ] Acceptance gates are measurable and verifiable{RESET}")
    print(f"{CYAN}    [ ] Status table updated for each finding (FIXED/WONTFIX){RESET}")


def print_preflight_failure(result) -> None:
    """Print a formatted preflight failure report."""
    print(f"\n{RED}{BOLD}PREFLIGHT FAILED — artifact not ready for review{RESET}")
    for check in result.checks:
        if check.passed:
            print(f"  {GREEN}PASS{RESET} {check.name}: {check.message}")
        else:
            print(f"  {RED}FAIL{RESET} {check.name}: {check.message}")
    print(f"{YELLOW}Fix the issues above, then re-run with --resume{RESET}\n")


def print_verification_failure(result) -> None:
    """Print a formatted plan verification failure report.

    Renders ``PlanVerificationResult`` failures with line numbers, severity
    coloring, and actionable suggestions — matching the ``print_preflight_failure``
    pattern but specialised for structural plan verification.
    """
    print(f"\n{RED}{BOLD}PLAN VERIFICATION FAILED{RESET}")
    for issue in result.issues:
        if issue.severity == "error":
            prefix = f"{RED}ERROR{RESET}"
        else:
            prefix = f"{YELLOW}WARNING{RESET}"
        line_info = f" (line {issue.line_number})" if issue.line_number else ""
        print(f"  {prefix}{line_info}: {issue.message}")
        if issue.suggestion:
            print(f"    {CYAN}Suggestion:{RESET} {issue.suggestion}")
    error_count = sum(1 for i in result.issues if i.severity == "error")
    warning_count = sum(1 for i in result.issues if i.severity == "warning")
    print(
        f"{YELLOW}{error_count} error{'s' if error_count != 1 else ''}, "
        f"{warning_count} warning{'s' if warning_count != 1 else ''} "
        f"— fix errors before resubmitting{RESET}\n"
    )


def print_max_rounds_banner(max_rounds: int, mode: str = "", stage_label: str | None = None) -> None:
    """Print an error banner when max review rounds are exhausted."""
    msg = f"ERROR: Max rounds ({max_rounds}) reached without approval"
    if stage_label:
        msg += f" [{stage_label}]"
    msg += "."
    print(f"\n{RED}{BOLD}{msg}{RESET}")
    print(f"{RED}Increase --max-rounds or review feedback manually.{RESET}\n")


def print_retry_banner() -> None:
    """Print an error banner when the reviewer process fails."""
    print(
        f"\n{RED}{BOLD}Reviewer failed. "
        f"Re-run the same command to retry.{RESET}\n"
    )


def print_dry_run(prompt: str) -> None:
    """Print the prompt that would be sent in a real run."""
    border = "-" * 40
    print(f"\n{DIM}{border}")
    print("DRY RUN — prompt that would be sent:")
    print(f"{border}{RESET}")
    print(prompt)
    print(f"{DIM}{border}{RESET}\n")


def print_stage_header(
    stage_num: int, total_stages: int, stage_label: str, file_path: str,
) -> None:
    """Print a stage header for complex plan reviews."""
    print(f"\n{CYAN}{BOLD}=== Stage {stage_num + 1}/{total_stages}: {stage_label} ==={RESET}")
    print(f"  File: {file_path}")


def print_stage_approved(stage_label: str, rounds: int) -> None:
    """Print a stage approval message for complex plan reviews."""
    print(f'{GREEN}Stage "{stage_label}" approved after {rounds} round(s).{RESET}')


# ── Research-mode banners ─────────────────────────────────────────────

def print_research_header(slug: str, question: str, intent: str) -> None:
    """Print the research session header banner."""
    border = "=" * 50
    print(border)
    print(f"{BOLD}{CYAN}=== RESEARCH MODE: {slug} ==={RESET}")
    print(f"  Intent: {intent}")
    print(f"  Question: {question[:80]}{'...' if len(question) > 80 else ''}")
    print(border)


def print_research_phase(phase: int, phase_name: str) -> None:
    """Print a research phase separator."""
    print(f"\n{BOLD}{YELLOW}--- PHASE {phase}: {phase_name} ---{RESET}")


def print_research_model_call(model_name: str, phase: int, round_num: int | None = None) -> None:
    """Print a per-model call banner."""
    label = f"  [{model_name}] Phase {phase}"
    if round_num is not None:
        label += f", Round {round_num}"
    print(f"{CYAN}{label}{RESET}")


def print_research_convergence_status(
    round_num: int,
    opus_agree: int | None,
    codex_agree: int | None,
    issues: int | None,
) -> None:
    """Print convergence status after a round."""
    opus_str = str(opus_agree) if opus_agree is not None else "?"
    codex_str = str(codex_agree) if codex_agree is not None else "?"
    issues_str = str(issues) if issues is not None else "?"
    print(
        f"  {DIM}Round {round_num}: "
        f"Opus agreement={opus_str}, "
        f"Codex agreement={codex_str}, "
        f"Open issues={issues_str}{RESET}"
    )


def print_research_converged(round_num: int) -> None:
    """Print a green convergence success banner."""
    border = "*" * 40
    print(f"\n{GREEN}{BOLD}{border}")
    print(f"  CONVERGED (round {round_num})")
    print(f"{border}{RESET}\n")


def print_research_max_rounds(max_rounds: int) -> None:
    """Print a yellow warning when max convergence rounds reached."""
    print(
        f"\n{YELLOW}{BOLD}Max convergence rounds ({max_rounds}) reached "
        f"without full agreement. Proceeding to synthesis.{RESET}\n"
    )


def print_research_failure(phase: int, model: str, reason: str) -> None:
    """Print a research mode failure with phase, model, and reason."""
    print(f"\n{RED}{BOLD}RESEARCH ERROR — Phase {phase}, {model}{RESET}")
    print(f"  {RED}{reason}{RESET}")
    print(f"  {YELLOW}Fix the issue and re-run the research command.{RESET}\n")


def print_research_meta_missing(model: str, round_num: int) -> None:
    """Print a warning when RESEARCH_META block is missing from a convergence artifact."""
    print(
        f"  {YELLOW}WARNING: {model} convergence round {round_num} "
        f"has no RESEARCH_META block — treating as not converged.{RESET}"
    )


def print_research_complete(synthesis_path: str) -> None:
    """Print research completion with synthesis file path."""
    print(f"\n{GREEN}{BOLD}Research complete.{RESET}")
    print(f"  Synthesis: {synthesis_path}")


# ── Query functions (called by CLI commands) ─────────────────────────

def print_status(state: "OrchestratorState") -> None:
    """Print a one-line status summary (used by ``orchestrator_v3 status``).

    Works with OrchestratorState, TaskState, or CampaignIndex using getattr fallbacks.
    """
    # Extract fields with fallbacks for different state types
    slug = getattr(state, 'plan_slug', None) or getattr(state, 'slug', '?')
    phase = getattr(state, 'current_phase', None)
    if phase is None:
        phase = getattr(state, 'phase', '?')
    task = getattr(state, 'current_task', None)
    if task is None:
        task = getattr(state, 'task', '?')
    round_num = getattr(state, 'current_round', '?')
    status = getattr(state, 'status', 'unknown')

    color = _STATUS_COLOR.get(status, RED)
    print(
        f"{slug}: Phase {phase}, "
        f"Task {task}, Round {round_num} "
        f"-- {color}{status}{RESET}"
    )


def print_info(state: "OrchestratorState", settings: "OrchestratorSettings") -> None:
    """Print detailed progress info (used by ``orchestrator_v3 info``).

    Works with OrchestratorState, TaskState, or CampaignIndex using getattr fallbacks.
    """
    # Extract fields with fallbacks
    slug = getattr(state, 'plan_slug', None) or getattr(state, 'slug', '?')
    mode = getattr(state, 'mode', '?')
    plan_file = getattr(state, 'plan_file', None)
    phase = getattr(state, 'current_phase', None)
    if phase is None:
        phase = getattr(state, 'phase', '?')
    task = getattr(state, 'current_task', None)
    if task is None:
        task = getattr(state, 'task', '?')
    round_num = getattr(state, 'current_round', '?')
    status = getattr(state, 'status', 'unknown')
    started_at = getattr(state, 'started_at', '?')
    last_updated = getattr(state, 'last_updated', '?')

    print(f"{BOLD}{CYAN}=== Orchestrator Info: {slug} ==={RESET}")
    color = _STATUS_COLOR.get(status, "")
    print(f"{'Mode:':>16} {mode}")
    print(f"{'Plan:':>16} {plan_file or '(not set)'}")
    print(
        f"{'Current:':>16} Phase {phase}, "
        f"Task {task}, Round {round_num}"
    )
    print(f"{'Status:':>16} {color}{status}{RESET}")
    print()

    # Progress section: only if total_phases exists
    total_phases = getattr(state, 'total_phases', None)
    tasks_per_phase = getattr(state, 'tasks_per_phase', None)
    if total_phases is not None and tasks_per_phase is not None:
        print(f"{'Progress:':>16}")
        current_phase = getattr(state, 'current_phase', None)
        if current_phase is None:
            current_phase = getattr(state, 'phase', 0)
        current_task = getattr(state, 'current_task', None)
        if current_task is None:
            current_task = getattr(state, 'task', 1)

        for phase_idx in range(total_phases):
            key = str(phase_idx)
            total_tasks = tasks_per_phase.get(key, 0)
            if phase_idx < current_phase:
                done = total_tasks
                marker = f" {GREEN}✓{RESET}"
            elif phase_idx == current_phase:
                done = current_task - 1
                if status in ("approved", "complete"):
                    done = current_task
                marker = " (current)"
            else:
                done = 0
                marker = f" {DIM}not started{RESET}"
            print(f"{'':>16} Phase {phase_idx}: {done}/{total_tasks} tasks{marker}")
        print()

    print(f"{'Started:':>16} {started_at}")
    print(f"{'Last Updated:':>16} {last_updated}")


def print_history(state: "OrchestratorState") -> None:
    """Print round-by-round review history table (used by ``orchestrator_v3 history``).

    Works with OrchestratorState or TaskState (both have history). CampaignIndex has no history.
    """
    history = getattr(state, 'history', None)
    if history is None:
        print(f"{DIM}No history available for this state type.{RESET}")
        return
    if not history:
        print(f"{DIM}No review history recorded.{RESET}")
        return
    print(f"{'Round':<7} {'Verdict':<18} {'B':>3} {'M':>3} {'m':>3}  Timestamp")
    print("-" * 65)
    for entry in history:
        verdict = entry.get("verdict", "?")
        color = GREEN if verdict.lower() == "approved" else YELLOW
        print(
            f"{entry.get('round', '?'):<7} "
            f"{color}{verdict:<18}{RESET} "
            f"{entry.get('blocker', 0):>3} "
            f"{entry.get('major', 0):>3} "
            f"{entry.get('minor', 0):>3}  "
            f"{entry.get('timestamp', '')}"
        )
