# Migrations

Alembic migrations for the RFP Assistant database.

## Running Migrations

```bash
# Apply all migrations
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/rfpassistant alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "your migration description"

# Check current revision
alembic current

# View migration history
alembic history
```

## Migration History

| Revision | Description |
|----------|-------------|
| 0001 | Enable pgvector extension |
| 0002 | Full schema (users, teams, documents, chunks, rfps) |
| 0003 | FTS index (tsvector on chunks) |
| 0004 | Tenant config column on users |
| 0005 | Portfolio schema (products, product_embeddings) |
| 0006 | Win/loss lessons and score adjustments |

## Verified Run (2026-03-18)

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Enable pgvector extension
```
