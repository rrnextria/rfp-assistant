"""Plan content linter — validates plan quality beyond structural syntax.

Complements ``plan-verify`` (which checks structure) by validating content:
file path existence, evolution log failure patterns, task granularity, and
code-mode file references. Feeds back from the Phase 4 evolution system.

Usage:
    plan_lint.lint_plan(target) -> LintResult
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from orchestrator_v3.plan_tool import (
    ParsedPlan,
    ParsedTask,
    PlanVerificationIssue,
    PlanVerificationResult,
    parse_plan,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default task granularity thresholds (word counts)
MIN_TASK_WORDS = 20
MAX_TASK_WORDS = 300

# Known extensionless filenames that should be treated as file references
# when they appear as bare backtick strings (without a directory prefix)
_KNOWN_EXTENSIONLESS = frozenset({
    "Dockerfile", "Makefile", "Jenkinsfile", "Vagrantfile",
    "Procfile", "Gemfile", "Rakefile",
    "README", "LICENSE", "CHANGELOG", "CONTRIBUTING", "CODEOWNERS",
})

# Known dotfiles that represent actual repo files (not format descriptions)
_KNOWN_DOTFILES = frozenset({
    ".gitignore", ".gitattributes", ".gitmodules", ".gitkeep",
    ".dockerignore", ".editorconfig",
    ".env", ".env.example", ".env.local", ".env.test",
    ".prettierrc", ".eslintrc", ".babelrc",
    ".npmrc", ".nvmrc",
    ".python-version", ".ruby-version", ".node-version",
    ".flake8", ".pylintrc",
    ".clang-format", ".htaccess",
})

# Backtick-delimited path pattern:
# 1. paths ending in .ext or / (e.g., `src/main.py`, `tools/`)
# 2. paths containing / (e.g., `scripts/maistro`, `bin/run`)
# 3. known extensionless files (e.g., `Dockerfile`, `README`)
# 4. dotfiles (e.g., `.gitignore`, `.env`, `.env.example`)
_ext_alt = "|".join(re.escape(f) for f in sorted(_KNOWN_EXTENSIONLESS))
_BACKTICK_PATH_RE = re.compile(
    r"`("
    r"[^`]+?(?:\.\w+|/)"                        # paths ending in .ext or /
    r"|[^`]+/[^`/]+"                             # paths with / but no extension
    r"|(?:" + _ext_alt + r")"                    # known bare extensionless files
    r"|\.[a-zA-Z][\w.]*"                         # dotfiles (.gitignore, .env)
    r")`"
)

# Words preceding a path that indicate it's a creation target (not expected to exist).
# Per Task 1.1 spec: only "create" and "generate" are authorized skip triggers.
_CREATION_KEYWORDS = frozenset({"create", "generate"})

# Known file extensions — used to distinguish file paths from code symbols
_KNOWN_EXTENSIONS = frozenset({
    # Programming
    "py", "js", "ts", "jsx", "tsx", "go", "rs", "c", "h", "cpp", "hpp",
    "java", "rb", "pl", "php", "cs", "swift", "kt", "scala", "lua",
    "r", "m", "mm", "zig", "ex", "exs", "erl",
    # Web
    "html", "htm", "css", "scss", "sass", "less", "vue", "svelte",
    # Data/config
    "json", "yaml", "yml", "toml", "xml", "csv", "tsv", "ini", "cfg",
    "conf", "env", "properties",
    # Documentation
    "md", "rst", "txt", "adoc", "tex",
    # Shell/scripts
    "sh", "bash", "zsh", "fish", "bat", "cmd", "ps1",
    # Build/project
    "lock", "sum", "mod", "gradle", "cmake", "mk",
    # Other common
    "sql", "graphql", "proto", "log", "diff", "patch",
    "tf", "hcl", "jsonl", "ndjson",
})


def _is_file_path(path_str: str) -> bool:
    """Check if a backtick-matched string looks like a genuine file path.

    Returns False for code expressions, version numbers, dotted code symbols
    (os.execv, foo.bar), and other non-path patterns that the regex may match.
    """
    # Skip URLs, command-line flags, template vars
    if path_str.startswith(("-", "http", "$", "{", "<")):
        return False
    if "(" in path_str or ")" in path_str:
        return False
    # Skip code expressions (assignments, comparisons, spaces)
    if "=" in path_str or " " in path_str:
        return False
    # Skip Python attribute access (self.x, cls.x)
    if path_str.startswith(("self.", "cls.")):
        return False
    # For dotted names without / that don't start with .: require known extension
    # This rejects os.execv, foo.bar, PlanType.COMPLEX, v1.2.3, etc.
    if ("/" not in path_str and "." in path_str
            and not path_str.startswith(".")):
        ext = path_str.rsplit(".", 1)[-1].lower()
        if ext not in _KNOWN_EXTENSIONS:
            return False
    # For leading-dot strings without /: must be a known dotfile
    # Rejects format descriptions like .tar.gz, .sqlite, .json
    if path_str.startswith(".") and "/" not in path_str:
        if path_str not in _KNOWN_DOTFILES:
            return False
    # Must look like a file/dir path (contains / or . or is known extensionless)
    if "/" not in path_str and "." not in path_str and Path(path_str).name not in _KNOWN_EXTENSIONLESS:
        return False
    return True


# ---------------------------------------------------------------------------
# File path existence checker (Task 1.1)
# ---------------------------------------------------------------------------

def check_file_paths(
    plan: ParsedPlan,
    plan_text: str,
    repo_root: Path,
) -> list[PlanVerificationIssue]:
    """Check that backtick-delimited file paths in plan text exist in the repo.

    Skips paths that appear to be creation targets (preceded by create/generate)
    or listed under a Destination Files heading.
    """
    issues: list[PlanVerificationIssue] = []

    # Find Destination Files section content to exclude those paths
    dest_paths: set[str] = set()
    in_dest_section = False
    for line in plan_text.splitlines():
        if re.match(r"^###?\s+Destination Files", line):
            in_dest_section = True
            continue
        if in_dest_section:
            if re.match(r"^###?\s+", line):
                in_dest_section = False
                continue
            for m in _BACKTICK_PATH_RE.finditer(line):
                dest_paths.add(m.group(1))

    # Check all backtick paths in the plan
    for line_num, line in enumerate(plan_text.splitlines(), 1):
        for m in _BACKTICK_PATH_RE.finditer(line):
            path_str = m.group(1)

            # Skip if listed under Destination Files
            if path_str in dest_paths:
                continue

            # Skip if the word immediately before the backtick is a creation keyword
            prefix_words = line[:m.start()].lower().split()
            if prefix_words and prefix_words[-1] in _CREATION_KEYWORDS:
                continue

            if not _is_file_path(path_str):
                continue

            # Check existence
            full_path = repo_root / path_str
            if not full_path.exists():
                # Try to suggest similar files
                suggestion = _find_similar(path_str, repo_root)
                issues.append(PlanVerificationIssue(
                    severity="warning",
                    message=f"Referenced path does not exist: `{path_str}`",
                    line_number=line_num,
                    suggestion=suggestion,
                ))

    return issues


def _find_similar(path_str: str, repo_root: Path) -> str | None:
    """Find a similar existing file when a referenced path doesn't exist."""
    name = Path(path_str).name
    parent = repo_root / Path(path_str).parent
    if parent.is_dir():
        candidates = [f.name for f in parent.iterdir() if f.is_file()]
        for c in candidates:
            if c.startswith(name[:3]) or name in c:
                return f"Did you mean `{Path(path_str).parent / c}`?"
    return None


