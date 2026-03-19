#!/usr/bin/env python3
"""
Demo data seed script for RFP Assistant.

Creates a demo organization with accounts you can log in with and test:

  system_admin  — admin@demo.com       / Demo@1234
  content_admin — content@demo.com     / Demo@1234
  end_user      — user@demo.com        / Demo@1234

Also seeds:
  - 2 teams: Engineering, Sales
  - 1 sample product (Cloud Storage Suite)
  - 1 sample document (approved, with searchable chunks)
  - 1 sample RFP with questions and a draft answer

Run after migrations:
    python scripts/seed_demo.py
    # or inside Docker:
    docker compose exec api-gateway python /app/../scripts/seed_demo.py
"""

import asyncio
import os
import sys

# Ensure the repo root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/rfpassistant",
)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

TEAMS = [
    {"name": "Engineering"},
    {"name": "Sales"},
]

USERS = [
    {
        "email": "admin@demo.com",
        "role": "system_admin",
        "password": "Demo@1234",
        "teams": ["Engineering", "Sales"],
    },
    {
        "email": "content@demo.com",
        "role": "content_admin",
        "password": "Demo@1234",
        "teams": ["Engineering"],
    },
    {
        "email": "user@demo.com",
        "role": "end_user",
        "password": "Demo@1234",
        "teams": ["Sales"],
    },
]

PRODUCT = {
    "name": "Cloud Storage Suite",
    "vendor": "Nextria",
    "category": "Storage",
    "description": (
        "Enterprise-grade cloud object storage with AES-256 encryption at rest, "
        "TLS 1.3 in transit, SOC 2 Type II certified, and 99.999% durability SLA. "
        "Supports versioning, lifecycle policies, cross-region replication, and "
        "S3-compatible API."
    ),
    "features": {
        "encryption_at_rest": "AES-256",
        "encryption_in_transit": "TLS 1.3",
        "certification": "SOC 2 Type II",
        "durability_sla": "99.999%",
        "api_compatibility": "S3-compatible",
        "versioning": True,
        "cross_region_replication": True,
    },
}

DOCUMENT_CHUNKS = [
    {
        "heading": "Security Overview",
        "text": (
            "Cloud Storage Suite provides AES-256 encryption at rest and TLS 1.3 for "
            "all data in transit. All data centres are SOC 2 Type II certified and "
            "undergo annual third-party penetration testing."
        ),
    },
    {
        "heading": "Durability and Availability",
        "text": (
            "The platform delivers 99.999% data durability through erasure coding across "
            "a minimum of three availability zones. An availability SLA of 99.9% is "
            "backed by financial credits."
        ),
    },
    {
        "heading": "Compliance",
        "text": (
            "Cloud Storage Suite is GDPR-compliant, supports data residency requirements "
            "in the EU, US, and APAC, and provides immutable audit logs for all object "
            "operations."
        ),
    },
    {
        "heading": "Integration",
        "text": (
            "The S3-compatible REST API allows drop-in replacement of Amazon S3 with "
            "no client code changes. SDKs are available for Python, Java, Go, and .NET."
        ),
    },
]

RFP = {
    "customer": "Acme Corp",
    "industry": "Financial Services",
    "region": "North America",
    "raw_text": "Sample RFP for cloud storage procurement.",
}

RFP_QUESTIONS = [
    "Does the solution support AES-256 encryption at rest?",
    "What durability SLA does the solution offer?",
    "Is the solution SOC 2 Type II certified?",
    "Does the solution provide an S3-compatible API?",
]

