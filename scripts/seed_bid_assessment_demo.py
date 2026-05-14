"""Seed rich demo data for the bid-assessment workflow.

Idempotent: every insert uses ON CONFLICT or skips when matching rows exist.
Safe to re-run.

What this script seeds for the default tenant (Akkodis):
  - 5-dim capability profile: 3 industries, 3 geographies, 2 certs, 3
    service lines (with industry/geography links), products kept as-is.
  - 8 boilerplate snippets covering the most common RFP topics.
  - 25 past_proposals across the 3 industries with mixed outcomes — enough
    to push at least one pattern past the min-N=20 analytics gate.
  - 5 contracts.
  - 3 rich demo RFPs with real raw_text and extracted requirements (uses
    the existing RequirementExtractionAgent prefix detection — "shall",
    "must", etc. — so requirements actually populate).

Usage (from project root, with services already up):
    docker compose exec -T api-gateway python /scripts/seed_bid_assessment_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date, timedelta

# Make common/ + the agents importable when run from /scripts inside the
# api-gateway container (which mounts /scripts).
sys.path.insert(0, "/")
sys.path.insert(0, "/common")
sys.path.insert(0, "/app")  # gateway container default
for content_path in ("/services/content-service", "/app"):
    if os.path.isdir(content_path):
        sys.path.insert(0, content_path)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@postgres:5432/rfpassistant",
)

# Reproducible
random.seed(42)


SNIPPETS = [
    ("GDPR posture",
     "Akkodis processes personal data per Articles 6 and 9 of the GDPR. "
     "We sign Data Processing Agreements with controllers, honour Data "
     "Subject Access Requests within 30 days, and maintain documented "
     "breach-notification procedures aligned to the 72-hour reporting "
     "obligation.",
     ["gdpr", "privacy"]),
    ("SOC 2 Type II",
     "Akkodis holds an active SOC 2 Type II report covering the security, "
     "availability, and confidentiality trust services criteria. The full "
     "report is furnished under NDA at proposal stage.",
     ["soc2", "security"]),
    ("ISO 27001",
     "Akkodis maintains an ISO 27001-certified Information Security "
     "Management System covering global delivery operations. The certificate "
     "is available on request.",
     ["iso27001", "security"]),
    ("Standard SLA — Gold tier",
     "Gold tier delivers 99.95% monthly availability, P1 ticket response "
     "within 30 minutes 24×7, RTO 4 hours, RPO 1 hour, and a dedicated "
     "service manager. Monthly governance and quarterly business reviews.",
     ["sla", "support"]),
    ("Multi-factor authentication",
     "All Akkodis personnel accessing customer environments authenticate via "
     "phishing-resistant MFA (FIDO2/WebAuthn). Conditional-access policies "
     "enforce device-trust and managed-network requirements.",
     ["mfa", "security"]),
    ("Data residency",
     "Customer data is hosted in the region specified by the customer. We "
     "support Canada (Central + East), United States (East-1/East-2/West-2), "
     "and the EU (Frankfurt, Ireland, Paris). Data does not cross region "
     "boundaries without written instruction.",
     ["data-residency", "privacy"]),
    ("Escalation matrix",
     "Tier-1 → Tier-2 → Engagement Manager → Delivery Director. P1 "
     "escalations to the Delivery Director within 1 hour. P2 within 4 hours. "
     "Named executive sponsor for every engagement above $500k.",
     ["escalation", "support"]),
    ("Background screening",
     "All personnel undergo a background screening including identity, "
     "criminal-record check (where legally permitted), and prior-employment "
     "verification before being assigned to a customer engagement.",
     ["background-check", "compliance"]),
]


# 3 service lines × industries × geographies for matrix demos
INDUSTRIES = [
    ("Banking & Financial Services", "banking"),
    ("Healthcare", "healthcare"),
    ("Public Sector", "public-sector"),
]
GEOGRAPHIES = [
    ("Canada", "country"),
    ("United States", "country"),
    ("EMEA", "region"),
]
CERTIFICATIONS = [
    ("ISO 27001", "BSI", "Global ISMS coverage"),
    ("SOC 2 Type II", "AICPA", "Security, availability, confidentiality"),
]
SERVICE_LINES = [
    ("Cloud Migration",
     "End-to-end migration of legacy workloads to AWS, Azure, or GCP, "
     "including landing-zone design, application modernisation, and "
     "operational handover.",
     ["Banking & Financial Services", "Healthcare"],
     ["Canada", "United States"]),
    ("Cybersecurity Advisory",
     "ISO 27001 / SOC 2 readiness, threat-model workshops, zero-trust "
     "design, identity rationalisation, and incident-response retainer.",
     ["Banking & Financial Services", "Public Sector"],
     ["Canada", "EMEA"]),
    ("Data & Analytics",
     "Lakehouse architecture (Databricks / Snowflake / Fabric), BI "
     "modernisation, ML feature stores, and applied analytics for "
     "regulated industries.",
     ["Healthcare", "Public Sector"],
     ["United States", "EMEA"]),
]


DEMO_RFP_TEMPLATES = [
    {
        "customer": "Meridian Trust Bank",
        "industry": "Banking & Financial Services",
        "region": "Canada",
        "raw_text": (
            "REQUEST FOR PROPOSAL — Cloud Migration & Modernisation\n\n"
            "Meridian Trust Bank ('Meridian') is soliciting proposals for "
            "the migration of its core deposit and payments platform from "
            "an on-premise mainframe environment to a major public cloud "
            "provider. The selected vendor will be responsible for "
            "discovery, landing-zone design, application refactor, and "
            "operational hand-over.\n\n"
            "SCOPE OF WORK\n"
            "The vendor shall conduct a discovery and assessment of the "
            "in-scope applications within the first 60 days of engagement.\n"
            "The vendor shall design and implement a multi-account landing "
            "zone aligned to the cloud provider's well-architected "
            "framework.\n"
            "The vendor shall migrate the workloads with zero data loss "
            "and a maximum of 4 hours of planned downtime per cutover "
            "event.\n"
            "Must demonstrate active SOC 2 Type II attestation covering "
            "security, availability, and confidentiality criteria.\n"
            "Must provide ISO 27001 certification covering the delivery "
            "geography.\n"
            "Shall maintain GDPR-equivalent data-processing controls "
            "consistent with Canadian PIPEDA.\n"
            "Should provide a dedicated escalation matrix with executive "
            "sponsor named in the response.\n"
            "Required: data residency in Canada-Central or Canada-East.\n"
            "Required: 24×7 P1 response within 30 minutes.\n\n"
            "COMMERCIAL\n"
            "Engagement value is estimated at $4M–$6M CAD over an 18-month "
            "delivery window. Time-and-materials pricing is acceptable for "
            "discovery; fixed-price is required for the migration waves."
        ),
        "matches_service_line": "Cloud Migration",
    },
    {
        "customer": "Provincial Health Authority",
        "industry": "Healthcare",
        "region": "Canada",
        "raw_text": (
            "RFP — Clinical Data Lakehouse and BI Modernisation\n\n"
            "The Provincial Health Authority ('PHA') invites proposals to "
            "modernise its analytics estate, consolidating clinical, "
            "operational, and finance data sources into a single "
            "lakehouse architecture with downstream BI and ML "
            "consumption.\n\n"
            "REQUIREMENTS\n"
            "The vendor shall implement a medallion-architected lakehouse "
            "(bronze / silver / gold) using a cloud-native platform.\n"
            "The vendor shall migrate existing Cognos reports to a modern "
            "BI tool with role-based row-level security.\n"
            "The vendor shall integrate at least three source systems "
            "including Meditech (HL7 v2) and Workday Finance.\n"
            "Must hold ISO 27001 certification scoped to data-handling "
            "operations.\n"
            "Must provide SOC 2 Type II evidence.\n"
            "Required: data residency in Canada.\n"
            "Shall maintain GDPR-aligned consent and DSAR procedures for "
            "any patient-identifiable data.\n"
            "Should provide MFA across all administrative access using "
            "FIDO2 hardware tokens.\n"
            "Shall meet 99.9% availability for the consumption tier.\n\n"
            "COMMERCIAL\n"
            "Budget envelope $2.5M CAD over 12 months. Hourly blended "
            "rate cap of CAD 250."
        ),
        "matches_service_line": "Data & Analytics",
    },
    {
        "customer": "Federal Cyber Defence Agency",
        "industry": "Public Sector",
        "region": "EMEA",
        "raw_text": (
            "REQUEST FOR PROPOSAL — Zero-Trust Reference Architecture\n\n"
            "The Federal Cyber Defence Agency is seeking advisory and "
            "delivery partners for the design and implementation of a "
            "zero-trust reference architecture applicable to federal "
            "civilian agencies operating in the EMEA region.\n\n"
            "STATEMENT OF REQUIREMENTS\n"
            "The vendor shall produce a documented zero-trust reference "
            "architecture covering identity, device, network, "
            "application, and data planes.\n"
            "The vendor shall pilot the architecture with two volunteer "
            "agencies of differing scale.\n"
            "Must demonstrate ISO 27001 certification.\n"
            "Must demonstrate SOC 2 Type II — or equivalent national-"
            "scheme attestation.\n"
            "Required: cleared personnel for the engagement leads.\n"
            "Required: delivery presence within the EMEA region.\n"
            "Shall align to NIS2 and DORA where applicable.\n"
            "Shall maintain GDPR data-handling controls for any "
            "engagement artefacts containing personal data.\n"
            "Should provide a defined escalation matrix with response-"
            "time SLAs.\n"
            "Should propose a knowledge-transfer programme for agency "
            "engineers.\n"
        ),
        "matches_service_line": "Cybersecurity Advisory",
    },
]


PAST_PROPOSAL_CLIENTS = [
    "Stellar Bank", "Apex Mutual", "Continental Trust",
    "Northern Wealth", "Sterling Credit", "Granite Bank",
    "MedGrove Health", "Beacon Hospital", "Pinewood Medical",
    "Vista Care", "Riverside Clinics", "Summit Health",
    "Metropolis Transit", "Provincial Records Office", "Civic Data Bureau",
    "Federal Aviation Agency", "Department of Commerce", "Civic Energy Authority",
    "Pinnacle Capital", "Atlantic Insurance", "Coastal Federal Credit",
    "Lakeside Community Health", "Mercy Regional Health", "Sunrise Care Group",
    "Capital District Schools", "Provincial Education Agency", "Regional Tax Office",
    "Coastal Defence Forces", "City of Northport", "Municipal Water Authority",
]


CONTRACT_CLIENTS = [
    ("Stellar Bank", date(2024, 6, 1), date(2027, 5, 31), 4_500_000),
    ("MedGrove Health", date(2024, 9, 15), date(2026, 9, 14), 2_200_000),
    ("Federal Aviation Agency", date(2025, 1, 1), date(2028, 12, 31), 8_750_000),
    ("Provincial Education Agency", date(2024, 3, 1), date(2026, 2, 28), 1_650_000),
    ("Pinnacle Capital", date(2025, 2, 1), date(2027, 1, 31), 3_400_000),
]


async def _ensure(session, sql: str, params: dict):
    """Execute a single statement that uses ON CONFLICT DO NOTHING /
    NOT EXISTS guards. Returns the resulting row mapping if RETURNING was
    used, else None."""
    r = await session.execute(text(sql), params)
    try:
        return r.mappings().first()
    except Exception:
        return None


async def _embedding(text_value: str) -> str:
    """Lazy import the embedder so this script also runs on a host without
    sentence-transformers if all you need is the dimension tables."""
    from common.embedder import SentenceTransformerEmbedder  # type: ignore
    emb = SentenceTransformerEmbedder().embed([text_value])[0]
    return "[" + ",".join(str(v) for v in emb) + "]"


async def seed_capability_profile(session, tenant_id: str) -> dict:
    """3 industries + 3 geographies + 2 certs + 3 service lines (+ M2M)."""
    industry_ids: dict[str, str] = {}
    for name, _slug in INDUSTRIES:
        existing = await session.execute(
            text("SELECT id::text FROM industries WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": name},
        )
        row = existing.first()
        if row:
            industry_ids[name] = row[0]
            continue
        iid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO industries (id, tenant_id, name) VALUES (:i, :t, :n)"),
            {"i": iid, "t": tenant_id, "n": name},
        )
        industry_ids[name] = iid

    geography_ids: dict[str, str] = {}
    for name, typ in GEOGRAPHIES:
        existing = await session.execute(
            text("SELECT id::text FROM geographies WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": name},
        )
        row = existing.first()
        if row:
            geography_ids[name] = row[0]
            continue
        gid = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO geographies (id, tenant_id, name, type) "
                 "VALUES (:i, :t, :n, :ty)"),
            {"i": gid, "t": tenant_id, "n": name, "ty": typ},
        )
        geography_ids[name] = gid

    for name, issuer, scope in CERTIFICATIONS:
        existing = await session.execute(
            text("SELECT id FROM certifications WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": name},
        )
        if existing.first():
            continue
        await session.execute(
            text("INSERT INTO certifications (id, tenant_id, name, issuing_body, scope) "
                 "VALUES (gen_random_uuid(), :t, :n, :ib, :sc)"),
            {"t": tenant_id, "n": name, "ib": issuer, "sc": scope},
        )

    sl_ids: dict[str, str] = {}
    for sl_name, sl_desc, ind_names, geo_names in SERVICE_LINES:
        existing = await session.execute(
            text("SELECT id::text FROM service_lines WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": sl_name},
        )
        row = existing.first()
        if row:
            sl_ids[sl_name] = row[0]
            continue
        sid = str(uuid.uuid4())
        emb = await _embedding(f"{sl_name}: {sl_desc}")
        await session.execute(
            text("INSERT INTO service_lines (id, tenant_id, name, description, embedding) "
                 "VALUES (:i, :t, :n, :d, CAST(:e AS vector))"),
            {"i": sid, "t": tenant_id, "n": sl_name, "d": sl_desc, "e": emb},
        )
        sl_ids[sl_name] = sid
        for ind in ind_names:
            await session.execute(
                text("INSERT INTO service_line_industries (service_line_id, industry_id) "
                     "VALUES (:s, :i) ON CONFLICT DO NOTHING"),
                {"s": sid, "i": industry_ids[ind]},
            )
        for geo in geo_names:
            await session.execute(
                text("INSERT INTO service_line_geographies (service_line_id, geography_id) "
                     "VALUES (:s, :g) ON CONFLICT DO NOTHING"),
                {"s": sid, "g": geography_ids[geo]},
            )

    await session.commit()
    return {"industries": industry_ids, "geographies": geography_ids,
            "service_lines": sl_ids}


async def seed_snippets(session, tenant_id: str) -> None:
    for title, body, tags in SNIPPETS:
        existing = await session.execute(
            text("SELECT id FROM documents WHERE tenant_id = :t AND title = :ti "
                 "AND category = 'boilerplate_snippet'"),
            {"t": tenant_id, "ti": title},
        )
        if existing.first():
            continue
        doc_id = str(uuid.uuid4())
        meta = {"topic_tags": tags, "version": 1, "approved": True}
        await session.execute(
            text("INSERT INTO documents (id, tenant_id, title, category, status) "
                 "VALUES (:i, :t, :ti, 'boilerplate_snippet', 'approved')"),
            {"i": doc_id, "t": tenant_id, "ti": title},
        )
        emb = await _embedding(body)
        await session.execute(
            text("INSERT INTO chunks (id, document_id, text, metadata, embedding) "
                 "VALUES (gen_random_uuid(), :d, :b, CAST(:m AS jsonb), CAST(:e AS vector))"),
            {"d": doc_id, "b": body, "m": json.dumps(meta), "e": emb},
        )
    await session.commit()


async def seed_past_proposals(session, tenant_id: str, industry_ids: dict) -> None:
    # If we already have ≥25 past proposals, skip.
    existing = await session.execute(
        text("SELECT COUNT(*) FROM past_proposals WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    if (existing.scalar() or 0) >= 25:
        return

    industries = list(industry_ids.items())
    today = date.today()
    for i, client in enumerate(PAST_PROPOSAL_CLIENTS):
        ind_name, ind_id = industries[i % len(industries)]
        # Skew toward wins (~70%) for banking/healthcare so the gate flips
        # to "active" with a positive boost in those buckets.
        outcome = random.choices(
            ["won", "lost", "withdrawn"],
            weights=([70, 25, 5] if ind_name != "Public Sector"
                     else [40, 50, 10]),
        )[0]
        submitted = today - timedelta(days=random.randint(60, 720))
        value = random.randint(500_000, 6_000_000)
        body = (
            f"Proposal submitted to {client} for a {ind_name.lower()} "
            f"engagement. Scope included cloud and security workstreams "
            f"with an estimated value of CAD {value:,}. The proposal was "
            f"marked as {outcome}."
        )
        doc_id = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO documents (id, tenant_id, title, category, status) "
                 "VALUES (:i, :t, :ti, 'past_proposal', 'approved')"),
            {"i": doc_id, "t": tenant_id,
             "ti": f"{client} — {ind_name} ({submitted.year})"},
        )
        emb = await _embedding(body)
        meta = {"client_name": client, "outcome": outcome,
                "submitted_at": submitted.isoformat()}
        await session.execute(
            text("INSERT INTO chunks (id, document_id, text, metadata, embedding) "
                 "VALUES (gen_random_uuid(), :d, :b, CAST(:m AS jsonb), CAST(:e AS vector))"),
            {"d": doc_id, "b": body, "m": json.dumps(meta), "e": emb},
        )
        await session.execute(
            text("INSERT INTO past_proposals (id, tenant_id, document_id, "
                 "client_name, industry_id, submitted_at, outcome, "
                 "outcome_reason, value_amount, value_currency) "
                 "VALUES (gen_random_uuid(), :t, :d, :c, :ind, :s, :o, :r, :v, 'CAD')"),
            {"t": tenant_id, "d": doc_id, "c": client, "ind": ind_id,
             "s": submitted, "o": outcome,
             "r": "Lost on price" if outcome == "lost"
                  else "Best value" if outcome == "won"
                  else None,
             "v": value},
        )
    await session.commit()


async def seed_contracts(session, tenant_id: str) -> None:
    existing = await session.execute(
        text("SELECT COUNT(*) FROM contracts WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    if (existing.scalar() or 0) >= len(CONTRACT_CLIENTS):
        return
    for client, eff, exp, value in CONTRACT_CLIENTS:
        existing = await session.execute(
            text("SELECT id FROM contracts WHERE tenant_id = :t AND client_name = :c "
                 "AND effective_date = :e"),
            {"t": tenant_id, "c": client, "e": eff},
        )
        if existing.first():
            continue
        body = (f"Master Services Agreement between Akkodis and {client}. "
                f"Effective {eff:%B %Y}, expiring {exp:%B %Y}. Total value "
                f"CAD {value:,}.")
        doc_id = str(uuid.uuid4())
        await session.execute(
            text("INSERT INTO documents (id, tenant_id, title, category, status) "
                 "VALUES (:i, :t, :ti, 'contract', 'approved')"),
            {"i": doc_id, "t": tenant_id,
             "ti": f"{client} — MSA {eff.year}"},
        )
        emb = await _embedding(body)
        meta = {"client_name": client, "effective_date": eff.isoformat()}
        await session.execute(
            text("INSERT INTO chunks (id, document_id, text, metadata, embedding) "
                 "VALUES (gen_random_uuid(), :d, :b, CAST(:m AS jsonb), CAST(:e AS vector))"),
            {"d": doc_id, "b": body, "m": json.dumps(meta), "e": emb},
        )
        await session.execute(
            text("INSERT INTO contracts (id, tenant_id, document_id, client_name, "
                 "effective_date, expires_at, value_amount, value_currency) "
                 "VALUES (gen_random_uuid(), :t, :d, :c, :ef, :ex, :v, 'CAD')"),
            {"t": tenant_id, "d": doc_id, "c": client, "ef": eff,
             "ex": exp, "v": value},
        )
    await session.commit()


async def seed_demo_rfps(session, tenant_id: str) -> list[str]:
    """Create 3 rich demo RFPs with raw_text + requirements.

    Uses the existing RequirementExtractionAgent so requirements pick up the
    same way they would for a user-uploaded RFP. Returns the list of RFP ids
    that were freshly created (skipped ones are not in the return list)."""
    new_ids: list[str] = []
    # Late import — these modules live in the content-service. When this
    # script runs in the api-gateway container, the content-service code
    # isn't on the path; we'll fall back to a regex-only extraction in
    # _extract_simple() below.
    extract_via_agent = None
    try:
        from agents import RequirementExtractionAgent  # type: ignore
        extract_via_agent = RequirementExtractionAgent()
    except Exception:
        extract_via_agent = None

    for tpl in DEMO_RFP_TEMPLATES:
        existing = await session.execute(
            text("SELECT id::text FROM rfps WHERE tenant_id = :t AND customer = :c"),
            {"t": tenant_id, "c": tpl["customer"]},
        )
        existing_row = existing.first()
        if existing_row:
            rfp_id = existing_row[0]
        else:
            rfp_id = str(uuid.uuid4())
            await session.execute(
                text("INSERT INTO rfps (id, tenant_id, customer, industry, region, "
                     "raw_text, status) VALUES (:i, :t, :c, :ind, :reg, :rt, 'draft')"),
                {"i": rfp_id, "t": tenant_id, "c": tpl["customer"],
                 "ind": tpl["industry"], "reg": tpl["region"], "rt": tpl["raw_text"]},
            )
            new_ids.append(rfp_id)
        # Skip re-extraction if requirements already exist
        existing_reqs = await session.execute(
            text("SELECT COUNT(*) FROM rfp_requirements WHERE rfp_id = :r"),
            {"r": rfp_id},
        )
        if (existing_reqs.scalar() or 0) > 0:
            continue
        # Extract requirements
        reqs = _extract_simple(tpl["raw_text"])
        for r_text, r_cat, mandatory in reqs:
            scoring = {"weight": 1.0, "mandatory": mandatory, "tags": []}
            await session.execute(
                text("INSERT INTO rfp_requirements (id, rfp_id, tenant_id, text, "
                     "category, scoring_criteria, is_questionnaire) "
                     "VALUES (gen_random_uuid(), :r, :t, :tx, :cat, "
                     "CAST(:sc AS jsonb), false)"),
                {"r": rfp_id, "t": tenant_id, "tx": r_text, "cat": r_cat,
                 "sc": json.dumps(scoring)},
            )
    await session.commit()
    return new_ids


def _extract_simple(raw: str) -> list[tuple[str, str, bool]]:
    """Same prefix-driven extraction the content-service agent does. Returns
    (text, category, mandatory) tuples."""
    PREFIXES = {
        "The vendor shall": ("operational", True),
        "The system shall": ("operational", True),
        "Must ": ("operational", True),
        "Required:": ("operational", True),
        "Shall ": ("operational", True),
        "Should ": ("operational", False),
    }
    out: list[tuple[str, str, bool]] = []
    for raw_line in raw.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        for prefix, (cat, mandatory) in PREFIXES.items():
            if line.startswith(prefix):
                out.append((line, cat, mandatory))
                break
    return out


async def main():
    print(f"Connecting to {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        tenant_row = await session.execute(
            text("SELECT id::text FROM tenants ORDER BY created_at LIMIT 1")
        )
        tr = tenant_row.first()
        if not tr:
            raise SystemExit("No tenants seeded yet; run migrations + base seed first.")
        tenant_id = tr[0]
        print(f"Tenant: {tenant_id}")

        print("→ Capability profile…")
        ids = await seed_capability_profile(session, tenant_id)
        print(f"  industries={len(ids['industries'])} "
              f"geographies={len(ids['geographies'])} "
              f"service_lines={len(ids['service_lines'])}")

        print("→ Snippets…")
        await seed_snippets(session, tenant_id)

        print("→ Past proposals (target ≥25 for analytics gate)…")
        await seed_past_proposals(session, tenant_id, ids["industries"])

        print("→ Contracts…")
        await seed_contracts(session, tenant_id)

        print("→ Demo RFPs with requirements…")
        new_rfps = await seed_demo_rfps(session, tenant_id)
        if new_rfps:
            print(f"  created RFP ids: {new_rfps}")
        else:
            print("  (existing demo RFPs already present)")

    await engine.dispose()
    print("✓ Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
