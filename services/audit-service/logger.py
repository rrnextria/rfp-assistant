from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("audit-service")

_SENSITIVE_KEYS = re.compile(r"password|secret|token|key|hash", re.IGNORECASE)


def _sanitize(payload: dict) -> dict:
    """Strip sensitive keys from payload before logging."""
    return {k: "***REDACTED***" if _SENSITIVE_KEYS.search(k) else v for k, v in payload.items()}


async def log_action(
    db: AsyncSession,
    user_id: str | None,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert one row into audit_logs. Call via BackgroundTasks to avoid blocking."""
    safe_payload = _sanitize(payload or {})
    try:
        await db.execute(
            text(
                "INSERT INTO audit_logs (user_id, action, payload) VALUES (:uid, :action, :payload::jsonb)"
            ),
            {"uid": user_id, "action": action, "payload": __import__("json").dumps(safe_payload)},
        )
        await db.commit()
    except Exception as exc:
        logger.error(f"Failed to write audit log: {exc}")
