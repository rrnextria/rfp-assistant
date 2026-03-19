"""Typer CLI for orchestrator_v3 — plan and code review loop automation.

Provides commands: ``plan``, ``code``, ``status``, ``info``, ``history``,
``validate``, ``research``, ``postmortem``, and ``plan-verify``.
Each command is exposed via the shell wrapper
``python -m orchestrator_v3`` (e.g. ``python -m orchestrator_v3 plan ...``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

import functools

import click
import typer

from orchestrator_v3 import display
from orchestrator_v3.artifacts import ArtifactResolver
from orchestrator_v3.config import (
    Mode,
    OrchestratorSettings,
    PlanType,
    Status,
    _env_int,
    _env_str,
)
from orchestrator_v3.loop import OrchestratorLoop
from orchestrator_v3.plan_tool import (
    plan_reconcile,
    plan_render_master,
    plan_sync,
    verify_plan_syntax,
)
from orchestrator_v3.prompts import PromptBuilder
from orchestrator_v3.reviewer import CodexReviewer, MockReviewer
from orchestrator_v3.state import (
    CampaignManager,
    StateManager,
    TaskStateManager,
    campaign_index_path,
    task_state_path,
)

class _BootstrapGroup(typer.core.TyperGroup):
    """Custom Click Group that runs bootstrap before subcommand execution.

    This is the shared app-level hook required by Task 2.1.  It wraps each
    subcommand's ``invoke()`` so that ``_bootstrap_maistro_dirs()`` runs
    exactly once, after Click has finished ``--help`` processing (which exits
    inside ``make_context()``) but before the command body executes.  This
    avoids the Typer ``@app.callback`` problem where the callback fires
    *before* ``--help`` processing and no Click context attribute can
    distinguish help from normal invocation.
    """

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None and not getattr(cmd, "_bootstrap_wrapped", False):
            original_invoke = cmd.invoke

            @functools.wraps(original_invoke)
            def _bootstrapped_invoke(ctx: click.Context) -> object:
                _bootstrap_maistro_dirs()
                return original_invoke(ctx)

            cmd.invoke = _bootstrapped_invoke  # type: ignore[assignment]
            cmd._bootstrap_wrapped = True  # type: ignore[attr-defined]
        return cmd


app = typer.Typer(
    no_args_is_help=True,
    help="Orchestrator V3 -- plan and code review loop automation.",
    cls=_BootstrapGroup,
)


def _bootstrap_maistro_dirs() -> None:
    """Create maistro/sessions/ at repo root and ensure maistro/ is gitignored.

    Called via the shared ``_BootstrapGroup`` app-level hook before any
    subcommand executes.  The hook intercepts at the Click Group level so
    ``--help`` (which exits during ``make_context()``) never triggers bootstrap.
    """
    from orchestrator_v3.config import detect_repo_root

    repo_root = detect_repo_root()
    sessions_dir = repo_root / "maistro" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    gitignore = repo_root / ".gitignore"
    marker = "maistro/"
    if gitignore.exists():
        content = gitignore.read_text()
        if marker not in content.splitlines():
            with gitignore.open("a") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(f"\n# Maistro runtime data (auto-created)\n{marker}\n")
    else:
        gitignore.write_text(f"# Maistro runtime data (auto-created)\n{marker}\n")


def _run_env_preflight(command: str) -> None:
    """Run environment checks and abort on any FAIL result."""
    from orchestrator_v3.env_checks import run_env_checks

    results = run_env_checks(command)
    failures = [r for r in results if r.status == "FAIL"]
    if failures:
        typer.echo(
            f"\n{display.RED}{display.BOLD}ENVIRONMENT CHECK FAILED{display.RESET}",
            err=True,
        )
        for r in results:
            if r.status == "PASS":
                typer.echo(f"  {display.GREEN}PASS{display.RESET} {r.name}: {r.message}", err=True)
            elif r.status == "WARN":
                typer.echo(f"  {display.YELLOW}WARN{display.RESET} {r.name}: {r.message}", err=True)
            else:
                typer.echo(f"  {display.RED}FAIL{display.RESET} {r.name}: {r.message}", err=True)
                if r.fix_hint:
                    typer.echo(f"         {display.CYAN}Fix: {r.fix_hint}{display.RESET}", err=True)
        raise typer.Exit(code=1)


def _derive_slug(plan_file: Path) -> str:
    """Derive project slug from plan file path."""
    stem = plan_file.stem
    for suffix in ("_master_plan", "_plan"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def _state_path(slug: str, settings: OrchestratorSettings) -> Path:
    return settings.reviews_dir / f"{slug}_orchestrator_state.json"


def _guard_init(state_path: Path, force: bool, label: str) -> None:
    """Abort if --init would overwrite existing state without --force."""
    if state_path.exists() and not force:
        typer.echo(
            f"{display.RED}ERROR: State already exists for {label}: "
            f"{state_path}{display.RESET}\n"
            f"  Use --resume to continue, or --init --force to overwrite.",
            err=True,
        )
        raise typer.Exit(code=1)


def _guard_flags(init: bool, resume: bool, state_path: Path, label: str) -> None:
    """Validate flag combinations and state existence.

    Rules:
    - --init and --resume are mutually exclusive.
    - If state exists and neither flag is given, error with guidance.
    """
    if init and resume:
        typer.echo(
            f"{display.RED}ERROR: --init and --resume are mutually exclusive.{display.RESET}\n"
            f"  Use --init to start fresh, or --resume to continue.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not init and not resume and state_path.exists():
        typer.echo(
            f"{display.RED}ERROR: State already exists for {label}: "
            f"{state_path}{display.RESET}\n"
            f"  Use --resume to continue from where you left off.\n"
            f"  Use --init --force to discard existing state and start over.",
            err=True,
        )
        raise typer.Exit(code=1)


def _count_tasks_per_phase(ar: ArtifactResolver) -> tuple[int, dict[str, int]]:
    """Parse phase plan files to count tasks per phase."""
    stages = ar.get_review_stages()
    phase_files = [s for s in stages if "phase_" in s.name]
    task_re = re.compile(r"^### \[[ x✅]\] (\d+)")
    tasks_per_phase: dict[str, int] = {}
    for i, pf in enumerate(phase_files):
        task_numbers = set()
        for line in pf.read_text().splitlines():
            m = task_re.match(line)
            if m:
                task_numbers.add(int(m.group(1)))
        tasks_per_phase[str(i)] = len(task_numbers) if task_numbers else 1
    total_phases = len(phase_files) if phase_files else 1
    if not phase_files:
        tasks_per_phase["0"] = 1
    return total_phases, tasks_per_phase


@app.command()
def plan(
    plan_file: Path = typer.Argument(..., help="Path to the plan file to review"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last checkpoint"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt without invoking reviewer"),
    max_rounds: int = typer.Option(5, "--max-rounds", help="Maximum review rounds"),
    model: str = typer.Option(_env_str("MAISTRO_CODEX_MODEL", "gpt-5.4"), "--model", help="Reviewer model (DO NOT pass this flag unless the user explicitly asks — the default is correct)"),
    timeout: int = typer.Option(_env_int("MAISTRO_TIMEOUT", 1800), "--timeout", help="Reviewer wall-clock timeout in seconds"),
    idle_timeout: int = typer.Option(_env_int("MAISTRO_IDLE_TIMEOUT", 600), "--idle-timeout", help="Kill reviewer after N seconds of no output"),
    reasoning_effort: str = typer.Option(_env_str("MAISTRO_CODEX_REASONING", "high"), "--reasoning-effort", help="Codex reasoning effort level (low/medium/high)"),
    mock_reviewer: Optional[Path] = typer.Option(None, "--mock-reviewer", help="Directory with mock review files"),
    init: bool = typer.Option(False, "--init", help="Initialize state for a new review session"),
    force: bool = typer.Option(False, "--force", help="Force --init even if state already exists"),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip preflight validation checks"),
    slug_override: Optional[str] = typer.Option(None, "--slug", help="Override slug (default: derived from plan filename)"),
) -> None:
    """Run the plan review loop.

    The default model and reasoning effort are pre-configured. Do NOT pass
    --model unless the user explicitly asks you to change it.

    Examples:
        python -m orchestrator_v3 plan active_plans/my_plan/my_plan_master_plan.md
        python -m orchestrator_v3 plan plan.md --dry-run
        python -m orchestrator_v3 plan plan.md --resume --max-rounds 5
        python -m orchestrator_v3 plan plan.md --mock-reviewer fixtures/
        python -m orchestrator_v3 plan plan.md --slug my_custom_slug
    """
    if not skip_preflight:
        _run_env_preflight("plan")

    derived_slug = _derive_slug(plan_file)
    slug = slug_override if slug_override else derived_slug
    # When slug is overridden, plan_slug keeps the original directory name
    plan_slug_val = derived_slug if slug_override else None
    settings = OrchestratorSettings(
        repo_root=Path.cwd(),
        default_max_rounds=max_rounds,
        default_model=model,
    )

    sm = StateManager(state_path=_state_path(slug, settings), settings=settings)
    ar = ArtifactResolver(slug=slug, mode=Mode.PLAN, phase=0, task=1, settings=settings, plan_slug=plan_slug_val)

    _guard_flags(init, resume, sm.state_path, f"plan '{slug}'")
    if init:
        _guard_init(sm.state_path, force, f"plan '{slug}'")

    # Verification gate: complex plan --init verifies master before state init
    if (init or not sm.state_path.exists()) and not skip_preflight:
        _plan_type_check = ar.detect_plan_type()
        if _plan_type_check == PlanType.COMPLEX:
            vr = verify_plan_syntax(
                plan_file, settings=settings, check_cross_file=True
            )
            if not vr.passed:
                display.print_verification_failure(vr)
                raise typer.Exit(code=1)
            # Log warnings but continue
            if vr.warnings > 0:
                for issue in vr.issues:
                    if issue.severity == "warning":
                        line_info = f" (line {issue.line_number})" if issue.line_number else ""
                        typer.echo(
                            f"Plan verification warning{line_info}: {issue.message}",
                            err=True,
                        )

    if init or not sm.state_path.exists():
        plan_type = ar.detect_plan_type()
        if plan_type == PlanType.COMPLEX:
            stages = ar.get_review_stages()
            stage_files = [str(s) for s in stages]
            total_stages = len(stages)
        else:
            stage_files = [str(plan_file)]
            total_stages = 1
        sm.init(
            plan_slug=slug,
            mode=Mode.PLAN,
            plan_file=str(plan_file),
            plan_type=plan_type,
            total_stages=total_stages,
            stage_files=stage_files,
        )

    # For complex plan resume: set stage_label on resolver so
    # determine_resume_point() uses the correct glob patterns.
    if resume and sm.state_path.exists():
        state = sm.load()
        if state.plan_type == PlanType.COMPLEX.value:
            stage_idx = state.current_stage
            stage_files = state.stage_files
            if stage_idx < len(stage_files):
                stage_label = Path(stage_files[stage_idx]).stem
                ar = ArtifactResolver(
                    slug=slug, mode=Mode.PLAN, phase=0, task=1,
                    settings=settings, stage_label=stage_label,
                    plan_slug=plan_slug_val,
                )

    pb = PromptBuilder(artifact_resolver=ar, mode=Mode.PLAN, slug=slug, model=model)
    reviewer = MockReviewer(mock_dir=mock_reviewer) if mock_reviewer else CodexReviewer(model=model, timeout=timeout, idle_timeout=idle_timeout, reasoning_effort=reasoning_effort)

    loop = OrchestratorLoop(
        state_manager=sm,
        artifact_resolver=ar,
        prompt_builder=pb,
        reviewer=reviewer,
        display=display,
        settings=settings,
        skip_preflight=skip_preflight,
    )

    from orchestrator_v3.run_recorder import RunRecorder

    display.print_header("plan", slug, settings)
    recorder = RunRecorder(mode="plan", slug=slug, repo_root=settings.repo_root, plan_slug=plan_slug_val or derived_slug, reviewer_model=model)
    with recorder:
        result = loop.run(start_round=1, max_rounds=max_rounds, dry_run=dry_run, resume=resume)
        # Determine outcome from state (loop returns 0 for both approved and paused)
        state = sm.load()
        recorder.outcome = state.status if result == 0 else "error"
        recorder.set_verdict_history(state.history)
        for entry in state.history:
            if entry.get("artifact"):
                recorder.add_artifact(entry["artifact"])
    raise typer.Exit(code=result)


@app.command()
def code(
    slug: str = typer.Argument(..., help="Project slug"),
    phase: int = typer.Argument(..., help="Phase number"),
    task: int = typer.Argument(..., help="Task number"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last checkpoint"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt without invoking reviewer"),
    max_rounds: int = typer.Option(5, "--max-rounds", help="Maximum review rounds"),
    model: str = typer.Option(_env_str("MAISTRO_CODEX_MODEL", "gpt-5.4"), "--model", help="Reviewer model (DO NOT pass this flag unless the user explicitly asks — the default is correct)"),
    timeout: int = typer.Option(_env_int("MAISTRO_TIMEOUT", 1800), "--timeout", help="Reviewer wall-clock timeout in seconds"),
    idle_timeout: int = typer.Option(_env_int("MAISTRO_IDLE_TIMEOUT", 600), "--idle-timeout", help="Kill reviewer after N seconds of no output"),
    reasoning_effort: str = typer.Option(_env_str("MAISTRO_CODEX_REASONING", "high"), "--reasoning-effort", help="Codex reasoning effort level (low/medium/high)"),
    mock_reviewer: Optional[Path] = typer.Option(None, "--mock-reviewer", help="Directory with mock review files"),
    init: bool = typer.Option(False, "--init", help="Initialize state for a new review session"),
    force: bool = typer.Option(False, "--force", help="Force --init even if state already exists"),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip preflight validation checks"),
    plan_slug: Optional[str] = typer.Option(None, "--plan-slug", help="Override plan directory slug (default: same as slug)"),
) -> None:
    """Run the code review loop.

    The default model and reasoning effort are pre-configured. Do NOT pass
    --model unless the user explicitly asks you to change it.

    Examples:
        python -m orchestrator_v3 code fp8_training 0 1
        python -m orchestrator_v3 code my_project 2 3 --dry-run
        python -m orchestrator_v3 code my_project 2 3 --resume --max-rounds 10
        python -m orchestrator_v3 code my_project 0 1 --mock-reviewer fixtures/
        python -m orchestrator_v3 code test_slug 0 1 --plan-slug real_plan_dir
    """
    if not skip_preflight:
        _run_env_preflight("code")

    settings = OrchestratorSettings(
        repo_root=Path.cwd(),
        default_max_rounds=max_rounds,
        default_model=model,
    )

    ar = ArtifactResolver(slug=slug, mode=Mode.CODE, phase=phase, task=task, settings=settings, plan_slug=plan_slug)

    # Per-task state file (v3): each (slug, phase, task) gets its own state
    tsm = TaskStateManager(state_path=task_state_path(slug, phase, task, settings))
    # Campaign index: tracks overall progress across tasks
    cm = CampaignManager(
        state_path=campaign_index_path(slug, settings), settings=settings,
    )

    _guard_flags(init, resume, tsm.state_path, f"code '{slug}' phase {phase} task {task}")
    if init:
        _guard_init(tsm.state_path, force, f"code '{slug}' phase {phase} task {task}")

    # Verification gate: verify master plan at CLI entry for code mode
    if not skip_preflight:
        if init or not tsm.state_path.exists():
            # --init path: resolve plan file and verify
            try:
                _code_plan_file = Path(str(ar.find_plan_file()))
            except FileNotFoundError:
                _code_plan_file = None
            if _code_plan_file is not None:
                vr = verify_plan_syntax(
                    _code_plan_file, settings=settings, check_cross_file=True
                )
                if not vr.passed:
                    display.print_verification_failure(vr)
                    raise typer.Exit(code=1)
                if vr.warnings > 0:
                    for issue in vr.issues:
                        if issue.severity == "warning":
                            line_info = f" (line {issue.line_number})" if issue.line_number else ""
                            typer.echo(
                                f"Plan verification warning{line_info}: {issue.message}",
                                err=True,
                            )
        elif resume and tsm.state_path.exists():
            # --resume path: load plan file from existing task state and verify
            _task_state = tsm.load()
            if _task_state.plan_file:
                _resume_plan = Path(_task_state.plan_file)
                if _resume_plan.exists():
                    vr = verify_plan_syntax(
                        _resume_plan, settings=settings, check_cross_file=True
                    )
                    if not vr.passed:
                        display.print_verification_failure(vr)
                        raise typer.Exit(code=1)
                    if vr.warnings > 0:
                        for issue in vr.issues:
                            if issue.severity == "warning":
                                line_info = f" (line {issue.line_number})" if issue.line_number else ""
                                typer.echo(
                                    f"Plan verification warning{line_info}: {issue.message}",
                                    err=True,
                                )

    if init or not tsm.state_path.exists():
        try:
            plan_file = str(ar.find_plan_file())
        except FileNotFoundError:
            typer.echo(
                f"{display.RED}ERROR: Plan file not found for slug '{slug}'.{display.RESET}\n"
                f"  Expected at: active_plans/{slug}.md\n"
                f"           or: active_plans/{slug}/{slug}_master_plan.md",
                err=True,
            )
            raise typer.Exit(code=1)
        tsm.init(
            slug=slug,
            phase=phase,
            task=task,
            plan_file=plan_file,
            mode=Mode.CODE,
        )

    if init or not cm.state_path.exists():
        plan_file = str(ar.find_plan_file())
        plan_type = ar.detect_plan_type()
        if plan_type == PlanType.COMPLEX:
            total_phases, tasks_per_phase = _count_tasks_per_phase(ar)
        else:
            total_phases = 1
            tasks_per_phase = {"0": 1}
        cm.init(
            slug=slug,
            mode=Mode.CODE,
            plan_file=plan_file,
            total_phases=total_phases,
            tasks_per_phase=tasks_per_phase,
            current_phase=phase,
            current_task=task,
        )

    pb = PromptBuilder(artifact_resolver=ar, mode=Mode.CODE, slug=slug, model=model)
    reviewer = MockReviewer(mock_dir=mock_reviewer) if mock_reviewer else CodexReviewer(model=model, timeout=timeout, idle_timeout=idle_timeout, reasoning_effort=reasoning_effort)

    loop = OrchestratorLoop(
        state_manager=tsm,
        artifact_resolver=ar,
        prompt_builder=pb,
        reviewer=reviewer,
        display=display,
        settings=settings,
        campaign_manager=cm,
        skip_preflight=skip_preflight,
    )

    # Set phase file for complex plans (code prompt includes Phase Plan context)
    if ar.detect_plan_type() == PlanType.COMPLEX:
        stages = ar.get_review_stages()
        phase_files = [s for s in stages if "phase_" in s.name]
        if phase < len(phase_files):
            loop._phase_file = str(phase_files[phase])

    from orchestrator_v3.run_recorder import RunRecorder

    display.print_header("code", slug, settings)
    recorder = RunRecorder(
        mode="code", slug=slug, repo_root=settings.repo_root,
        phase=phase, task=task, plan_slug=plan_slug or slug,
        reviewer_model=model,
    )
    with recorder:
        result = loop.run(start_round=1, max_rounds=max_rounds, dry_run=dry_run, resume=resume)
        state = tsm.load()
        recorder.outcome = state.status if result == 0 else "error"
        recorder.set_verdict_history(state.history)
        for entry in state.history:
            if entry.get("artifact"):
                recorder.add_artifact(entry["artifact"])
    raise typer.Exit(code=result)


def _load_state_for_query(slug, settings, phase=None, task=None):
    """Load the appropriate state object for query commands.

    With phase+task: loads per-task state. Without: tries campaign index
    first, then falls back to plan-mode orchestrator state.

    Raises:
        ValueError: If phase is given without task (or vice versa).
    """
    # Validate partial args
    if phase is not None and task is None:
        raise ValueError("Phase given but task is None. Provide both or neither.")
    if task is not None and phase is None:
        raise ValueError("Task given but phase is None. Provide both or neither.")

    if phase is not None and task is not None:
        ts_path = task_state_path(slug, phase, task, settings)
        tsm = TaskStateManager(state_path=ts_path)
        return tsm.load()

    # Try campaign index first (code-mode campaigns)
    ci_path = campaign_index_path(slug, settings)
    if ci_path.exists():
        cm = CampaignManager(state_path=ci_path, settings=settings)
        return cm.load()

    # Fall back to plan-mode orchestrator state
    sm = StateManager(state_path=_state_path(slug, settings), settings=settings)
    return sm.load()


@app.command()
def status(
    slug: str = typer.Argument(..., help="Project slug"),
    phase: Optional[int] = typer.Argument(None, help="Phase number (for per-task detail)"),
    task: Optional[int] = typer.Argument(None, help="Task number (for per-task detail)"),
) -> None:
    """Show one-line status summary.

    Examples:
        python -m orchestrator_v3 status fp8_training
        python -m orchestrator_v3 status fp8_training 0 1
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        state = _load_state_for_query(slug, settings, phase, task)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    display.print_status(state)