# ---------------------------------------------------------------------------
# Evolution log pattern checker (Task 1.2)
# ---------------------------------------------------------------------------

def check_evolution_patterns(
    plan: ParsedPlan,
    plan_text: str,
    evolution_log_path: Path | None = None,
) -> list[PlanVerificationIssue]:
    """Check plan against known failure patterns from the evolution log.

    Queries the Phase 4 evolution log for open issues and warns if the
    current plan's paths or patterns overlap with previously identified
    failure patterns.
    """
    issues: list[PlanVerificationIssue] = []

    if evolution_log_path is None or not evolution_log_path.exists():
        return issues

    try:
        from evolution.evolve.log_manager import LogManager
    except ImportError:
        logger.debug("evolution.evolve.log_manager not available, skipping pattern check")
        return issues

    mgr = LogManager(evolution_log_path)
    open_issues = mgr.query_open_issues()

    # Filter to plan-related findings only (fingerprint category = plan_quality)
    plan_issues = [e for e in open_issues if e.fingerprint.startswith("plan_quality|")]

    # Extract all file paths referenced in the plan
    plan_paths: set[str] = set()
    for m in _BACKTICK_PATH_RE.finditer(plan_text):
        plan_paths.add(m.group(1))

    # 1. Check plan-related open issues for path overlap
    for event in plan_issues:
        for affected in event.affected_paths:
            if affected in plan_paths:
                issues.append(PlanVerificationIssue(
                    severity="warning",
                    message=(
                        f"Plan references `{affected}` which has an open "
                        f"evolution issue: {event.description}"
                    ),
                    suggestion=(
                        f"Issue {event.issue_id} ({event.fingerprint}): "
                        f"consider addressing this known issue in the plan"
                    ),
                ))

    # 2. Query by fingerprint for recurring plan-quality patterns
    #    Only warn when the plan references at least one affected path
    seen_fingerprints: set[str] = set()
    for event in plan_issues:
        fp = event.fingerprint
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)

        # Only warn about recurring patterns relevant to the current plan
        has_plan_overlap = any(p in plan_paths for p in event.affected_paths)
        if not has_plan_overlap:
            continue

        # Look for similar historical patterns via fingerprint
        similar = mgr.query_by_fingerprint(fp)
        if len(similar) >= 2:
            # Recurring pattern — warn about it
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=(
                    f"Recurring evolution pattern ({len(similar)} occurrences): "
                    f"{event.description}"
                ),
                suggestion=(
                    f"Fingerprint {fp} has recurred {len(similar)} times. "
                    f"Consider updating the plan to address this pattern."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# Task granularity checker (Task 1.3)
# ---------------------------------------------------------------------------

def check_task_granularity(
    plan: ParsedPlan,
    plan_text: str,
    min_words: int = MIN_TASK_WORDS,
    max_words: int = MAX_TASK_WORDS,
) -> list[PlanVerificationIssue]:
    """Check that task descriptions are neither too vague nor too detailed.

    Tasks with < min_words may be too vague and lead to search cascades.
    Tasks with > max_words may be too detailed and cause backtracks.
    Only checks leaf-level tasks (subtasks with actual descriptions).
    """
    issues: list[PlanVerificationIssue] = []
    lines = plan_text.splitlines()

    for task in _all_tasks(plan):
        # Use only the task's own description line(s), not child task lines.
        # For leaf tasks, use the full line_range. For parent tasks, use
        # only the line up to the first child's line.
        start, end = task.line_range
        if start < 1 or end < start:
            continue

        if task.children:
            # Stop before the first child task line
            child_start = min(c.line_range[0] for c in task.children)
            end = child_start - 1

        task_text = " ".join(lines[start - 1:max(start, end)])
        word_count = len(task_text.split())

        if word_count < min_words:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=(
                    f"Task {task.number} may be too vague "
                    f"({word_count} words, minimum {min_words}): "
                    f"{task.title[:60]}"
                ),
                line_number=task.line_range[0],
                suggestion=(
                    "Vague tasks correlate with search cascades. "
                    "Consider adding target files or expected behaviors."
                ),
            ))
        elif word_count > max_words:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=(
                    f"Task {task.number} may be too detailed "
                    f"({word_count} words, maximum {max_words}): "
                    f"{task.title[:60]}"
                ),
                line_number=task.line_range[0],
                suggestion=(
                    "Overly detailed tasks correlate with backtracks. "
                    "Consider splitting into smaller subtasks."
                ),
            ))

    return issues


