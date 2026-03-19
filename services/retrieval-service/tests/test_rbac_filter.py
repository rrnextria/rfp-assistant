from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/retrieval-service")


def test_build_rbac_filter_includes_approved():
    from rbac_filter import UserContext, build_rbac_filter

    ctx = UserContext(user_id="u1", role="end_user", teams=["team-a"])
    where = build_rbac_filter(ctx)
    assert "approved" in where
    assert "allowed_roles" in where


def test_build_rbac_filter_role():
    from rbac_filter import UserContext, build_rbac_filter

    ctx = UserContext(user_id="u1", role="content_admin", teams=[])
    where = build_rbac_filter(ctx)
    assert "content_admin" in where


def test_build_rbac_filter_empty_teams():
    from rbac_filter import UserContext, build_rbac_filter

    ctx = UserContext(user_id="u1", role="end_user", teams=[])
    where = build_rbac_filter(ctx)
    # With no teams, should only allow chunks with empty allowed_teams
    assert "allowed_teams" in where
