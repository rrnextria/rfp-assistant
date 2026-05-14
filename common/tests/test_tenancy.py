from sqlalchemy import column, table, select

from common.tenancy import tenant_scope


def test_tenant_scope_adds_where_clause():
    t = table("docs", column("id"), column("tenant_id"))
    base = select(t.c.id)
    scoped = tenant_scope(base, "t-123", t)
    sql = str(scoped.compile(compile_kwargs={"literal_binds": True}))
    assert "tenant_id = 't-123'" in sql
