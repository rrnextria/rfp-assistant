"""Tenant scoping for SQLAlchemy queries.

Code-review rule: any query touching a tenant-scoped table without this
helper is a tenancy leak.
"""
from __future__ import annotations

from typing import Any


def tenant_scope(query: Any, tenant_id: str, table: Any) -> Any:
    """Add WHERE tenant_id = :tenant_id to a query."""
    return query.where(table.c.tenant_id == tenant_id)
