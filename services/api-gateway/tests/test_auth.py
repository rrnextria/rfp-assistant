from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_user_and_login(client):
    # Create user
    resp = await client.post("/users", json={
        "email": "test@example.com",
        "name": "Test User",
        "role": "end_user",
        "teams": ["team-a"],
        "password": "testpassword123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "user_id" in data

    # Login
    resp = await client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123",
    })
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # GET /me
    token = token_data["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == "test@example.com"
    assert me["role"] == "end_user"
    assert "team-a" in me["teams"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/users", json={
        "email": "wrong@example.com", "password": "correct", "role": "end_user", "teams": [],
    })
    resp = await client.post("/auth/login", json={"email": "wrong@example.com", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_no_token(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
