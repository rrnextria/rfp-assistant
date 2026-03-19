"""RunRecorder — context manager that captures session metadata for orchestrator runs.

Wraps orchestrator loop execution to record run_id (UUIDv7), mode, slug,
timing, git state, file hashes, and artifact paths.  On exit, emits a
``run_summary.json`` to ``maistro/sessions/`` containing metadata, verdict
history, finding counts, and (for research mode) convergence data.
Optionally builds a ``.tar.gz`` session archive with all run artifacts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _uuid7() -> str:
    """Generate a UUIDv7 string (RFC 9562) from current timestamp + random bytes.

    Uses millisecond-precision timestamp in the upper 48 bits and random bytes
    for the remaining bits, with version=7 and variant=RFC 4122.
    """
    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)

    # 48-bit timestamp (6 bytes)
    ts_bytes = timestamp_ms.to_bytes(6, byteorder="big")

    # rand_a: 12 bits (upper 12 bits of rand_bytes[0:2])
    rand_a = int.from_bytes(rand_bytes[0:2], "big") & 0x0FFF

    # rand_b: 62 bits (from rand_bytes[2:10])
    rand_b = int.from_bytes(rand_bytes[2:10], "big") & 0x3FFFFFFFFFFFFFFF

    # Construct 128-bit value
    uuid_int = (
        (int.from_bytes(ts_bytes, "big") << 80)
        | (0x7 << 76)  # version 7
        | (rand_a << 64)
        | (0x2 << 62)  # variant RFC 4122
        | rand_b
    )

    hex_str = f"{uuid_int:032x}"
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_files(paths: list[Path]) -> dict[str, str]:
    """Compute SHA-256 hashes for a list of files, skipping missing ones."""
    result: dict[str, str] = {}
    for p in paths:
        if p.exists() and p.is_file():
            result[str(p)] = sha256_file(p)
    return result


@dataclass
class GitState:
    """Snapshot of git repository state."""

    sha: str = "unknown"
    branch: str = "unknown"
    dirty: bool = False


def capture_git_state(repo_root: Path | None = None) -> GitState:
    """Capture current git SHA, branch name, and dirty/clean status.

    Falls back to defaults if git commands fail (e.g. not in a git repo).
    """
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 5}
    if repo_root:
        kwargs["cwd"] = str(repo_root)

    state = GitState()
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], **kwargs)
        if result.returncode == 0:
            state.sha = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], **kwargs)
        if result.returncode == 0:
            state.branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        result = subprocess.run(["git", "status", "--porcelain"], **kwargs)
        if result.returncode == 0:
            state.dirty = bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return state


def _epoch_to_iso(ts: float) -> str:
    """Convert a UNIX epoch float to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def extract_finding_counts(artifact_paths: list[str]) -> list[dict[str, Any]]:
    """Parse ORCH_META from review artifacts and return per-round finding counts.

    Only processes artifacts whose filenames contain ``_review_round`` (review
    files), skipping code_complete, coder_response, etc.
    """
    from orchestrator_v3.approval import parse_orch_meta

    results: list[dict[str, Any]] = []
    for path_str in artifact_paths:
        p = Path(path_str)
        if "_review_round" not in p.name:
            continue
        meta = parse_orch_meta(p)
        if meta is None:
            continue
        results.append({
            "file": p.name,
            "verdict": meta.verdict.value,
            "blocker": meta.blocker,
            "major": meta.major,
            "minor": meta.minor,
            "decisions": meta.decisions,
            "verified": meta.verified,
        })
    return results


# ── Claude Session Discovery ─────────────────────────────────────────


def encode_project_path(repo_root: Path) -> str:
    """Encode a repo root path to match Claude Code's project directory convention.

    Replaces ``/`` separators with ``-`` in the resolved absolute path.
    Example: ``/home/user/git/MyRepo`` → ``-home-user-git-MyRepo``
    """
    return str(repo_root.resolve()).replace("/", "-")


