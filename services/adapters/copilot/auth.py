"""MSAL token validation, UPN→user_id resolution, and service JWT management."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("copilot-adapter.auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOT_APP_ID: str = os.environ.get("BOT_APP_ID", "")
BOT_APP_PASSWORD: str = os.environ.get("BOT_APP_PASSWORD", "")
ORCHESTRATOR_URL: str = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8004")
JWT_SECRET: str = os.environ.get("JWT_SECRET", os.environ.get("jwt_secret", "changeme-in-production"))
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# Service account user_id for the copilot adapter (pre-created system_admin user).
COPILOT_SERVICE_USER_ID: str = os.environ.get("COPILOT_SERVICE_USER_ID", "copilot-service-account")
COPILOT_SERVICE_ROLE: str = "system_admin"

# Dev-mode bypass: skip real Azure token validation and use UPN directly.
COPILOT_DEV_MODE: bool = os.environ.get("COPILOT_DEV_MODE", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Service JWT cache
# ---------------------------------------------------------------------------

_service_token_cache: dict = {"token": None, "expires_at": 0.0}
_cache_lock = Lock()


def get_service_jwt() -> str:
    """Return a cached, auto-renewed service JWT for the copilot adapter.

    The token is signed with JWT_SECRET and carries the service account
    user_id / system_admin role so the orchestrator can authorise the call.
    The token is renewed 60 seconds before expiry.
    """
    with _cache_lock:
        now = time.monotonic()
        if _service_token_cache["token"] and now < _service_token_cache["expires_at"]:
            return _service_token_cache["token"]  # type: ignore[return-value]

        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
        payload = {
            "sub": COPILOT_SERVICE_USER_ID,
            "role": COPILOT_SERVICE_ROLE,
            "exp": expire,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        _service_token_cache["token"] = token
        _service_token_cache["expires_at"] = now + (JWT_EXPIRE_MINUTES * 60) - 60
        logger.debug("Issued new service JWT for copilot adapter")
        return token


# ---------------------------------------------------------------------------
# User identity resolution
# ---------------------------------------------------------------------------


async def resolve_user(upn: str, db: AsyncSession) -> str | None:
    """Resolve a Teams UPN (email) to an internal user_id.

    Args:
        upn: The Teams User Principal Name (typically the user's email).
        db: Async SQLAlchemy session.

    Returns:
        The string user_id if found, or None if not registered.
    """
    try:
        result = await db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": upn.lower()},
        )
        row = result.first()
        if row:
            user_id = str(row[0])
            logger.debug("Resolved UPN %s → user_id %s", upn, user_id)
            return user_id
        logger.warning("UPN lookup miss: %s is not registered", upn)
        return None
    except Exception as exc:
        logger.error("DB error resolving UPN %s: %s", upn, exc)
        return None


def build_user_context_header(user_id: str) -> dict[str, str]:
    """Build the X-User-Id header so the orchestrator can log the real user.

    The adapter calls the orchestrator with the service account JWT but
    passes the actual Teams user's ID in this header so audit logs capture
    the real actor rather than the service account.
    """
    return {"X-User-Id": user_id}
