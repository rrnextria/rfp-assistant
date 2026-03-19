"""Context preloader — generates compact task briefs to reduce exploration waste.

Produces a markdown context bundle for a specific plan task containing:
- Directory trees (max depth 2) for referenced directories
- File headers (first 20 lines) for referenced files
- Condensation anti-pattern context from Phase 3 session analysis

Usage:
    task_brief.generate_brief(plan_path, task_number) -> TaskBrief
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from orchestrator_v3.plan_lint import _BACKTICK_PATH_RE, _is_file_path
from orchestrator_v3.plan_tool import ParsedPlan, ParsedTask, parse_plan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class TaskBrief(BaseModel):
    """Generated context bundle for a plan task."""

    task_number: str
    task_title: str
    plan_path: str
    directory_trees: dict[str, str] = Field(default_factory=dict)
    file_headers: dict[str, list[str]] = Field(default_factory=dict)
    anti_patterns: list[dict] = Field(default_factory=list)
    markdown: str = ""


# ---------------------------------------------------------------------------
# 2.1 — Directory tree extractor
# ---------------------------------------------------------------------------

def extract_directory_trees(
    paths: list[str],
    repo_root: Path,
    max_depth: int = 2,
) -> dict[str, str]:
    """Produce max-depth-2 trees for directories referenced in the plan.

    For file paths, uses the parent directory. Deduplicates directories.
    Returns {dir_path: tree_string}.
    """
    dirs: set[str] = set()
    for p in paths:
        full = repo_root / p
        if full.is_dir():
            dirs.add(p)
        elif full.parent != repo_root and full.parent.is_dir():
            dirs.add(str(Path(p).parent))

    trees: dict[str, str] = {}
    for d in sorted(dirs):
        tree = _build_tree(repo_root / d, repo_root, max_depth)
        if tree:
            trees[d] = tree
    return trees


def _build_tree(directory: Path, repo_root: Path, max_depth: int) -> str:
    """Build an indented tree string for a directory up to max_depth."""
    lines: list[str] = []
    rel = directory.relative_to(repo_root)
    lines.append(f"{rel}/")
    _walk_tree(directory, repo_root, lines, depth=1, max_depth=max_depth)
    return "\n".join(lines)


def _walk_tree(
    directory: Path,
    repo_root: Path,
    lines: list[str],
    depth: int,
    max_depth: int,
) -> None:
    """Recursively walk directory, appending indented entries."""
    if depth > max_depth:
        return
    try:
        entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    except PermissionError:
        return

    for entry in entries:
        # Skip hidden dirs and common noise
        if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
            continue
        indent = "  " * depth
        if entry.is_dir():
            lines.append(f"{indent}{entry.name}/")
            _walk_tree(entry, repo_root, lines, depth + 1, max_depth)
        else:
            lines.append(f"{indent}{entry.name}")


# ---------------------------------------------------------------------------
# 2.2 — File header extractor
# ---------------------------------------------------------------------------

def extract_file_headers(
    paths: list[str],
    repo_root: Path,
    max_lines: int = 20,
) -> dict[str, list[str]]:
    """Capture the first N lines of files mentioned in the plan.

    Only includes files that exist and are text-readable.
    Returns {file_path: [line1, line2, ...]}.
    """
    headers: dict[str, list[str]] = {}
    seen: set[str] = set()

    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        full = repo_root / p
        if not full.is_file():
            continue
        try:
            with full.open("r", errors="replace") as f:
                head = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    head.append(line.rstrip("\n"))
                headers[p] = head
        except (OSError, UnicodeDecodeError):
            logger.debug("Could not read %s", full)

    return headers


# ---------------------------------------------------------------------------
# 2.3 — Condensation anti-pattern query
# ---------------------------------------------------------------------------

def query_anti_patterns(
    plan_path: Path,
    sessions_dir: Path | None = None,
) -> list[dict]:
    """Read Phase 3 condensation files and extract anti-patterns.

    Looks for condensation JSON files in the sessions directory,
    filters to sessions with a matching template_hash (computed from
    the repo's template files), and extracts pattern data with
    associated file paths.

    Returns a list of anti-pattern dicts with pattern_type, description,
    estimated_tokens_wasted, associated_files, and source_session.
    """
    repo_root = _find_repo_root(plan_path)

    if sessions_dir is None:
        sessions_dir = repo_root / "maistro" / "sessions"

    if not sessions_dir.is_dir():
        logger.debug("Sessions dir not found: %s", sessions_dir)
        return []

    # Compute current template_hash for scoping
    current_hash = _compute_template_hash(repo_root)

    # Find run_ids with matching template_hash from summary files
    matching_run_ids = _find_matching_sessions(sessions_dir, current_hash)
    if not matching_run_ids:
        logger.debug("No sessions with matching template_hash in %s", sessions_dir)
        return []

    # Load condensation data only for matching sessions
    anti_patterns: list[dict] = []
    seen_descriptions: set[str] = set()

    for run_id in matching_run_ids:
        cf = sessions_dir / f"{run_id}_condensation.json"
        if not cf.is_file():
            continue
        try:
            data = json.loads(cf.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        patterns = data.get("patterns", [])
        for p in patterns:
            desc = p.get("description", "")
            if desc in seen_descriptions:
                continue
            seen_descriptions.add(desc)

            # Extract associated file paths from the description text
            associated_files = _extract_paths_from_text(desc)

            anti_patterns.append({
                "pattern_type": p.get("pattern_type", "unknown"),
                "description": desc,
                "estimated_tokens_wasted": p.get("estimated_tokens_wasted", 0),
                "associated_files": associated_files,
                "source_session": data.get("run_id", "unknown"),
            })

    return anti_patterns


def _compute_template_hash(repo_root: Path) -> str | None:
    """Compute the canonical template_hash for the current repo.

    Matches the contract used by run_recorder.hash_files() and
    evolution/ingest.py _extract_file_hash(): the SHA-256 of the first
    template file found (sorted by path), which is the same value stored
    in session summaries under file_hashes.
    """
    templates_dir = repo_root / "how_to" / "templates"
    if not templates_dir.is_dir():
        return None

    for f in sorted(templates_dir.iterdir()):
        if f.is_file():
            try:
                h = hashlib.sha256()
                with f.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(8192), b""):
                        h.update(chunk)
                return h.hexdigest()
            except OSError:
                continue
    return None


def _find_matching_sessions(
    sessions_dir: Path,
    current_hash: str | None,
) -> list[str]:
    """Find session run_ids whose template_hash matches the current one.

    Reads summary JSON files and checks file_hashes for a templates/ entry.
    If current_hash is None, returns empty (no matching possible).
    """
    if current_hash is None:
        return []

    run_ids: list[str] = []
    for sf in sorted(sessions_dir.glob("*_summary.json")):
        try:
            data = json.loads(sf.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        run_id = data.get("run_id")
        if not run_id:
            continue

        # Extract template_hash from file_hashes (same logic as ingest.py)
        file_hashes = data.get("file_hashes") or {}
        session_hash = None
        for path, h in file_hashes.items():
            if "templates/" in path:
                session_hash = h
                break

        if session_hash == current_hash:
            run_ids.append(run_id)

    return run_ids


def _extract_paths_from_text(text: str) -> list[str]:
    """Extract file paths from description text.

    Handles backtick-delimited paths, search-pattern prefixes (glob:, grep:),
    and bare path-like tokens.
    """
    paths: list[str] = []
    seen: set[str] = set()

    # Try backtick-delimited paths first
    for p in _BACKTICK_PATH_RE.findall(text):
        if _is_file_path(p) and p not in seen:
            paths.append(p)
            seen.add(p)

    # Extract from search-pattern tokens (glob:path, grep:term:path)
    for token in text.split():
        token = token.strip(".,;:'\"()[]")
        cleaned = None
        if token.startswith("glob:"):
            cleaned = token[5:]
        elif token.startswith("grep:"):
            # grep:term:path — take the last colon-segment
            parts = token.split(":")
            if len(parts) >= 3:
                cleaned = parts[-1]
        if cleaned and "/" in cleaned and cleaned not in seen:
            paths.append(cleaned)
            seen.add(cleaned)

    # Scan for bare path-like tokens
    if not paths:
        for token in text.split():
            token = token.strip(".,;:'\"()[]")
            if "/" in token and "." in token.split("/")[-1]:
                if token not in seen:
                    paths.append(token)
                    seen.add(token)
    return paths


# ---------------------------------------------------------------------------
# 2.4 — Context bundle formatter
# ---------------------------------------------------------------------------

def format_brief(brief: TaskBrief) -> str:
    """Assemble directory trees, file headers, and anti-patterns into markdown."""
    sections: list[str] = []

    # Header
    sections.append(f"# Task Brief: {brief.task_number} — {brief.task_title}")
    sections.append(f"\nPlan: `{brief.plan_path}`\n")

    # Directory trees
    if brief.directory_trees:
        sections.append("## Directory Trees\n")
        for dir_path, tree in brief.directory_trees.items():
            sections.append(f"### `{dir_path}`\n")
            sections.append(f"```\n{tree}\n```\n")

    # File headers
    if brief.file_headers:
        sections.append("## File Headers\n")
        for file_path, header_lines in brief.file_headers.items():
            ext = Path(file_path).suffix.lstrip(".")
            lang = ext if ext else ""
            sections.append(f"### `{file_path}`\n")
            header_text = "\n".join(header_lines)
            sections.append(f"```{lang}\n{header_text}\n```\n")

    # Anti-patterns
    if brief.anti_patterns:
        sections.append("## Historical Anti-Patterns\n")
        sections.append(
            "These patterns were detected in previous sessions working on "
            "similar tasks. Avoid repeating them.\n"
        )
        for ap in brief.anti_patterns:
            tokens = ap.get("estimated_tokens_wasted", 0)
            files = ap.get("associated_files", [])
            line = f"- **{ap['pattern_type']}**: {ap['description']}"
            if tokens:
                line += f" (~{tokens} tokens wasted)"
            sections.append(line)
            if files:
                for fp in files:
                    sections.append(f"  - `{fp}`")
        sections.append("")

    # No data notice
    if not brief.directory_trees and not brief.file_headers and not brief.anti_patterns:
        sections.append(
            "*No context data available. The task does not reference "
            "any existing files or directories.*\n"
        )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_brief(
    plan_path: Path,
    task_number: str,
    *,
    repo_root: Path | None = None,
    sessions_dir: Path | None = None,
    max_header_lines: int = 20,
    max_tree_depth: int = 2,
) -> TaskBrief:
    """Generate a context brief for a specific task in a plan.

    Args:
        plan_path: Path to the plan file.
        task_number: Task number to generate brief for (e.g., "2", "2.1").
        repo_root: Repository root. Auto-detected if not specified.
        sessions_dir: Path to session archives for anti-pattern data.
        max_header_lines: Max lines to capture per file header.
        max_tree_depth: Max directory tree depth.

    Returns:
        TaskBrief with all context data and formatted markdown.
    """
    if repo_root is None:
        repo_root = _find_repo_root(plan_path)

    plan = parse_plan(plan_path)
    plan_text = plan_path.read_text()

    # Find the target task
    task = _find_task(plan, task_number)
    if task is None:
        raise ValueError(f"Task {task_number} not found in plan")

    # Extract file paths from the task and its children
    file_paths = _extract_task_paths(task, plan_text)

    # Build context
    trees = extract_directory_trees(file_paths, repo_root, max_depth=max_tree_depth)
    headers = extract_file_headers(file_paths, repo_root, max_lines=max_header_lines)
    anti_patterns = query_anti_patterns(plan_path, sessions_dir)

    brief = TaskBrief(
        task_number=task_number,
        task_title=task.title,
        plan_path=str(plan_path),
        directory_trees=trees,
        file_headers=headers,
        anti_patterns=anti_patterns,
    )
    brief.markdown = format_brief(brief)
    return brief


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_repo_root(path: Path) -> Path:
    """Walk up to find .git directory."""
    candidate = path.resolve().parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return Path.cwd()


def _find_task(plan: ParsedPlan, task_number: str) -> ParsedTask | None:
    """Find a task by number in the plan."""
    for task in plan.tasks:
        if task.number == task_number:
            return task
        for child in task.children:
            if child.number == task_number:
                return child
            for grandchild in child.children:
                if grandchild.number == task_number:
                    return grandchild
    return None


def _extract_task_paths(task: ParsedTask, plan_text: str) -> list[str]:
    """Extract file paths from a task and its children's text."""
    lines = plan_text.splitlines()
    start, end = task.line_range
    if start < 1 or end < start:
        return []

    task_block = "\n".join(lines[start - 1:end])
    raw_paths = _BACKTICK_PATH_RE.findall(task_block)
    return [p for p in raw_paths if _is_file_path(p)]