def discover_session_files(
    repo_root: Path,
    start_time: float,
    end_time: float,
    claude_dir: Path | None = None,
) -> list[Path]:
    """Locate Claude Code JSONL session transcripts for the current run.

    Primary method: scan ``~/.claude/projects/<encoded-path>/`` for JSONL
    files whose modification time falls within the run window
    ``[start_time, end_time]`` (with 60s padding on each side).

    Fallback: if ``sessions-index.json`` exists under ``claude_dir``,
    parse it and match entries by project path.

    Returns a list of matching JSONL paths, sorted by modification time
    (newest first).  Returns an empty list when no sessions are found.
    """
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"

    encoded = encode_project_path(repo_root)
    project_dir = claude_dir / "projects" / encoded

    # Padding: sessions may start slightly before __enter__ or end after __exit__
    pad = 60.0
    window_start = start_time - pad
    window_end = end_time + pad

    matches: list[tuple[float, Path]] = []

    # Primary: filesystem scan
    if project_dir.is_dir():
        for jsonl in project_dir.glob("*.jsonl"):
            try:
                mtime = jsonl.stat().st_mtime
            except OSError:
                continue
            if window_start <= mtime <= window_end:
                matches.append((mtime, jsonl))

    # Fallback: per-project sessions-index.json
    if not matches:
        index_path = project_dir / "sessions-index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text())
                if not isinstance(index, dict):
                    index = {}
                entries = index.get("entries", [])
                if not isinstance(entries, list):
                    entries = []
                resolved_root = str(repo_root.resolve())
                # Top-level originalPath acts as default project path
                original_path = index.get("originalPath", "")
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    # Validate project path matches the current repo
                    # Per-entry projectPath takes precedence; fall back to top-level originalPath
                    entry_project = entry.get("projectPath", "") or original_path
                    if entry_project != resolved_root:
                        continue
                    full_path = entry.get("fullPath", "")
                    if not full_path:
                        continue
                    sp = Path(full_path)
                    if sp.exists() and sp.suffix == ".jsonl":
                        try:
                            mtime = sp.stat().st_mtime
                        except OSError:
                            continue
                        if window_start <= mtime <= window_end:
                            matches.append((mtime, sp))
            except (json.JSONDecodeError, OSError, TypeError):
                logger.debug("Failed to parse sessions-index.json")

    # Sort newest first
    matches.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in matches]


# ── Session Archive Builder ──────────────────────────────────────────


def _collect_plan_code_files(
    slug: str,
    repo_root: Path,
    reviews_dir: Path | None = None,
    phase: int | None = None,
    task: int | None = None,
    plan_slug: str | None = None,
) -> list[tuple[str, Path]]:
    """Collect artifacts for plan/code archives.

    Returns ``(arcname, source_path)`` pairs.  Collects:
    - ``artifacts/reviews/<file>`` for review artifacts filtered by slug
    - ``run/state.json`` for the orchestrator state file
    - ``run/plan_snapshot.md`` for the active plan snapshot
    """
    if reviews_dir is None:
        reviews_dir = repo_root / "reviews"
    files: list[tuple[str, Path]] = []

    # Review artifacts filtered by slug (includes .md and .md.log files)
    if reviews_dir.is_dir():
        for f in sorted(reviews_dir.iterdir()):
            if f.name.startswith(f"{slug}_") and f.is_file():
                files.append((f"artifacts/reviews/{f.name}", f))

    # State file — mode-specific primary state:
    # Plan mode: {slug}_orchestrator_state.json
    # Code mode: {slug}_p{phase}_t{task}_state.json (the primary state for the task)
    if phase is not None and task is not None:
        task_state = reviews_dir / f"{slug}_p{phase}_t{task}_state.json"
        if task_state.exists():
            files.append(("run/state.json", task_state))
    else:
        orch_state = reviews_dir / f"{slug}_orchestrator_state.json"
        if orch_state.exists():
            files.append(("run/state.json", orch_state))

    # Campaign state (code mode: {slug}_campaign.json)
    campaign = reviews_dir / f"{slug}_campaign.json"
    if campaign.exists():
        files.append(("run/campaign.json", campaign))

    # Plan snapshot — try multiple naming conventions matching ArtifactResolver.
    # Use plan_slug if provided (e.g. code mode with --plan-slug), else slug.
    ps = plan_slug or slug
    plans_dir = repo_root / "active_plans"
    master = plans_dir / ps / f"{ps}_master_plan.md"
    simple1 = plans_dir / f"{ps}.md"
    simple2 = plans_dir / ps / f"{ps}_plan.md"

    if master.exists():
        files.append(("run/plan_snapshot.md", master))
        # Archive phase plan(s) alongside the master plan.
        phases_dir = plans_dir / ps / "phases"
        if phases_dir.is_dir():
            if phase is not None:
                # Code mode: archive the specific phase plan
                for pf in sorted(phases_dir.glob(f"phase_{phase}_*.md")):
                    files.append(("run/phase_plan_snapshot.md", pf))
                    break  # first match only
            else:
                # Plan mode: archive all phase plans for analysis
                for pf in sorted(phases_dir.glob("phase_*.md")):
                    files.append((f"run/phase_plans/{pf.name}", pf))
    elif simple1.exists():
        files.append(("run/plan_snapshot.md", simple1))
    elif simple2.exists():
        files.append(("run/plan_snapshot.md", simple2))

    return files


