from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_log_action_inserts_row(db_session):
    import sys
    sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/audit-service")
    from logger import log_action

    user_id = str(uuid.uuid4())
    action = "TEST POST /test"
    payload = {"key": "value", "password": "secret"}

    await log_action(db_session, user_id, action, payload)

    result = await db_session.execute(
        text("SELECT action, payload FROM audit_logs WHERE action = :action"),
        {"action": action},
    )
    row = result.mappings().first()
    assert row is not None
    assert row["action"] == action
    parsed = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
    assert parsed.get("password") == "***REDACTED***"
    assert parsed.get("key") == "value"