@app.command()
def info(
    slug: str = typer.Argument(..., help="Project slug"),
    phase: Optional[int] = typer.Argument(None, help="Phase number (for per-task detail)"),
    task: Optional[int] = typer.Argument(None, help="Task number (for per-task detail)"),
) -> None:
    """Show detailed progress info.

    Examples:
        python -m orchestrator_v3 info fp8_training
        python -m orchestrator_v3 info fp8_training 0 1
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        state = _load_state_for_query(slug, settings, phase, task)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    display.print_info(state, settings)


@app.command()
def history(
    slug: str = typer.Argument(..., help="Project slug"),
    phase: Optional[int] = typer.Argument(None, help="Phase number (for per-task detail)"),
    task: Optional[int] = typer.Argument(None, help="Task number (for per-task detail)"),
) -> None:
    """Show round-by-round review history.

    Examples:
        python -m orchestrator_v3 history fp8_training
        python -m orchestrator_v3 history fp8_training 0 1
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        state = _load_state_for_query(slug, settings, phase, task)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    display.print_history(state)


@app.command()
def validate(
    slug: str = typer.Argument(..., help="Project slug"),
) -> None:
    """Validate state file integrity.

    Example: python -m orchestrator_v3 validate fp8_training
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    sm = StateManager(state_path=_state_path(slug, settings), settings=settings)
    errors: list[str] = []

    try:
        state = sm.load()
    except FileNotFoundError:
        typer.echo(f"State file not found for slug: {slug}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"{display.RED}FAIL: State file invalid: {e}{display.RESET}", err=True)
        raise typer.Exit(code=1)

    if state.plan_file and not Path(state.plan_file).exists():
        errors.append(f"Plan file not found: {state.plan_file}")

    for sf in state.stage_files:
        if not Path(sf).exists():
            errors.append(f"Stage file not found: {sf}")

    if state.current_round < 1:
        errors.append(f"Invalid current_round: {state.current_round}")
    if state.current_phase < 0:
        errors.append(f"Invalid current_phase: {state.current_phase}")
    if state.current_task < 1:
        errors.append(f"Invalid current_task: {state.current_task}")
    if state.stage_files and state.current_stage >= state.total_stages:
        errors.append(
            f"current_stage ({state.current_stage}) >= "
            f"total_stages ({state.total_stages})"
        )

    if errors:
        for e in errors:
            typer.echo(f"{display.RED}FAIL: {e}{display.RESET}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f'{display.GREEN}OK: State file for "{slug}" is valid.{display.RESET}')


@app.command()
def research(
    question: str = typer.Argument(..., help="The research question to investigate"),
    slug: Optional[str] = typer.Option(None, "--slug", help="Session slug (auto-generated from question if omitted)"),
    max_rounds: int = typer.Option(10, "--max-rounds", help="Maximum convergence rounds"),
    timeout: int = typer.Option(_env_int("MAISTRO_TIMEOUT", 1800), "--timeout", help="Per-model wall-clock timeout in seconds"),
    idle_timeout: int = typer.Option(_env_int("MAISTRO_IDLE_TIMEOUT", 600), "--idle-timeout", help="Kill model after N seconds of no output"),
    claude_model: str = typer.Option(_env_str("MAISTRO_CLAUDE_MODEL", "opus"), "--claude-model", help="Claude model name"),
    codex_model: str = typer.Option(_env_str("MAISTRO_CODEX_MODEL", "gpt-5.4"), "--codex-model", help="Codex model (DO NOT pass this flag unless the user explicitly asks — the default is correct)"),
    reasoning_effort: str = typer.Option(_env_str("MAISTRO_CODEX_REASONING", "high"), "--reasoning-effort", help="Codex reasoning effort level (low/medium/high)"),
    force: bool = typer.Option(False, "--force", help="Force overwrite if research state already exists"),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip preflight validation checks"),
) -> None:
    """Run dual-model research deliberation.

    Two LLMs (Claude Opus and Codex) independently analyze the question,
    cross-review each other's work, iterate toward convergence, and produce
    a synthesis.

    The default models and reasoning effort are pre-configured. Do NOT pass
    --claude-model or --codex-model unless the user explicitly asks.

    Examples:
        python -m orchestrator_v3 research "What are the tradeoffs between sync and async IO?"
        python -m orchestrator_v3 research "Debug this OOM" --slug oom_debug --max-rounds 3
    """
    if not skip_preflight:
        _run_env_preflight("research")

    from orchestrator_v3.research import (
        ClaudeRunner,
        ResearchLoop,
        ResearchStateManager,
        _slugify,
    )
    from orchestrator_v3.research_prompts import ResearchPromptBuilder

    session_slug = slug if slug else _slugify(question)

    settings = OrchestratorSettings(
        repo_root=Path.cwd(),
        default_max_rounds=max_rounds,
        default_model=codex_model,
    )

    research_dir = settings.research_dir / session_slug
    research_dir.mkdir(parents=True, exist_ok=True)

    state_path = research_dir / "state.json"
    _guard_init(state_path, force, f"research '{session_slug}'")

    # Clean up old artifacts when --force is used
    if force and research_dir.exists():
        for old_file in research_dir.glob("*.md"):
            old_file.unlink()
        for old_file in research_dir.glob("*.log"):
            old_file.unlink()

    sm = ResearchStateManager(state_path=state_path)
    sm.init(slug=session_slug, question=question, max_rounds=max_rounds)

    pb = ResearchPromptBuilder(question=question, intent="", slug=session_slug)
    claude = ClaudeRunner(model=claude_model, timeout=timeout, idle_timeout=idle_timeout)
    codex = CodexReviewer(model=codex_model, timeout=timeout, idle_timeout=idle_timeout, reasoning_effort=reasoning_effort)

    from orchestrator_v3 import display as disp

    loop = ResearchLoop(
        state_manager=sm,
        prompt_builder=pb,
        claude_runner=claude,
        codex_runner=codex,
        display=disp,
        settings=settings,
        slug=session_slug,
    )

    from orchestrator_v3.run_recorder import RunRecorder

    disp.print_research_header(session_slug, question, "(classifying...)")
    recorder = RunRecorder(mode="research", slug=session_slug, repo_root=settings.repo_root)
    with recorder:
        result = loop.run(max_rounds=max_rounds)
        state = sm.load()
        recorder.outcome = state.status if result == 0 else "error"
        # Derive convergence outcome from agreement scores (state.status is
        # overwritten to "complete" after synthesis, losing the distinction)
        if result != 0:
            convergence_status = "error"
        elif (
            state.opus_agreement is not None and state.opus_agreement >= 8
            and state.codex_agreement is not None and state.codex_agreement >= 8
            and state.open_issues is not None and state.open_issues == 0
        ):
            convergence_status = "converged"
        else:
            convergence_status = "max_rounds_reached"
        recorder.set_convergence_data(
            rounds=state.convergence_round,
            opus_agreement=state.opus_agreement,
            codex_agreement=state.codex_agreement,
            open_issues=state.open_issues,
            final_status=convergence_status,
            history=state.history,
        )
        for entry in state.history:
            if entry.get("artifact"):
                recorder.add_artifact(str(research_dir / entry["artifact"]))
    raise typer.Exit(code=result)


@app.command()
def postmortem(
    slug: str = typer.Argument(..., help="Campaign slug to analyze"),
    skip_reflection: bool = typer.Option(
        False, "--skip-reflection", help="Skip LLM reflection (metrics only)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List artifacts without generating report"
    ),
    model: str = typer.Option(_env_str("MAISTRO_CODEX_MODEL", "gpt-5.4"), "--model", help="Reflection model (DO NOT pass this flag unless the user explicitly asks — the default is correct)"),
    timeout: int = typer.Option(_env_int("MAISTRO_TIMEOUT", 1800), "--timeout", help="Reflection wall-clock timeout in seconds"),
    idle_timeout: int = typer.Option(_env_int("MAISTRO_IDLE_TIMEOUT", 600), "--idle-timeout", help="Kill reviewer after N seconds of no output"),
    reasoning_effort: str = typer.Option(_env_str("MAISTRO_CODEX_REASONING", "high"), "--reasoning-effort", help="Codex reasoning effort level (low/medium/high)"),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip preflight validation checks"),
) -> None:
    """Generate a campaign postmortem report.

    Scans review artifacts for the given slug, computes metrics, and
    optionally generates an LLM evolutionary reflection.

    Examples:
        python -m orchestrator_v3 postmortem bf16_grad_compress --skip-reflection
        python -m orchestrator_v3 postmortem orchestrator_v2
        python -m orchestrator_v3 postmortem bf16_grad_compress --dry-run
    """
    if not skip_preflight:
        _run_env_preflight("postmortem")

    from orchestrator_v3.postmortem import (
        calculate_metrics,
        generate_report,
        scan_campaign_artifacts,
        write_report,
    )
    from orchestrator_v3.reflection import (
        build_reflection_prompt,
        run_reflection,
        select_failing_artifacts,
    )

    settings = OrchestratorSettings(repo_root=Path.cwd())
    scan = scan_campaign_artifacts(slug, settings)

    if not scan.artifacts:
        typer.echo(f"No review artifacts found for slug: {slug}")
        raise typer.Exit(code=0)

    if dry_run:
        typer.echo(f"DRY RUN — {len(scan.artifacts)} artifacts found for '{slug}':")
        for art in scan.artifacts:
            typer.echo(f"  {art.path.name}")
        raise typer.Exit(code=0)

    metrics = calculate_metrics(scan)

    reflection_text = None
    if not skip_reflection:
        failing = select_failing_artifacts(scan)
        prompt = build_reflection_prompt(metrics, failing)
        reviewer = CodexReviewer(model=model, timeout=timeout, idle_timeout=idle_timeout, reasoning_effort=reasoning_effort)
        reflection_path = settings.reviews_dir / f"{slug}_reflection.md"
        typer.echo("Running evolutionary reflection...")
        reflection_text = run_reflection(prompt, reflection_path, reviewer)
        if reflection_text:
            typer.echo(f"{display.GREEN}Reflection generated.{display.RESET}")
        else:
            typer.echo(
                f"{display.YELLOW}Reflection failed (non-fatal). "
                f"Producing metrics-only report.{display.RESET}"
            )

    report = generate_report(metrics, reflection=reflection_text)
    output_path = write_report(slug, report, settings)
    typer.echo(f"{display.GREEN}Postmortem written to: {output_path}{display.RESET}")
    typer.echo("")
    typer.echo(f"  Total tasks: {metrics.total_tasks}")
    typer.echo(f"  Total rounds: {metrics.total_rounds}")
    typer.echo(
        f"  First-round approval rate: "
        f"{metrics.first_round_approvals}/{metrics.total_tasks} "
        f"({metrics.first_round_approval_rate:.0%})"
    )
    typer.echo(
        f"  Average rounds to approval: {metrics.avg_rounds_to_approval:.1f}"
    )


@app.command()
def doctor() -> None:
    """Run extended environment diagnostics.

    Checks CLI tools, directories, repo root, Python version, required
    packages, and venv health. Prints a summary table and exits with
    code 0 if no failures, 1 otherwise.

    Example:
        python -m orchestrator_v3 doctor
    """
    from orchestrator_v3.env_checks import (
        _find_repo_root,
        check_cli_tools,
        check_directories,
        check_python_version,
        check_repo_root,
        check_required_packages,
        check_venv,
    )

    results = []
    results.append(check_repo_root())
    results.extend(check_cli_tools(["claude", "codex"]))
    repo_root = _find_repo_root() or Path.cwd()
    results.extend(check_directories(repo_root))
    results.append(check_python_version())
    results.extend(check_required_packages())
    results.append(check_venv())

    typer.echo(f"\n{display.BOLD}{'Check':<25} {'Status':<8} Message{display.RESET}")
    typer.echo("-" * 65)
    for r in results:
        if r.status == "PASS":
            color = display.GREEN
        elif r.status == "WARN":
            color = display.YELLOW
        else:
            color = display.RED
        typer.echo(f"  {r.name:<23} {color}{r.status:<8}{display.RESET} {r.message}")
        if r.fix_hint and r.status != "PASS":
            typer.echo(f"  {'':23} {'':8} {display.CYAN}Fix: {r.fix_hint}{display.RESET}")

    passes = sum(1 for r in results if r.status == "PASS")
    warns = sum(1 for r in results if r.status == "WARN")
    fails = sum(1 for r in results if r.status == "FAIL")

    typer.echo(f"\n{display.BOLD}Summary:{display.RESET} {passes} passed, {warns} warnings, {fails} failures")

    if fails > 0:
        raise typer.Exit(code=1)


@app.command("plan-verify")
def plan_verify(
    target: Path = typer.Argument(..., help="Path to plan file to verify"),
    verbose: bool = typer.Option(False, "--verbose", help="Show warnings in addition to errors"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    no_cross_file: bool = typer.Option(False, "--no-cross-file", help="Skip cross-file consistency checks"),
    no_source_paths: bool = typer.Option(False, "--no-source-paths", help="Skip source path existence checks"),
) -> None:
    """Verify plan file syntax and structure.

    Runs structural checks on a plan file and reports errors and warnings.
    Exit code 0 if no errors (warnings are acceptable), 1 if any errors.

    Examples:
        python -m orchestrator_v3 plan-verify active_plans/my_plan/phases/phase_0_setup.md
        python -m orchestrator_v3 plan-verify plan.md --verbose
        python -m orchestrator_v3 plan-verify plan.md --json
        python -m orchestrator_v3 plan-verify master_plan.md --no-cross-file
    """
    from orchestrator_v3.plan_tool import verify_plan_syntax

    result = verify_plan_syntax(
        target,
        check_cross_file=not no_cross_file,
        validate_source_paths=not no_source_paths,
    )

    if json_output:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        if not result.passed:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    # Human-readable output
    use_color = sys.stdout.isatty()
    red = display.RED if use_color else ""
    yellow = display.YELLOW if use_color else ""
    green = display.GREEN if use_color else ""
    reset = display.RESET if use_color else ""

    typer.echo(f"Verifying: {target}")

    for issue in result.issues:
        if issue.severity == "error":
            prefix = f"{red}ERROR{reset}"
        else:
            if not verbose:
                continue
            prefix = f"{yellow}WARNING{reset}"

        line_info = f" (line {issue.line_number})" if issue.line_number else ""
        typer.echo(f"  {prefix}{line_info}: {issue.message}")
        if verbose and issue.suggestion:
            typer.echo(f"    Suggestion: {issue.suggestion}")

    # Summary line (always includes warning count)
    if result.passed:
        typer.echo(f"Result: {green}PASSED{reset} ({result.summary})")
    else:
        typer.echo(f"Result: {red}FAILED{reset} ({result.summary})")
        raise typer.Exit(code=1)


@app.command("plan-lint")
def plan_lint_cmd(
    target: Path = typer.Argument(..., help="Path to plan file to lint"),
    verbose: bool = typer.Option(False, "--verbose", help="Show all warnings with suggestions"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    min_words: int = typer.Option(20, "--min-words", help="Minimum words for task granularity"),
    max_words: int = typer.Option(300, "--max-words", help="Maximum words for task granularity"),
    evolution_log: str = typer.Option("", "--evolution-log", help="Path to evolution log JSONL file"),
) -> None:
    """Lint plan file content for quality issues.

    Validates file path existence, task granularity, code-mode file
    references, and known evolution log failure patterns. Complements
    plan-verify which checks structural syntax.

    Examples:
        python -m orchestrator_v3 plan-lint active_plans/my_plan/phases/phase_0.md
        python -m orchestrator_v3 plan-lint plan.md --verbose
        python -m orchestrator_v3 plan-lint plan.md --json
        python -m orchestrator_v3 plan-lint plan.md --min-words 15 --max-words 250
    """
    from orchestrator_v3.plan_lint import lint_plan

    log_path = Path(evolution_log) if evolution_log else None

    result = lint_plan(
        target,
        evolution_log_path=log_path,
        min_words=min_words,
        max_words=max_words,
    )

    if json_output:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        raise typer.Exit(code=0 if result.passed else 1)

    # Human-readable output
    use_color = sys.stdout.isatty()
    red = display.RED if use_color else ""
    yellow = display.YELLOW if use_color else ""
    green = display.GREEN if use_color else ""
    reset = display.RESET if use_color else ""

    typer.echo(f"Linting: {target}")

    for issue in result.issues:
        if issue.severity == "error":
            prefix = f"{red}ERROR{reset}"
        else:
            if not verbose:
                continue
            prefix = f"{yellow}WARNING{reset}"

        line_info = f" (line {issue.line_number})" if issue.line_number else ""
        typer.echo(f"  {prefix}{line_info}: {issue.message}")
        if verbose and issue.suggestion:
            typer.echo(f"    Suggestion: {issue.suggestion}")

    if result.passed:
        typer.echo(f"Result: {green}PASSED{reset} ({result.summary})")
    else:
        typer.echo(f"Result: {red}FAILED{reset} ({result.summary})")
        raise typer.Exit(code=1)


@app.command("task-brief")
def task_brief_cmd(
    target: Path = typer.Argument(..., help="Path to plan file"),
    task: str = typer.Argument(..., help="Task number (e.g., '2' or '2.1')"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    sessions_dir: str = typer.Option("", "--sessions-dir", help="Path to sessions directory"),
    output_file: str = typer.Option("", "--output", "-o", help="Write brief to file instead of stdout"),
) -> None:
    """Generate a context brief for a plan task.

    Produces a compact markdown bundle with directory trees, file headers,
    and historical anti-pattern data to reduce exploration waste.

    Examples:
        python -m orchestrator_v3 task-brief plan.md 2
        python -m orchestrator_v3 task-brief plan.md 2.1 --json
        python -m orchestrator_v3 task-brief plan.md 3 -o brief.md
    """
    from orchestrator_v3.task_brief import generate_brief

    sess = Path(sessions_dir) if sessions_dir else None

    try:
        brief = generate_brief(target, task, sessions_dir=sess)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(brief.model_dump(), indent=2))
        raise typer.Exit(code=0)

    if output_file:
        Path(output_file).write_text(brief.markdown)
        typer.echo(f"Brief written to {output_file}")
    else:
        typer.echo(brief.markdown)


@app.command("plan-status")
def plan_status_cmd(
    slug: str = typer.Argument(..., help="Project slug"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show campaign progress summary.

    Reads campaign state and plan files to compute completion percentage,
    per-phase breakdown, and current phase/task pointer.

    Examples:
        python -m orchestrator_v3 plan-status plan_tool
        python -m orchestrator_v3 plan-status plan_tool --json
    """
    from orchestrator_v3.plan_tool import plan_status

    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        result = plan_status(slug, settings)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(result.to_json(), indent=2))
    else:
        typer.echo(result.to_text())