def _collect_research_files(
    slug: str, repo_root: Path,
) -> list[tuple[str, Path]]:
    """Collect artifacts for research archives.

    Returns ``(arcname, source_path)`` pairs from ``research/<slug>/``.
    """
    research_dir = repo_root / "research" / slug
    files: list[tuple[str, Path]] = []
    if research_dir.is_dir():
        for f in sorted(research_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(research_dir)
                files.append((f"artifacts/research/{rel}", f))
    return files


def build_manifest(file_entries: list[tuple[str, Path]]) -> dict[str, Any]:
    """Build a manifest dict with SHA-256 hashes for all archive files.

    Returns a dict with ``files`` (list of {path, sha256, size_bytes}) and
    ``file_count``.
    """
    manifest_files: list[dict[str, Any]] = []
    for arcname, source in file_entries:
        if source.exists() and source.is_file():
            manifest_files.append({
                "path": arcname,
                "sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
            })
    return {
        "files": manifest_files,
        "file_count": len(manifest_files),
    }


def build_meta(
    run_id: str,
    mode: str,
    slug: str,
    git_state: GitState,
    start_time: float,
    end_time: float,
) -> dict[str, Any]:
    """Build meta.json content with git state and timestamps."""
    return {
        "run_id": run_id,
        "mode": mode,
        "slug": slug,
        "git_sha": git_state.sha,
        "git_branch": git_state.branch,
        "git_dirty": git_state.dirty,
        "start_time": _epoch_to_iso(start_time) if start_time else None,
        "end_time": _epoch_to_iso(end_time) if end_time else None,
    }


def _add_json_to_tar(tf: tarfile.TarFile, arcname: str, data: dict) -> None:
    """Add a JSON dict as a file entry in a tarfile."""
    content = json.dumps(data, indent=2).encode("utf-8") + b"\n"
    info = tarfile.TarInfo(name=arcname)
    info.size = len(content)
    tf.addfile(info, BytesIO(content))


def build_session_archive(
    *,
    run_id: str,
    mode: str,
    slug: str,
    repo_root: Path,
    git_state: GitState,
    start_time: float,
    end_time: float,
    summary_path: Path,
    session_paths: list[str],
    phase: int | None = None,
    task: int | None = None,
    plan_slug: str | None = None,
    reviews_dir: Path | None = None,
) -> Path | None:
    """Build a ``.tar.gz`` session archive in ``maistro/sessions/``.

    Archive naming: ``YYYYMMDDTHHMMSSZ_{mode}_{slug}_{run_id}.tar.gz``

    Returns the archive path on success, None on failure.
    """
    sessions_dir = repo_root / "maistro" / "sessions"
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Failed to create sessions directory: %s", sessions_dir)
        return None

    if reviews_dir is None:
        reviews_dir = repo_root / "reviews"

    # Timestamp for filename
    ts = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_name = f"{ts}_{mode}_{slug}_{run_id}.tar.gz"
    archive_path = sessions_dir / archive_name

    # Collect mode-specific files
    if mode == "research":
        file_entries = _collect_research_files(slug, repo_root)
    else:
        file_entries = _collect_plan_code_files(
            slug, repo_root, reviews_dir,
            phase=phase, task=task, plan_slug=plan_slug,
        )

    # Add summary
    if summary_path.exists():
        file_entries.append(("run/run_summary.json", summary_path))

    # Add Claude session transcripts
    for sp_str in session_paths:
        sp = Path(sp_str)
        if sp.exists():
            file_entries.append((f"claude/{sp.name}", sp))

    # Build meta first so we can include its hash in the manifest
    meta = build_meta(run_id, mode, slug, git_state, start_time, end_time)
    meta_bytes = json.dumps(meta, indent=2).encode("utf-8") + b"\n"
    meta_hash = hashlib.sha256(meta_bytes).hexdigest()

    # Build manifest including meta.json
    manifest = build_manifest(file_entries)
    manifest["files"].append({
        "path": "meta.json",
        "sha256": meta_hash,
        "size_bytes": len(meta_bytes),
    })
    manifest["file_count"] = len(manifest["files"])

    try:
        with tarfile.open(archive_path, "w:gz") as tf:
            # Add manifest and meta as in-memory JSON
            _add_json_to_tar(tf, "manifest.json", manifest)
            meta_info = tarfile.TarInfo(name="meta.json")
            meta_info.size = len(meta_bytes)
            tf.addfile(meta_info, BytesIO(meta_bytes))

            # Add all collected files
            for arcname, source in file_entries:
                if source.exists() and source.is_file():
                    tf.add(str(source), arcname=arcname)
    except OSError:
        logger.warning("Failed to create archive: %s", archive_path)
        return None

    return archive_path


@dataclass
class RunRecorder:
    """Context manager that captures session metadata for orchestrator runs.

    On exit, emits ``{run_id}_summary.json`` to ``maistro/sessions/``.

    Usage::

        recorder = RunRecorder(mode="plan", slug="my_plan", repo_root=Path.cwd())
        with recorder:
            result = loop.run(...)
            recorder.outcome = state.status if result == 0 else "error"
            recorder.set_verdict_history(state.history)
    """

    mode: str
    slug: str
    repo_root: Path
    phase: int | None = None
    task: int | None = None
    plan_slug: str | None = None
    reviewer_model: str = ""

    # Auto-populated on __enter__
    run_id: str = ""
    start_time: float = 0.0
    git_state: GitState = field(default_factory=GitState)
    file_hashes: dict[str, str] = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)

    # Set during/after the run
    outcome: str = "unknown"
    end_time: float = 0.0

    # Verdict history (plan/code modes)
    verdict_history: list[dict] = field(default_factory=list)

    # Convergence data (research mode)
    convergence_data: dict[str, Any] = field(default_factory=dict)

    # Claude session transcripts (discovered on exit)
    session_paths: list[str] = field(default_factory=list)

    # Archive path (set after archive is built)
    archive_path: str = ""

    def __enter__(self) -> RunRecorder:
        self.run_id = _uuid7()
        self.start_time = time.time()
        self.git_state = capture_git_state(self.repo_root)
        self._hash_project_files()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        self.end_time = time.time()
        if exc_type is not None and self.outcome == "unknown":
            self.outcome = "error"
        self._discover_sessions()
        self._emit_summary()
        self._build_archive()
        return None  # Don't suppress exceptions

    @property
    def duration(self) -> float:
        """Wall-clock duration in seconds."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0

    def add_artifact(self, path: str | Path) -> None:
        """Register an artifact produced during this run."""
        self.artifact_paths.append(str(path))

    def set_verdict_history(self, state_history: list[dict]) -> None:
        """Populate verdict history from state history entries (plan/code modes)."""
        self.verdict_history = list(state_history)

    def set_convergence_data(
        self,
        *,
        rounds: int,
        opus_agreement: int | None,
        codex_agreement: int | None,
        open_issues: int | None,
        final_status: str,
        history: list[dict],
    ) -> None:
        """Populate convergence data from research state (research mode)."""
        self.convergence_data = {
            "rounds": rounds,
            "opus_agreement": opus_agreement,
            "codex_agreement": codex_agreement,
            "open_issues": open_issues,
            "final_status": final_status,
            "history": history,
        }

    def _discover_sessions(self) -> None:
        """Locate Claude Code session transcripts for this run."""
        if self.start_time and self.end_time:
            found = discover_session_files(self.repo_root, self.start_time, self.end_time)
            self.session_paths = [str(p) for p in found]

    def _emit_summary(self) -> None:
        """Write run_summary.json to maistro/sessions/."""
        sessions_dir = self.repo_root / "maistro" / "sessions"
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Failed to create sessions directory: %s", sessions_dir)
            return

        summary: dict[str, Any] = {
            "run_id": self.run_id,
            "mode": self.mode,
            "slug": self.slug,
            "phase": self.phase,
            "task": self.task,
            "outcome": self.outcome,
            "start_time": _epoch_to_iso(self.start_time) if self.start_time else None,
            "end_time": _epoch_to_iso(self.end_time) if self.end_time else None,
            "duration_seconds": round(self.duration, 3),
            "git_state": {
                "sha": self.git_state.sha,
                "branch": self.git_state.branch,
                "dirty": self.git_state.dirty,
            },
            "file_hashes": self.file_hashes,
            "artifact_paths": self.artifact_paths,
            "session_paths": self.session_paths,
            "reviewer_model": self.reviewer_model,
        }

        if self.mode == "research":
            summary["convergence"] = self.convergence_data or None
        else:
            # Plan/code: include verdict history and finding counts
            summary["verdict_history"] = self.verdict_history
            finding_counts = extract_finding_counts(self.artifact_paths)
            summary["finding_counts"] = finding_counts
            # Aggregate totals across all rounds
            summary["total_rounds"] = len(self.verdict_history)
            if finding_counts:
                summary["total_findings"] = {
                    "blocker": sum(r["blocker"] for r in finding_counts),
                    "major": sum(r["major"] for r in finding_counts),
                    "minor": sum(r["minor"] for r in finding_counts),
                }

        self._summary_path = sessions_dir / f"{self.run_id}_summary.json"
        try:
            self._summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        except OSError:
            logger.warning("Failed to write summary: %s", self._summary_path)

    def _build_archive(self) -> None:
        """Build a .tar.gz session archive after summary emission."""
        summary_path = getattr(self, "_summary_path", None)
        if summary_path is None:
            return
        result = build_session_archive(
            run_id=self.run_id,
            mode=self.mode,
            slug=self.slug,
            repo_root=self.repo_root,
            git_state=self.git_state,
            start_time=self.start_time,
            end_time=self.end_time,
            summary_path=summary_path,
            session_paths=self.session_paths,
            phase=self.phase,
            task=self.task,
            plan_slug=self.plan_slug,
        )
        if result:
            self.archive_path = str(result)

    def _hash_project_files(self) -> None:
        """Hash templates, guides, and prompts used during runs."""
        how_to = self.repo_root / "how_to"
        paths: list[Path] = []

        # Guides
        guides_dir = how_to / "guides"
        if guides_dir.is_dir():
            paths.extend(sorted(guides_dir.glob("*.md")))

        # Templates
        templates_dir = how_to / "templates"
        if templates_dir.is_dir():
            paths.extend(sorted(templates_dir.glob("*.md")))

        # Prompt files
        for prompt_file in ("prompts.py", "research_prompts.py"):
            p = how_to / "orchestrator_v3" / prompt_file
            if p.exists():
                paths.append(p)

        self.file_hashes = hash_files(paths)
