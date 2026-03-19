from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class UserContext:
    user_id: str
    role: str
    teams: list[str] = field(default_factory=list)


def build_rbac_filter(user_ctx: UserContext) -> str:
    """
    Returns a SQL WHERE clause fragment for RBAC enforcement on chunks.

    Filters:
    - chunks.metadata['approved'] must be true
    - chunks.metadata['allowed_roles'] must contain user's role
    - chunks.metadata['allowed_teams'] must overlap with user's teams (or teams list is empty)
    """
    role_literal = user_ctx.role.replace("'", "''")

    conditions = [
        "(metadata->>'approved')::boolean = true",
        f"metadata->'allowed_roles' @> '\"{role_literal}\"'::jsonb",
    ]

    if user_ctx.teams:
        # Build a JSON array of team names for overlap check
        team_json = "[" + ",".join(f'"{t.replace(chr(39), chr(39)*2)}"' for t in user_ctx.teams) + "]"
        conditions.append(
            f"(metadata->'allowed_teams' @> '{team_json}'::jsonb "
            f"OR metadata->'allowed_teams' = '[]'::jsonb)"
        )
    else:
        # No teams: only allow chunks with empty allowed_teams
        conditions.append("metadata->'allowed_teams' = '[]'::jsonb")

    return " AND ".join(conditions)


def build_metadata_filter(filters: dict) -> str:
    """Build optional metadata equality filters (product, industry, etc.)."""
    parts = []
    for key, value in filters.items():
        if key in ("product", "industry", "region") and value:
            safe_val = str(value).replace("'", "''")
            parts.append(f"metadata->>'\"'{key}'\"' = '{safe_val}'")
    return " AND ".join(parts) if parts else ""
