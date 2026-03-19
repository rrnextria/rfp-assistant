"""ORCH_META machine-readable verdict protocol and approval parsing.

The ORCH_META protocol uses an HTML comment block placed at the **top** of
reviewer-generated ``.md`` files.  It encodes the review verdict and severity
counts in a structured, grep-proof format that prevents the false-approval bug
present in v1 (where prompt instruction text containing the approval string was
captured to ``.log`` files and matched by ``grep``).

Format specification
--------------------

The block MUST appear within the **first 50 lines** of the file::

    <!-- ORCH_META
    VERDICT: APPROVED
    BLOCKER: 0
    MAJOR: 0
    MINOR: 0
    DECISIONS: 0
    VERIFIED: 9
    -->

Recognised keys (case-insensitive — keys are normalised to uppercase):
    VERDICT     -- ``APPROVED`` or ``FIXES_REQUIRED``
    BLOCKER     -- integer count of blocker-severity findings
    MAJOR       -- integer count of major-severity findings
    MINOR       -- integer count of minor-severity findings
    DECISIONS   -- integer count of open decision requests
    VERIFIED    -- integer count of verified items

Unknown keys are silently ignored.  The ``VERDICT`` key is **mandatory** -- if
it is missing, the block is considered malformed and ``parse_orch_meta``
returns ``None``.

``FIXES_REQUIRED`` example::

    <!-- ORCH_META
    VERDICT: FIXES_REQUIRED
    BLOCKER: 1
    MAJOR: 2
    MINOR: 1
    DECISIONS: 0
    VERIFIED: 5
    -->

Fail-closed design
------------------
If the file is missing, the ORCH_META block is absent, or the block is
malformed (missing VERDICT, missing required count keys for APPROVED,
non-numeric counts, or truncated — i.e. no closing ``-->`` within 50
lines), ``parse_orch_meta`` returns ``None`` and ``check_approved``
returns ``False``.  This causes the orchestration loop to continue to the
next round rather than falsely approving.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_SCAN_LINES = 50
_START_MARKER = "<!-- ORCH_META"
_END_MARKER = "-->"

_COUNT_KEYS = ("BLOCKER", "MAJOR", "MINOR", "DECISIONS", "VERIFIED")


class Verdict(Enum):
    """Review verdict values matching ORCH_META VERDICT key."""

    APPROVED = "APPROVED"
    FIXES_REQUIRED = "FIXES_REQUIRED"


@dataclass
class ReviewResult:
    """Parsed result from an ORCH_META block."""

    verdict: Verdict
    blocker: int = 0
    major: int = 0
    minor: int = 0
    decisions: int = 0
    verified: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_orch_meta(filepath: Path) -> ReviewResult | None:
    """Parse an ORCH_META block from a review artifact file.

    Returns a ``ReviewResult`` on success, or ``None`` if the file is
    missing, has no ORCH_META block within the first 50 lines, or the
    block is malformed (missing VERDICT, non-numeric counts).
    """
    if not filepath.exists():
        return None

    try:
        lines = filepath.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    # Scan for start marker within first _MAX_SCAN_LINES lines.
    # The safety bound applies to both the search for the start marker AND
    # the block content — the entire block must fit within _MAX_SCAN_LINES lines.
    in_block = False
    block_closed = False
    kv: dict[str, str] = {}

    for i, raw_line in enumerate(lines[:_MAX_SCAN_LINES]):
        line = raw_line.strip()

        if not in_block:
            if line.startswith(_START_MARKER):
                in_block = True
            continue

        # Inside the block
        if line == _END_MARKER or line.endswith(_END_MARKER):
            block_closed = True
            break

        if ":" in line:
            key, _, value = line.partition(":")
            kv[key.strip().upper()] = value.strip()

    if not in_block:
        logger.warning(
            "No ORCH_META block found in first %d lines of %s",
            _MAX_SCAN_LINES,
            filepath,
        )
        return None

    if not block_closed:
        logger.warning(
            "ORCH_META block in %s is truncated (no closing --> within %d lines)",
            filepath,
            _MAX_SCAN_LINES,
        )
        return None

    # Validate mandatory VERDICT key
    verdict_str = kv.get("VERDICT")
    if not verdict_str:
        logger.warning(
            "ORCH_META block in %s is missing the VERDICT key", filepath
        )
        return None

    try:
        verdict = Verdict(verdict_str.upper())
    except ValueError:
        logger.warning(
            "ORCH_META block in %s has invalid VERDICT value: %r",
            filepath,
            verdict_str,
        )
        return None

    # Parse count fields
    counts: dict[str, int] = {}
    for key in _COUNT_KEYS:
        raw = kv.get(key)
        if raw is not None:
            try:
                counts[key.lower()] = int(raw)
            except ValueError:
                logger.warning(
                    "ORCH_META block in %s has non-numeric %s value: %r",
                    filepath,
                    key,
                    raw,
                )
                return None

    # When verdict is APPROVED, require all four severity count keys to be
    # explicitly present.  A missing count key could mask unresolved findings.
    if verdict == Verdict.APPROVED:
        required = ("BLOCKER", "MAJOR", "MINOR", "DECISIONS")
        missing = [k for k in required if k not in kv]
        if missing:
            logger.warning(
                "ORCH_META block in %s has VERDICT=APPROVED but missing "
                "required count keys: %s",
                filepath,
                ", ".join(missing),
            )
            return None

    return ReviewResult(
        verdict=verdict,
        blocker=counts.get("blocker", 0),
        major=counts.get("major", 0),
        minor=counts.get("minor", 0),
        decisions=counts.get("decisions", 0),
        verified=counts.get("verified", 0),
    )


def check_approved(filepath: Path) -> bool:
    """Check whether a review artifact constitutes an approval.

    Returns ``True`` only when:
    1. ``parse_orch_meta`` succeeds (not None).
    2. The verdict is ``APPROVED``.
    3. All of blocker, major, minor, and decisions are exactly 0.

    DECISIONS intentionally blocks approval: an open decision request means
    the coder/planner must acknowledge a design choice before the review can
    be considered complete.

    **Warnings:** This function returns only a ``bool``.  Callers who need
    to inspect non-fatal warnings (e.g. APPROVED with non-zero counts)
    should call ``parse_orch_meta()`` directly and examine the
    ``ReviewResult.warnings`` list.
    """
    result = parse_orch_meta(filepath)
    if result is None:
        return False

    if result.verdict != Verdict.APPROVED:
        return False

    # Check all severity counts are zero
    non_zero: list[str] = []
    if result.blocker != 0:
        non_zero.append(f"blocker={result.blocker}")
    if result.major != 0:
        non_zero.append(f"major={result.major}")
    if result.minor != 0:
        non_zero.append(f"minor={result.minor}")
    if result.decisions != 0:
        non_zero.append(f"decisions={result.decisions}")

    if non_zero:
        warning = (
            f"VERDICT=APPROVED but non-zero counts in {filepath}: "
            + ", ".join(non_zero)
        )
        logger.warning(warning)
        result.warnings.append(warning)
        return False

    return True


# ── RESEARCH_META protocol ────────────────────────────────────────────

_RESEARCH_START_MARKER = "<!-- RESEARCH_META"

_RESEARCH_KEYS = ("AGREEMENT", "OPEN_ISSUES")


@dataclass
class ResearchResult:
    """Parsed result from a RESEARCH_META block."""

    agreement: int = 0
    open_issues: int = 0
    delta: str = ""


def parse_research_meta(filepath: Path) -> ResearchResult | None:
    """Parse a RESEARCH_META block from a convergence artifact.

    Returns a ``ResearchResult`` on success, or ``None`` if the file is
    missing, has no RESEARCH_META block within the first 50 lines, or
    the block is malformed.
    """
    if not filepath.exists():
        return None

    try:
        lines = filepath.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    in_block = False
    block_closed = False
    kv: dict[str, str] = {}

    for raw_line in lines[:_MAX_SCAN_LINES]:
        line = raw_line.strip()

        if not in_block:
            if line.startswith(_RESEARCH_START_MARKER):
                in_block = True
            continue

        if line == _END_MARKER or line.endswith(_END_MARKER):
            block_closed = True
            break

        if ":" in line:
            key, _, value = line.partition(":")
            kv[key.strip().upper()] = value.strip()

    if not in_block:
        logger.warning(
            "No RESEARCH_META block found in first %d lines of %s",
            _MAX_SCAN_LINES,
            filepath,
        )
        return None

    if not block_closed:
        logger.warning(
            "RESEARCH_META block in %s is truncated (no closing --> within %d lines)",
            filepath,
            _MAX_SCAN_LINES,
        )
        return None

    # Parse required integer keys
    counts: dict[str, int] = {}
    for key in _RESEARCH_KEYS:
        raw = kv.get(key)
        if raw is None:
            logger.warning(
                "RESEARCH_META block in %s is missing required key: %s",
                filepath,
                key,
            )
            return None
        try:
            counts[key.lower()] = int(raw)
        except ValueError:
            logger.warning(
                "RESEARCH_META block in %s has non-numeric %s value: %r",
                filepath,
                key,
                raw,
            )
            return None

    return ResearchResult(
        agreement=counts.get("agreement", 0),
        open_issues=counts.get("open_issues", 0),
        delta=kv.get("DELTA", ""),
    )


def check_converged(filepath: Path) -> bool:
    """Check whether a convergence artifact indicates convergence.

    Returns ``True`` only when AGREEMENT >= 8 AND OPEN_ISSUES == 0.
    """
    result = parse_research_meta(filepath)
    if result is None:
        return False
    return result.agreement >= 8 and result.open_issues == 0
