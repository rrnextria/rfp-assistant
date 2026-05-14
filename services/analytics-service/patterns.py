"""Past-proposal outcome aggregation + min-N gating.

A pattern emits a non-zero boost only once the per-pattern sample size
crosses the configured threshold. Below the threshold the system is
honest: no learned signal yet.
"""
from __future__ import annotations

from collections import defaultdict


def compute_patterns(rows: list[dict]) -> list[dict]:
    """Group rows by industry_id (None is its own bucket). Compute per-bucket
    n_total, n_won, win_rate. Value-bucket aggregation is a phase-2 follow-up."""
    grouped: dict[str | None, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r.get("industry_id")].append(r)
    out: list[dict] = []
    for industry_id, group in grouped.items():
        n_total = len(group)
        n_won = sum(1 for g in group if g["outcome"] == "won")
        win_rate = (n_won / n_total) if n_total else 0.0
        out.append({"industry_id": industry_id, "n_total": n_total,
                     "n_won": n_won, "win_rate": round(win_rate, 4)})
    return out


def gate_patterns(patterns: list[dict], *, min_n: int = 20,
                   max_boost: float = 0.10) -> list[dict]:
    """Apply min-N gating. Below threshold: boost=0, active=False.
    Above threshold: boost = max_boost * (win_rate - 0.5) * 2, clipped to
    [-max_boost, +max_boost]."""
    out: list[dict] = []
    for p in patterns:
        if p["n_total"] < min_n:
            out.append({**p, "boost": 0.0, "active": False})
            continue
        raw = max_boost * (p["win_rate"] - 0.5) * 2.0
        clipped = max(-max_boost, min(max_boost, round(raw, 4)))
        out.append({**p, "boost": clipped, "active": True})
    return out
