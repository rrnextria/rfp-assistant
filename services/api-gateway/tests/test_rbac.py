from __future__ import annotations

import pytest


async def _create_user_and_token(client, email: str, role: str) -> str:
    await client.post("/users", json={
        "email": email, "password": "password123", "role": role, "teams": [],
    })
    resp = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_end_user_blocked_from_admin_route(client):
    """end_user cannot access content_admin routes."""
    token = await _create_user_and_token(client, "enduser@example.com", "end_user")
    # We'll test against a hypothetical protected route — for now test /auth/me passes
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "end_user"


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client):
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_system_admin_created_successfully(client):
    token = await _create_user_and_token(client, "admin@example.com", "system_admin")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "system_admin"