@app.command("plan-show")
def plan_show_cmd(
    slug: str = typer.Argument(..., help="Project slug"),
    current: bool = typer.Option(False, "--current", help="Show current task subtree"),
    recent: bool = typer.Option(False, "--recent", help="Show last N approved tasks"),
) -> None:
    """Show plan task details.

    Three modes:
      --current: extract current task subtree (compact, for LLM prompts)
      --recent: show last N approved tasks sorted by timestamp
      (default): full task list with status icons

    Examples:
        python -m orchestrator_v3 plan-show plan_tool
        python -m orchestrator_v3 plan-show plan_tool --current
        python -m orchestrator_v3 plan-show plan_tool --recent
    """
    from orchestrator_v3.plan_tool import plan_show

    if current and recent:
        typer.echo("Error: --current and --recent are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        result = plan_show(slug, settings, current=current, recent=recent)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result)


@app.command("plan-sync")
def plan_sync_cmd(
    slug: str = typer.Argument(..., help="Project slug"),
    phase: int = typer.Argument(..., help="Phase number"),
    task: int = typer.Argument(..., help="Task number"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
) -> None:
    """Sync a single task's approval status to plan checkmarks.

    Toggles the task heading and all subtask checkmarks from [ ] to [checkmark]
    in the phase file.

    Examples:
        python -m orchestrator_v3 plan-sync plan_tool 5 1
        python -m orchestrator_v3 plan-sync plan_tool 5 1 --dry-run
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        result = plan_sync(slug, phase, task, settings, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.summary())
    for detail in result.details:
        typer.echo(f"  {detail}")


@app.command("plan-render-master")
def plan_render_master_cmd(
    slug: str = typer.Argument(..., help="Project slug"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
) -> None:
    """Regenerate master plan Phases Overview from phase file state.

    Reads all phase files, extracts task headings and first-level subtasks,
    and replaces the Phases Overview section in the master plan.

    Examples:
        python -m orchestrator_v3 plan-render-master plan_tool
        python -m orchestrator_v3 plan-render-master plan_tool --dry-run
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        result = plan_render_master(slug, settings, dry_run=dry_run)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.summary())
    for detail in result.details:
        typer.echo(f"  {detail}")


@app.command("plan-reconcile")
def plan_reconcile_cmd(
    slug: str = typer.Argument(..., help="Project slug"),
    apply: bool = typer.Option(False, "--apply", help="Fix drift by syncing missing checkmarks"),
    from_reviews: bool = typer.Option(False, "--from-reviews", help="Infer completion from review file verdicts"),
) -> None:
    """Detect and optionally repair drift between state and plan checkmarks.

    Compares per-task state files against plan checkmarks and reports
    discrepancies. With --apply, fixes drift by calling plan-sync for
    each missing entry.

    Exit code 0 if in sync, 1 if drift detected (matching plan-verify convention).

    Examples:
        python -m orchestrator_v3 plan-reconcile plan_tool
        python -m orchestrator_v3 plan-reconcile plan_tool --apply
        python -m orchestrator_v3 plan-reconcile plan_tool --from-reviews
    """
    settings = OrchestratorSettings(repo_root=Path.cwd())
    try:
        result = plan_reconcile(slug, settings, apply=apply, from_reviews=from_reviews)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.summary())
    if not result.in_sync:
        raise typer.Exit(code=1)
