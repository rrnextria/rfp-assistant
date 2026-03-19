"""Orchestrator V3 — modular review-loop automation.

A modular, testable review-loop automation package with 11 focused Python
modules.  Orchestrates plan and code reviews via Codex (or any reviewer
implementing ``ReviewerBase``), using the ORCH_META machine-readable verdict
protocol for reliable approval detection.

Modules
-------
- ``config`` — Enums (``Status``, ``Mode``, ``PlanType``), settings, repo root detection
- ``state`` — Atomic JSON state persistence with backup and ``advance_task`` logic
- ``artifacts`` — Artifact path resolution, plan type detection, round scanning
- ``approval`` — ORCH_META block parser and ``check_approved`` logic
- ``prompts`` — Structured prompt builder for plan and code review modes
- ``reviewer`` — ``CodexReviewer`` (production) and ``MockReviewer`` (testing)
- ``loop`` — Main orchestration engine with resume, complex-plan stages, and round loop
- ``display`` — ANSI-colored terminal output (banners, status, info, history)
- ``cli`` — Typer CLI with ``plan``, ``code``, ``status``, ``info``, ``history``, ``validate`` commands
- ``__main__`` — Entry point for ``python -m orchestrator_v3``

Guides
------
- ``how_to/guides/plan_review.md`` — Planner-Reviewer workflow
- ``how_to/guides/code_review.md`` — Coder-Reviewer workflow
- ``how_to/guides/workflow.md`` — Three-session pattern overview
- ``how_to/guides/reference.md`` — ORCH_META protocol, naming, CLI reference

Features
--------
- ORCH_META protocol — machine-readable verdicts
- Finding IDs (B/M/N/D prefixes) — stable tracking across rounds
- Prior-round context — reviewer reads prior review + response before writing
- ``status``, ``info``, ``history``, ``validate`` CLI commands
- Complex plan support (multi-stage review with per-stage ArtifactResolver)
- Atomic state persistence with backup files
- Mock reviewer for deterministic testing
- Dry-run mode for prompt inspection
"""

__version__ = "3.0.0"
