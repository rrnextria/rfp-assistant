#!/usr/bin/env python3
"""
Generate embeddings for any chunks that are missing them.
Run inside the content-service container:

    docker compose exec content-service python /app/embed_chunks.py

Or from the project root (if sentence-transformers is installed locally):

    python scripts/embed_chunks.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
sys.path.insert(0, "/common")

import asyncpg

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/rfpassistant",
)


async def main() -> None:
    print("Connecting to database…")
    conn = await asyncpg.connect(DB_URL.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", ""))

    rows = await conn.fetch(
        "SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id"
    )
    print(f"Found {len(rows)} chunks without embeddings.")

    if not rows:
        print("Nothing to do.")
        await conn.close()
        return

    print("Loading sentence-transformers model (all-MiniLM-L6-v2)…")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")

    texts = [r["text"] for r in rows]
    ids = [r["id"] for r in rows]

    print(f"Embedding {len(texts)} chunks…")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    print("Writing embeddings to database…")
    updated = 0
    for chunk_id, embedding in zip(ids, embeddings):
        vec_str = f"[{','.join(str(float(v)) for v in embedding)}]"
        await conn.execute(
            "UPDATE chunks SET embedding = $1::vector WHERE id = $2",
            vec_str, chunk_id,
        )
        updated += 1

    await conn.close()
    print(f"Done — updated {updated} chunks with embeddings.")


if __name__ == "__main__":
    asyncio.run(main())
