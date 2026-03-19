from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.db import get_db

security = HTTPBearer(auto_error=False)


@dataclass
class UserContext:
    user_id: str
    role: str
    teams: list[str] = field(default_factory=list)


async def load_user_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> UserContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        settings = get_settings()
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        role = payload.get("role", "end_user")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    teams_result = await db.execute(
        text("SELECT t.name FROM teams t JOIN user_teams ut ON t.id = ut.team_id WHERE ut.user_id = :uid"),
        {"uid": user_id},
    )
    teams = [r[0] for r in teams_result.fetchall()]
    return UserContext(user_id=user_id, role=role, teams=teams)


def require_role(*allowed_roles: str):
    """FastAPI dependency factory that enforces role-based access."""

    async def dependency(user_ctx: UserContext = Depends(load_user_context)) -> UserContext:
        if user_ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_ctx.role}' is not permitted. Required: {allowed_roles}",
            )
        return user_ctx

    return dependency