def _all_tasks(plan: ParsedPlan) -> list[ParsedTask]:
    """Flatten all tasks from the plan into a single list."""
    result: list[ParsedTask] = []
    for task in plan.tasks:
        result.append(task)
        for child in task.children:
            result.append(child)
            for grandchild in child.children:
                result.append(grandchild)
    return result


# ---------------------------------------------------------------------------
# Code-mode file reference checker (Task 1.4)
# ---------------------------------------------------------------------------

def check_code_mode_references(
    plan: ParsedPlan,
    plan_text: str,
) -> list[PlanVerificationIssue]:
    """Check that code-mode tasks reference at least one target file.

    A code-mode task should mention at least one file path so the coder
    knows what files to modify.
    """
    issues: list[PlanVerificationIssue] = []
    lines = plan_text.splitlines()
    code_keywords = {
        "implement", "create", "add", "write", "build", "fix", "update", "refactor",
        "change", "modify", "edit", "migrate", "remove", "delete", "replace", "patch",
        "integrate", "register", "wire", "connect", "configure", "enable", "extend",
        "inject", "hook", "port", "convert", "extract", "rename", "move", "split",
        "merge", "wrap",
    }

    # Track file refs per task number for parent-to-child inheritance.
    # Extract refs for ALL tasks (not just code tasks) so non-code parents
    # can still provide file context to code-oriented subtasks.
    task_file_refs: dict[str, list[str]] = {}

    for task in _all_tasks(plan):
        # Extract file refs from this task's own text (for all tasks)
        start, end = task.line_range
        file_refs: list[str] = []
        if start >= 1 and end >= start:
            task_end = end
            if task.children:
                child_start = min(c.line_range[0] for c in task.children)
                task_end = child_start - 1
            task_block = "\n".join(lines[start - 1:max(start, task_end)])
            path_refs = _BACKTICK_PATH_RE.findall(task_block)
            file_refs = [p for p in path_refs if _is_file_path(p)]

        if not file_refs and task.children:
            # Check if any child has file refs
            for child in task.children:
                cs, ce = child.line_range
                if cs < 1 or ce < cs:
                    continue
                child_block = "\n".join(lines[cs - 1:ce])
                child_paths = _BACKTICK_PATH_RE.findall(child_block)
                child_file_refs = [p for p in child_paths if _is_file_path(p)]
                if child_file_refs:
                    file_refs = child_file_refs
                    break

        # Inherit file refs from parent task if this subtask has none
        if not file_refs and "." in task.number:
            parent_num = task.number.rsplit(".", 1)[0]
            if parent_num in task_file_refs:
                file_refs = task_file_refs[parent_num]

        # Record this task's file refs for child inheritance
        if file_refs:
            task_file_refs[task.number] = file_refs

        # Only warn on code-oriented tasks
        title_words = set(task.title.lower().split())
        is_code_task = bool(title_words & code_keywords)
        if not is_code_task:
            continue

        if not file_refs:
            issues.append(PlanVerificationIssue(
                severity="warning",
                message=(
                    f"Task {task.number} appears to be a code task but "
                    f"does not reference any target files: {task.title[:60]}"
                ),
                line_number=task.line_range[0],
                suggestion=(
                    "Code-mode tasks should reference at least one file "
                    "path so the coder knows what to modify."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# Main lint entry point
# ---------------------------------------------------------------------------

def lint_plan(
    target: Path,
    *,
    repo_root: Path | None = None,
    evolution_log_path: Path | None = None,
    min_words: int = MIN_TASK_WORDS,
    max_words: int = MAX_TASK_WORDS,
) -> PlanVerificationResult:
    """Run all content lint checks on a plan file.

    Args:
        target: Path to the plan file.
        repo_root: Repository root for file path checking.
            Defaults to the git root if not specified.
        evolution_log_path: Path to the evolution JSONL log file.
        min_words: Minimum word count for task granularity.
        max_words: Maximum word count for task granularity.

    Returns:
        PlanVerificationResult with all lint issues.
    """
    if repo_root is None:
        # Walk up to find .git directory
        candidate = target.resolve().parent
        while candidate != candidate.parent:
            if (candidate / ".git").exists():
                repo_root = candidate
                break
            candidate = candidate.parent
        if repo_root is None:
            repo_root = Path.cwd()

    plan = parse_plan(target)
    plan_text = target.read_text()

    all_issues: list[PlanVerificationIssue] = []

    # Run all checkers
    all_issues.extend(check_file_paths(plan, plan_text, repo_root))
    all_issues.extend(check_evolution_patterns(plan, plan_text, evolution_log_path))
    all_issues.extend(check_task_granularity(plan, plan_text, min_words, max_words))
    all_issues.extend(check_code_mode_references(plan, plan_text))

    # Sort by line number
    all_issues.sort(key=lambda i: i.line_number or 0)

    errors = sum(1 for i in all_issues if i.severity == "error")
    warnings = sum(1 for i in all_issues if i.severity == "warning")

    return PlanVerificationResult(
        passed=errors == 0,
        issues=all_issues,
        summary=f"{errors} error(s), {warnings} warning(s)",
    )