DRAFT_ANSWER = (
    "Yes. Cloud Storage Suite encrypts all data at rest using AES-256 and uses "
    "TLS 1.3 for data in transit. The solution is SOC 2 Type II certified with "
    "annual penetration testing, delivers 99.999% durability, and provides a "
    "fully S3-compatible REST API."
)


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        print("Seeding demo data...")

        # ── Teams ──────────────────────────────────────────────────────────
        team_ids: dict[str, str] = {}
        for t in TEAMS:
            row = await db.execute(
                text(
                    "INSERT INTO teams (name) VALUES (:name) "
                    "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                    "RETURNING id"
                ),
                {"name": t["name"]},
            )
            team_ids[t["name"]] = str(row.scalar())
        print(f"  ✓ Teams: {list(team_ids.keys())}")

        # ── Users ──────────────────────────────────────────────────────────
        user_ids: dict[str, str] = {}
        for u in USERS:
            hashed = pwd_ctx.hash(u["password"])
            row = await db.execute(
                text(
                    "INSERT INTO users (email, role, password_hash) "
                    "VALUES (:email, :role, :pw) "
                    "ON CONFLICT (email) DO UPDATE "
                    "SET role = EXCLUDED.role, password_hash = EXCLUDED.password_hash "
                    "RETURNING id"
                ),
                {"email": u["email"], "role": u["role"], "pw": hashed},
            )
            uid = str(row.scalar())
            user_ids[u["email"]] = uid

            for team_name in u["teams"]:
                await db.execute(
                    text(
                        "INSERT INTO user_teams (user_id, team_id) "
                        "VALUES (:uid, :tid) ON CONFLICT DO NOTHING"
                    ),
                    {"uid": uid, "tid": team_ids[team_name]},
                )
        print(f"  ✓ Users: {[u['email'] for u in USERS]}")

        # ── Product ────────────────────────────────────────────────────────
        import json
        row = await db.execute(
            text(
                "INSERT INTO products (name, vendor, category, description, features) "
                "VALUES (:name, :vendor, :category, :desc, :features::jsonb) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            {
                "name": PRODUCT["name"],
                "vendor": PRODUCT["vendor"],
                "category": PRODUCT["category"],
                "desc": PRODUCT["description"],
                "features": json.dumps(PRODUCT["features"]),
            },
        )
        product_id = row.scalar()
        if product_id is None:
            r = await db.execute(
                text("SELECT id FROM products WHERE name = :name"),
                {"name": PRODUCT["name"]},
            )
            product_id = r.scalar()
        print(f"  ✓ Product: {PRODUCT['name']} ({product_id})")

        # ── Document + chunks ──────────────────────────────────────────────
        admin_id = user_ids["admin@demo.com"]
        eng_team_id = team_ids["Engineering"]
        sales_team_id = team_ids["Sales"]

        doc_meta = {
            "product": "Cloud Storage Suite",
            "region": "North America",
            "industry": "Financial Services",
            "approved": True,
            "allowed_roles": ["system_admin", "content_admin", "end_user"],
            "allowed_teams": [eng_team_id, sales_team_id],
        }

        row = await db.execute(
            text(
                "INSERT INTO documents (title, status, metadata, created_by) "
                "VALUES (:title, 'ready', :meta::jsonb, :uid) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            {
                "title": "Cloud Storage Suite — Product Brief",
                "meta": json.dumps(doc_meta),
                "uid": admin_id,
            },
        )
        doc_id = row.scalar()
        if doc_id is None:
            r = await db.execute(
                text("SELECT id FROM documents WHERE title = :t"),
                {"t": "Cloud Storage Suite — Product Brief"},
            )
            doc_id = r.scalar()

        for chunk in DOCUMENT_CHUNKS:
            chunk_meta = {**doc_meta, "heading": chunk["heading"]}
            await db.execute(
                text(
                    "INSERT INTO chunks (document_id, text, metadata) "
                    "VALUES (:did, :text, :meta::jsonb) ON CONFLICT DO NOTHING"
                ),
                {
                    "did": doc_id,
                    "text": chunk["text"],
                    "meta": json.dumps(chunk_meta),
                },
            )
        print(f"  ✓ Document + {len(DOCUMENT_CHUNKS)} chunks seeded")

        # ── RFP + questions + draft answer ─────────────────────────────────
        row = await db.execute(
            text(
                "INSERT INTO rfps (customer, industry, region, raw_text, created_by) "
                "VALUES (:customer, :industry, :region, :raw, :uid) "
                "ON CONFLICT DO NOTHING RETURNING id"
            ),
            {
                "customer": RFP["customer"],
                "industry": RFP["industry"],
                "region": RFP["region"],
                "raw": RFP["raw_text"],
                "uid": admin_id,
            },
        )
        rfp_id = row.scalar()
        if rfp_id is None:
            r = await db.execute(
                text("SELECT id FROM rfps WHERE customer = :c"),
                {"c": RFP["customer"]},
            )
            rfp_id = r.scalar()

        first_qid = None
        for i, q in enumerate(RFP_QUESTIONS):
            row = await db.execute(
                text(
                    "INSERT INTO rfp_questions (rfp_id, question) "
                    "VALUES (:rfp_id, :q) ON CONFLICT DO NOTHING RETURNING id"
                ),
                {"rfp_id": rfp_id, "q": q},
            )
            qid = row.scalar()
            if qid is None:
                r = await db.execute(
                    text("SELECT id FROM rfp_questions WHERE rfp_id=:r AND question=:q"),
                    {"r": rfp_id, "q": q},
                )
                qid = r.scalar()
            if i == 0:
                first_qid = qid

        # Draft answer for the first question
        if first_qid:
            await db.execute(
                text(
                    "INSERT INTO rfp_answers "
                    "(question_id, answer, version, approved, detail_level) "
                    "VALUES (:qid, :ans, 1, false, 'balanced') "
                    "ON CONFLICT DO NOTHING"
                ),
                {"qid": first_qid, "ans": DRAFT_ANSWER},
            )
        print(f"  ✓ RFP '{RFP['customer']}' + {len(RFP_QUESTIONS)} questions + 1 draft answer")

        await db.commit()

    await engine.dispose()

    print("\nDemo data seeded successfully!")
    print("\nLogin credentials:")
    print("  system_admin  → admin@demo.com    / Demo@1234")
    print("  content_admin → content@demo.com  / Demo@1234")
    print("  end_user      → user@demo.com     / Demo@1234")
    print(f"\nSample RFP customer: {RFP['customer']}")
    print("API: http://localhost:8000")
    print("UI:  http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(seed())
