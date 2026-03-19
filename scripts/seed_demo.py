#!/usr/bin/env python3
"""
Demo data seed script for RFP Assistant.

Creates a demo organization (Nextria — an enterprise IT solutions company)
with accounts you can log in with and test:

  system_admin  — admin@demo.com       / Demo@1234
  content_admin — content@demo.com     / Demo@1234
  end_user      — user@demo.com        / Demo@1234

Also seeds:
  - 3 teams: Engineering, Sales, Pre-Sales
  - 5 products: Cloud Storage Suite, SecureEdge Platform,
                CloudID (IAM), DevFlow Platform, AI Insights Engine
  - 10 documents with realistic sales / technical content
    (security briefs, compliance sheets, data sheets, integration guides)
  - 3 RFPs covering Financial Services, Healthcare, and Government sectors
  - Questions and draft answers for each RFP

Run after migrations:
    python scripts/seed_demo.py
    # or inside Docker:
    docker compose exec api-gateway python /app/../scripts/seed_demo.py
"""

import asyncio
import json
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
    {"name": "Pre-Sales"},
]

USERS = [
    {
        "email": "admin@demo.com",
        "role": "system_admin",
        "password": "Demo@1234",
        "teams": ["Engineering", "Sales", "Pre-Sales"],
    },
    {
        "email": "content@demo.com",
        "role": "content_admin",
        "password": "Demo@1234",
        "teams": ["Engineering", "Pre-Sales"],
    },
    {
        "email": "user@demo.com",
        "role": "end_user",
        "password": "Demo@1234",
        "teams": ["Sales", "Pre-Sales"],
    },
]

# ---------------------------------------------------------------------------
# Products — Nextria IT Solutions portfolio
# ---------------------------------------------------------------------------

PRODUCTS = [
    {
        "name": "Cloud Storage Suite",
        "vendor": "Nextria",
        "category": "Cloud Infrastructure",
        "description": (
            "Enterprise-grade cloud object storage with AES-256 encryption at rest, "
            "TLS 1.3 in transit, SOC 2 Type II certified, and 99.999% durability SLA. "
            "Supports versioning, lifecycle policies, cross-region replication, and "
            "an S3-compatible API."
        ),
        "features": {
            "encryption_at_rest": "AES-256",
            "encryption_in_transit": "TLS 1.3",
            "certification": "SOC 2 Type II",
            "durability_sla": "99.999%",
            "availability_sla": "99.9%",
            "api_compatibility": "S3-compatible",
            "versioning": True,
            "cross_region_replication": True,
            "immutable_audit_logs": True,
            "gdpr_compliant": True,
            "data_residency": ["EU", "US", "APAC"],
        },
    },
    {
        "name": "SecureEdge Platform",
        "vendor": "Nextria",
        "category": "Cybersecurity",
        "description": (
            "Unified endpoint detection and response (EDR) with AI-driven threat "
            "intelligence, zero-trust network access (ZTNA), and a built-in SIEM. "
            "FIPS 140-2 validated, FedRAMP Moderate authorized, and ISO 27001 certified. "
            "Provides continuous compliance posture monitoring and automated incident response."
        ),
        "features": {
            "edr": True,
            "ztna": True,
            "siem_included": True,
            "threat_intelligence": "AI-driven",
            "fips_140_2": True,
            "fedramp": "Moderate",
            "iso_27001": True,
            "soc_2_type_ii": True,
            "mfa_enforcement": True,
            "automated_incident_response": True,
            "deployment": ["cloud", "on-premise", "hybrid"],
            "mttr_minutes": 12,
        },
    },
    {
        "name": "CloudID",
        "vendor": "Nextria",
        "category": "Identity & Access Management",
        "description": (
            "Cloud-native identity and access management platform supporting SAML 2.0, "
            "OAuth 2.0, OpenID Connect, and SCIM provisioning. Provides adaptive MFA, "
            "privileged access management (PAM), single sign-on (SSO) across 3,000+ "
            "pre-built integrations, and a self-service identity governance portal."
        ),
        "features": {
            "sso": True,
            "mfa": "adaptive",
            "saml_2_0": True,
            "oauth_2_0": True,
            "oidc": True,
            "scim_provisioning": True,
            "pam": True,
            "integrations": 3000,
            "self_service_portal": True,
            "soc_2_type_ii": True,
            "uptime_sla": "99.99%",
            "passwordless": True,
        },
    },
    {
        "name": "DevFlow Platform",
        "vendor": "Nextria",
        "category": "DevOps & CI/CD",
        "description": (
            "End-to-end DevSecOps platform integrating source control, CI/CD pipelines, "
            "container registry, secret scanning, SAST/DAST tooling, and Kubernetes "
            "orchestration. Supports multi-cloud deployments across AWS, Azure, and GCP. "
            "SOC 2 Type II certified with built-in audit trails for every pipeline run."
        ),
        "features": {
            "ci_cd": True,
            "container_registry": True,
            "secret_scanning": True,
            "sast": True,
            "dast": True,
            "kubernetes_support": True,
            "multi_cloud": ["AWS", "Azure", "GCP"],
            "soc_2_type_ii": True,
            "audit_trails": True,
            "sbom_generation": True,
            "deployment_frequency": "unlimited",
        },
    },
    {
        "name": "AI Insights Engine",
        "vendor": "Nextria",
        "category": "Analytics & AI",
        "description": (
            "Enterprise AI analytics platform for structured and unstructured data. "
            "Provides natural-language querying (NLQ), predictive modelling, anomaly "
            "detection, and automated reporting dashboards. Supports data residency in "
            "EU, US, and APAC. SOC 2 Type II and ISO 27001 certified. On-premise and "
            "private-cloud deployment options available for regulated industries."
        ),
        "features": {
            "nlq": True,
            "predictive_modelling": True,
            "anomaly_detection": True,
            "automated_reporting": True,
            "data_residency": ["EU", "US", "APAC"],
            "soc_2_type_ii": True,
            "iso_27001": True,
            "deployment": ["cloud", "on-premise", "private-cloud"],
            "llm_integration": True,
            "role_based_data_access": True,
            "hipaa_ready": True,
        },
    },
]

# ---------------------------------------------------------------------------
# Documents with realistic sales / technical content
# ---------------------------------------------------------------------------

DOCUMENTS = [
    # ── Cloud Storage Suite ─────────────────────────────────────────────────
    {
        "title": "Cloud Storage Suite — Product Brief",
        "product": "Cloud Storage Suite",
        "chunks": [
            {
                "heading": "Security Overview",
                "text": (
                    "Cloud Storage Suite encrypts all data at rest using AES-256 and "
                    "all data in transit using TLS 1.3. All data centres are SOC 2 "
                    "Type II certified and undergo annual third-party penetration testing. "
                    "Immutable audit logs capture every object operation, preventing "
                    "tampering and supporting forensic investigations."
                ),
            },
            {
                "heading": "Durability and Availability",
                "text": (
                    "The platform delivers 99.999% data durability through erasure "
                    "coding across a minimum of three availability zones. An availability "
                    "SLA of 99.9% is backed by financial service credits. Cross-region "
                    "replication is configurable with RPO of less than 15 minutes."
                ),
            },
            {
                "heading": "Compliance and Data Residency",
                "text": (
                    "Cloud Storage Suite is GDPR-compliant and supports data residency "
                    "requirements in the EU, US, and APAC regions. Customers can pin "
                    "buckets to specific geographic regions, ensuring data never leaves "
                    "a defined boundary. HIPAA Business Associate Agreements (BAA) are "
                    "available for healthcare customers."
                ),
            },
            {
                "heading": "S3-Compatible API and SDKs",
                "text": (
                    "The S3-compatible REST API allows drop-in replacement of Amazon S3 "
                    "with no client code changes. SDKs are available for Python, Java, "
                    "Go, .NET, and Node.js. Lifecycle policies automate tiering to cold "
                    "storage after configurable retention periods."
                ),
            },
        ],
    },
    {
        "title": "Cloud Storage Suite — Compliance & Certifications Sheet",
        "product": "Cloud Storage Suite",
        "chunks": [
            {
                "heading": "SOC 2 Type II",
                "text": (
                    "Nextria Cloud Storage Suite holds a current SOC 2 Type II report "
                    "covering the Security, Availability, and Confidentiality trust "
                    "service criteria. The report is produced by an independent CPA firm "
                    "and covers a 12-month observation period. Copies are available under "
                    "NDA upon request."
                ),
            },
            {
                "heading": "GDPR Compliance",
                "text": (
                    "Cloud Storage Suite is fully GDPR-compliant. Nextria acts as a "
                    "data processor and provides a Data Processing Agreement (DPA). "
                    "Data subject access requests (DSARs) can be fulfilled within 30 "
                    "days. Data deletion requests result in cryptographic erasure within "
                    "72 hours across all replicas."
                ),
            },
            {
                "heading": "HIPAA Readiness",
                "text": (
                    "Cloud Storage Suite supports HIPAA requirements for ePHI storage. "
                    "Nextria signs Business Associate Agreements (BAA) with covered "
                    "entities and business associates. Access to ePHI buckets is "
                    "restricted via IAM policies with mandatory MFA enforcement and "
                    "full audit logging."
                ),
            },
            {
                "heading": "ISO/IEC 27001",
                "text": (
                    "Nextria's cloud infrastructure is ISO/IEC 27001:2022 certified, "
                    "covering the information security management system (ISMS) for "
                    "all cloud services including Cloud Storage Suite. Certificates "
                    "are available upon request."
                ),
            },
        ],
    },
    # ── SecureEdge Platform ─────────────────────────────────────────────────
    {
        "title": "SecureEdge Platform — Sales Data Sheet",
        "product": "SecureEdge Platform",
        "chunks": [
            {
                "heading": "Endpoint Detection and Response (EDR)",
                "text": (
                    "SecureEdge's EDR module monitors every endpoint process, file, "
                    "network connection, and registry change in real time. AI-driven "
                    "threat intelligence correlates indicators of compromise (IoCs) "
                    "across the global Nextria threat graph — updated every 5 minutes. "
                    "Mean time to detect (MTTD) averages 4 minutes; mean time to "
                    "respond (MTTR) averages 12 minutes."
                ),
            },
            {
                "heading": "Zero-Trust Network Access (ZTNA)",
                "text": (
                    "SecureEdge enforces a zero-trust architecture where every access "
                    "request is authenticated, authorised, and continuously verified — "
                    "regardless of network location. Micro-segmentation policies are "
                    "defined by identity, device posture, and application, replacing "
                    "legacy VPN with identity-aware proxying."
                ),
            },
            {
                "heading": "SIEM and Automated Incident Response",
                "text": (
                    "The built-in SIEM aggregates logs from endpoints, cloud services, "
                    "network devices, and SaaS applications. Machine-learning baselines "
                    "surface anomalies with contextual alerts. Playbooks automate "
                    "containment, evidence collection, and escalation — reducing "
                    "analyst alert fatigue by up to 70%."
                ),
            },
            {
                "heading": "Regulatory Compliance",
                "text": (
                    "SecureEdge is FedRAMP Moderate authorized, FIPS 140-2 validated, "
                    "SOC 2 Type II certified, and ISO 27001 certified. Pre-built "
                    "compliance dashboards map control status to NIST 800-53, CIS "
                    "Controls v8, PCI-DSS 4.0, and HIPAA. Evidence packages are "
                    "exportable for auditors."
                ),
            },
        ],
    },
    {
        "title": "SecureEdge Platform — Government & Public Sector Brief",
        "product": "SecureEdge Platform",
        "chunks": [
            {
                "heading": "FedRAMP Authorization",
                "text": (
                    "SecureEdge Platform holds a FedRAMP Moderate Authorization to "
                    "Operate (ATO) issued by a U.S. Federal agency acting as sponsor. "
                    "The Authority to Operate covers all cloud-hosted SecureEdge "
                    "components. FedRAMP High authorization is in progress, expected "
                    "Q3 2026."
                ),
            },
            {
                "heading": "FIPS 140-2 Validation",
                "text": (
                    "All cryptographic modules within SecureEdge are validated under "
                    "FIPS 140-2 at Security Level 2. This covers TLS termination, "
                    "key storage, and data-at-rest encryption — meeting the requirements "
                    "of Executive Order 14028 and NIST SP 800-171."
                ),
            },
            {
                "heading": "On-Premise Deployment for Air-Gapped Environments",
                "text": (
                    "SecureEdge can be fully deployed on-premise in air-gapped "
                    "environments with no dependency on external connectivity. "
                    "Threat intelligence feeds are updated via signed offline packages. "
                    "Suitable for classified networks (up to IL4 with additional controls)."
                ),
            },
        ],
    },
    # ── CloudID ─────────────────────────────────────────────────────────────
    {
        "title": "CloudID — Identity & Access Management Overview",
        "product": "CloudID",
        "chunks": [
            {
                "heading": "Single Sign-On and Federation",
                "text": (
                    "CloudID provides SSO across 3,000+ pre-built application connectors "
                    "using SAML 2.0 and OpenID Connect. Custom connectors can be built "
                    "using the OIDC/OAuth 2.0 integration wizard in under 30 minutes. "
                    "Federation with on-premise Active Directory and LDAP is supported "
                    "via a lightweight gateway agent."
                ),
            },
            {
                "heading": "Adaptive Multi-Factor Authentication",
                "text": (
                    "CloudID's adaptive MFA engine evaluates risk signals — device "
                    "posture, location, behaviour pattern, and time-of-day — to "
                    "step up authentication only when warranted. Supported factors "
                    "include TOTP, hardware security keys (FIDO2/WebAuthn), push "
                    "notifications, and biometrics via passkeys."
                ),
            },
            {
                "heading": "Privileged Access Management",
                "text": (
                    "The PAM module provides just-in-time (JIT) privileged access, "
                    "session recording, credential vaulting, and break-glass emergency "
                    "access with mandatory approval workflows. All privileged sessions "
                    "are recorded and indexed for search — supporting audit requirements "
                    "under SOX, PCI-DSS, and HIPAA."
                ),
            },
            {
                "heading": "SCIM Provisioning and Governance",
                "text": (
                    "Automated user lifecycle management via SCIM 2.0 ensures users "
                    "are provisioned and deprovisioned across connected applications "
                    "within minutes of HR system changes. Access certification campaigns "
                    "can be scheduled quarterly or triggered on role change, with "
                    "automated revocation of unreviewed access."
                ),
            },
        ],
    },
    # ── DevFlow Platform ────────────────────────────────────────────────────
    {
        "title": "DevFlow Platform — DevSecOps Capabilities Brief",
        "product": "DevFlow Platform",
        "chunks": [
            {
                "heading": "CI/CD Pipeline and Multi-Cloud Deployment",
                "text": (
                    "DevFlow provides unlimited CI/CD pipeline execution across AWS, "
                    "Azure, and GCP. Declarative pipeline-as-code (YAML) supports "
                    "parallel jobs, matrix builds, and dependency caching. Deployment "
                    "targets include Kubernetes, ECS, Azure App Service, Cloud Run, "
                    "and bare-metal servers via SSH."
                ),
            },
            {
                "heading": "Security Scanning and SBOM",
                "text": (
                    "Every pipeline run automatically executes secret scanning (pre-commit "
                    "and CI), SAST with 30+ language analysers, container image scanning "
                    "via integrated vulnerability database, and DAST against staging "
                    "environments. A Software Bill of Materials (SBOM) in CycloneDX or "
                    "SPDX format is generated for every build artifact."
                ),
            },
            {
                "heading": "Audit Trails and Compliance",
                "text": (
                    "DevFlow captures a tamper-evident audit trail for every pipeline "
                    "event: code commit, pipeline trigger, approval gate, deployment, "
                    "and rollback. Trails are exportable for SOC 2, FedRAMP, and PCI-DSS "
                    "evidence packages. Change advisory board (CAB) integration enforces "
                    "approval gates before production deployments."
                ),
            },
        ],
    },
    # ── AI Insights Engine ──────────────────────────────────────────────────
    {
        "title": "AI Insights Engine — Product Overview",
        "product": "AI Insights Engine",
        "chunks": [
            {
                "heading": "Natural Language Querying",
                "text": (
                    "AI Insights Engine lets business users query enterprise data in "
                    "plain English. The NLQ layer translates questions into SQL, "
                    "Spark, or API calls against connected data sources — returning "
                    "results as tables, charts, or narrative summaries. No SQL knowledge "
                    "is required."
                ),
            },
            {
                "heading": "Predictive Modelling and Anomaly Detection",
                "text": (
                    "Pre-built ML models for churn prediction, revenue forecasting, "
                    "inventory optimisation, and fraud detection can be deployed with "
                    "a single click. AutoML training pipelines retrain models on a "
                    "configurable schedule. Anomaly detection runs continuously and "
                    "surfaces statistical outliers with root-cause explanations."
                ),
            },
            {
                "heading": "Data Governance and Role-Based Access",
                "text": (
                    "All data access is governed by role-based policies synced from "
                    "the customer's identity provider via SCIM. Column-level and "
                    "row-level security ensure analysts only see data their role permits. "
                    "Data lineage is tracked end-to-end, supporting GDPR data mapping "
                    "and audit requirements."
                ),
            },
            {
                "heading": "Deployment and Data Residency",
                "text": (
                    "AI Insights Engine supports cloud (multi-tenant SaaS), private "
                    "cloud (dedicated VPC), and on-premise deployments. Data residency "
                    "is enforced in EU, US, and APAC regions. For regulated industries "
                    "(healthcare, finance, government), private-cloud and on-premise "
                    "options ensure data never leaves the customer's environment."
                ),
            },
        ],
    },
    {
        "title": "AI Insights Engine — Healthcare & Life Sciences Brief",
        "product": "AI Insights Engine",
        "chunks": [
            {
                "heading": "HIPAA Compliance",
                "text": (
                    "AI Insights Engine is HIPAA-ready for processing and analysing "
                    "electronic Protected Health Information (ePHI). Nextria signs "
                    "Business Associate Agreements (BAA) with covered entities and "
                    "business associates. PHI is never used for model training without "
                    "explicit written consent."
                ),
            },
            {
                "heading": "Clinical Data Integration",
                "text": (
                    "Pre-built connectors integrate with Epic, Cerner, HL7 FHIR R4, "
                    "and DICOM endpoints. Predictive models are available for patient "
                    "readmission risk, length-of-stay forecasting, and claims anomaly "
                    "detection. All model outputs include confidence intervals and "
                    "uncertainty quantification."
                ),
            },
            {
                "heading": "Audit Logging for Healthcare",
                "text": (
                    "Every query, report, and data export is logged to an immutable "
                    "audit trail with user identity, timestamp, data accessed, and "
                    "purpose. Audit logs are retained for 7 years by default and are "
                    "searchable for HIPAA audit readiness."
                ),
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# RFPs with questions and draft answers
# ---------------------------------------------------------------------------

RFPS = [
    {
        "customer": "Acme Financial Services",
        "industry": "Financial Services",
        "region": "North America",
        "raw_text": (
            "Acme Financial Services is seeking an enterprise cloud storage and "
            "identity management solution to support its digital transformation. "
            "Requirements include SOC 2 Type II certification, GDPR compliance, "
            "99.9%+ availability, strong encryption, and SSO integration."
        ),
        "questions": [
            {
                "q": "Does the solution support AES-256 encryption at rest and TLS 1.3 in transit?",
                "draft": (
                    "Yes. Cloud Storage Suite encrypts all data at rest using AES-256 "
                    "and all data in transit using TLS 1.3. These are non-configurable "
                    "defaults applied to all tenants — there is no lower encryption mode. "
                    "Key management is handled by Nextria's KMS with customer-managed "
                    "key (CMK) support via AWS KMS, Azure Key Vault, or GCP Cloud KMS."
                ),
            },
            {
                "q": "Is the solution SOC 2 Type II certified?",
                "draft": (
                    "Yes. Nextria Cloud Storage Suite holds a current SOC 2 Type II "
                    "report covering Security, Availability, and Confidentiality trust "
                    "service criteria. The report is produced annually by an independent "
                    "CPA firm and covers a 12-month observation period. Copies are "
                    "available under NDA upon request."
                ),
            },
            {
                "q": "What durability and availability SLAs does the solution provide?",
                "draft": (
                    "Cloud Storage Suite guarantees 99.999% data durability through "
                    "erasure coding across a minimum of three availability zones. "
                    "Availability is backed by a 99.9% SLA with financial service "
                    "credits for any breach. Cross-region replication provides an RPO "
                    "of under 15 minutes for disaster recovery."
                ),
            },
            {
                "q": "Does the solution support SSO and MFA for user access?",
                "draft": (
                    "Yes. CloudID, our IAM platform, provides SSO via SAML 2.0 and "
                    "OpenID Connect with 3,000+ pre-built connectors. Adaptive MFA "
                    "supports TOTP, FIDO2 hardware keys, and passkeys. CloudID "
                    "integrates directly with Cloud Storage Suite for unified identity "
                    "governance across storage access."
                ),
            },
            {
                "q": "How does the solution handle GDPR data subject rights requests?",
                "draft": (
                    "Cloud Storage Suite is fully GDPR-compliant. Nextria acts as a "
                    "data processor and provides a signed Data Processing Agreement "
                    "(DPA). Data subject access requests (DSARs) are fulfilled within "
                    "30 days. Deletion requests result in cryptographic erasure across "
                    "all replicas within 72 hours."
                ),
            },
        ],
    },
    {
        "customer": "MedGroup Healthcare Network",
        "industry": "Healthcare",
        "region": "North America",
        "raw_text": (
            "MedGroup Healthcare Network requires a HIPAA-compliant analytics and "
            "endpoint security platform to support clinical operations and protect "
            "patient data. Requirements include ePHI handling, HIPAA BAA availability, "
            "EDR, MFA enforcement, and audit logging."
        ),
        "questions": [
            {
                "q": "Is the solution HIPAA-compliant and will you sign a Business Associate Agreement?",
                "draft": (
                    "Yes. Both AI Insights Engine and SecureEdge Platform are HIPAA-ready "
                    "for processing and storing electronic Protected Health Information "
                    "(ePHI). Nextria signs Business Associate Agreements (BAA) as standard "
                    "for all healthcare customers. PHI is never used for model training "
                    "without explicit written consent."
                ),
            },
            {
                "q": "What endpoint detection and response capabilities does the solution provide?",
                "draft": (
                    "SecureEdge Platform provides full EDR coverage across Windows, macOS, "
                    "and Linux endpoints. The AI-driven threat intelligence engine updates "
                    "every 5 minutes from the global Nextria threat graph. Mean time to "
                    "detect (MTTD) averages 4 minutes; mean time to respond (MTTR) averages "
                    "12 minutes. Automated containment isolates compromised endpoints "
                    "without human intervention."
                ),
            },
            {
                "q": "How is MFA enforced for clinical staff accessing patient data?",
                "draft": (
                    "CloudID's adaptive MFA enforces step-up authentication for all access "
                    "to ePHI systems. Risk signals — device posture, location, and "
                    "behavioural pattern — determine when MFA is required. Clinical staff "
                    "can use TOTP apps, FIDO2 security keys, or passkeys. MFA bypass "
                    "policies are restricted to system administrators with dual approval."
                ),
            },
            {
                "q": "What audit logging is provided for HIPAA compliance?",
                "draft": (
                    "All Nextria products produce immutable audit logs for every user "
                    "action: login events, data access, query execution, report export, "
                    "and administrative changes. Logs are retained for 7 years by default "
                    "and are searchable. AI Insights Engine logs include the specific data "
                    "fields accessed, enabling precise HIPAA audit readiness reporting."
                ),
            },
        ],
    },
    {
        "customer": "State Department of Digital Services",
        "industry": "Government",
        "region": "North America",
        "raw_text": (
            "The State Department of Digital Services is issuing an RFP for a "
            "unified cybersecurity and DevSecOps platform. Requirements include "
            "FedRAMP Moderate or higher authorization, FIPS 140-2 validation, "
            "zero-trust architecture, SBOM generation, and on-premise deployment "
            "capability for classified workloads."
        ),
        "questions": [
            {
                "q": "Is the solution FedRAMP authorized and at what impact level?",
                "draft": (
                    "Yes. SecureEdge Platform holds a FedRAMP Moderate Authorization to "
                    "Operate (ATO) issued by a U.S. Federal agency sponsor. FedRAMP High "
                    "authorization is in progress, with expected authorization in Q3 2026. "
                    "DevFlow Platform's FedRAMP Moderate package is available in the FedRAMP "
                    "Marketplace under Nextria's CSP entry."
                ),
            },
            {
                "q": "Are cryptographic modules FIPS 140-2 validated?",
                "draft": (
                    "Yes. All cryptographic modules across SecureEdge and DevFlow are "
                    "validated under FIPS 140-2 at Security Level 2. This covers TLS "
                    "termination, key storage, and data-at-rest encryption — meeting "
                    "requirements under Executive Order 14028 and NIST SP 800-171. "
                    "FIPS validation certificates are available upon request."
                ),
            },
            {
                "q": "Does the security platform support zero-trust network access?",
                "draft": (
                    "Yes. SecureEdge Platform implements a full zero-trust architecture "
                    "aligned with NIST SP 800-207. Every access request is authenticated, "
                    "authorised via least-privilege policies, and continuously verified "
                    "regardless of network location. Identity-aware proxying replaces "
                    "legacy VPN with micro-segmentation enforced at the application level."
                ),
            },
            {
                "q": "Does the CI/CD platform generate Software Bills of Materials (SBOM)?",
                "draft": (
                    "Yes. DevFlow Platform automatically generates a Software Bill of "
                    "Materials (SBOM) in CycloneDX or SPDX format for every build "
                    "artifact. SBOMs are signed, stored in the artifact registry, and "
                    "can be exported for supply-chain risk analysis — meeting Executive "
                    "Order 14028 and CISA SBOM requirements."
                ),
            },
            {
                "q": "Can the platform be deployed on-premise in air-gapped environments?",
                "draft": (
                    "Yes. SecureEdge Platform and DevFlow Platform both support fully "
                    "on-premise deployment with no dependency on external internet "
                    "connectivity. Threat intelligence feeds and vulnerability databases "
                    "are updated via signed offline packages delivered on a configurable "
                    "schedule. Both platforms have been deployed in IL4-equivalent "
                    "environments."
                ),
            },
        ],
    },
]


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

        # ── Products ───────────────────────────────────────────────────────
        product_ids: dict[str, str] = {}
        for p in PRODUCTS:
            row = await db.execute(
                text(
                    "INSERT INTO products (name, vendor, category, description, features) "
                    "VALUES (:name, :vendor, :category, :desc, :features) "
                    "ON CONFLICT DO NOTHING RETURNING id"
                ),
                {
                    "name": p["name"],
                    "vendor": p["vendor"],
                    "category": p["category"],
                    "desc": p["description"],
                    "features": json.dumps(p["features"]),
                },
            )
            product_id = row.scalar()
            if product_id is None:
                r = await db.execute(
                    text("SELECT id FROM products WHERE name = :name"),
                    {"name": p["name"]},
                )
                product_id = r.scalar()
            product_ids[p["name"]] = str(product_id)
        print(f"  ✓ Products: {list(product_ids.keys())}")

        # ── Documents + chunks ─────────────────────────────────────────────
        admin_id = user_ids["admin@demo.com"]
        eng_team_id = team_ids["Engineering"]
        sales_team_id = team_ids["Sales"]
        presales_team_id = team_ids["Pre-Sales"]

        total_chunks = 0
        for doc in DOCUMENTS:
            doc_meta_base = {
                "product": doc["product"],
                "approved": True,
                "allowed_roles": ["system_admin", "content_admin", "end_user"],
                "allowed_teams": [],  # empty = accessible to all authenticated users
            }

            row = await db.execute(
                text(
                    "INSERT INTO documents (title, status, created_by) "
                    "VALUES (:title, 'ready', :uid) "
                    "ON CONFLICT DO NOTHING RETURNING id"
                ),
                {"title": doc["title"], "uid": admin_id},
            )
            doc_id = row.scalar()
            if doc_id is None:
                r = await db.execute(
                    text("SELECT id FROM documents WHERE title = :t"),
                    {"t": doc["title"]},
                )
                doc_id = r.scalar()

            for chunk in doc["chunks"]:
                chunk_meta = {**doc_meta_base, "heading": chunk["heading"]}
                await db.execute(
                    text(
                        "INSERT INTO chunks (document_id, text, metadata) "
                        "VALUES (:did, :text, :meta) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "did": doc_id,
                        "text": chunk["text"],
                        "meta": json.dumps(chunk_meta),
                    },
                )
                total_chunks += 1

        print(f"  ✓ Documents: {len(DOCUMENTS)} documents, {total_chunks} chunks")

        # ── RFPs + questions + draft answers ───────────────────────────────
        for rfp_def in RFPS:
            row = await db.execute(
                text(
                    "INSERT INTO rfps (customer, industry, region, raw_text, created_by) "
                    "VALUES (:customer, :industry, :region, :raw, :uid) "
                    "ON CONFLICT DO NOTHING RETURNING id"
                ),
                {
                    "customer": rfp_def["customer"],
                    "industry": rfp_def["industry"],
                    "region": rfp_def["region"],
                    "raw": rfp_def["raw_text"],
                    "uid": admin_id,
                },
            )
            rfp_id = row.scalar()
            if rfp_id is None:
                r = await db.execute(
                    text("SELECT id FROM rfps WHERE customer = :c"),
                    {"c": rfp_def["customer"]},
                )
                rfp_id = r.scalar()

            for item in rfp_def["questions"]:
                row = await db.execute(
                    text(
                        "INSERT INTO rfp_questions (rfp_id, question) "
                        "VALUES (:rfp_id, :q) ON CONFLICT DO NOTHING RETURNING id"
                    ),
                    {"rfp_id": rfp_id, "q": item["q"]},
                )
                qid = row.scalar()
                if qid is None:
                    r = await db.execute(
                        text("SELECT id FROM rfp_questions WHERE rfp_id=:r AND question=:q"),
                        {"r": rfp_id, "q": item["q"]},
                    )
                    qid = r.scalar()

                if item.get("draft"):
                    await db.execute(
                        text(
                            "INSERT INTO rfp_answers "
                            "(question_id, answer, version, approved, detail_level) "
                            "VALUES (:qid, :ans, 1, false, 'balanced') "
                            "ON CONFLICT DO NOTHING"
                        ),
                        {"qid": qid, "ans": item["draft"]},
                    )

            q_count = len(rfp_def["questions"])
            print(
                f"  ✓ RFP '{rfp_def['customer']}' ({rfp_def['industry']}) "
                f"— {q_count} questions + {q_count} draft answers"
            )

        await db.commit()

    await engine.dispose()

    print("\nDemo data seeded successfully!")
    print("\nLogin credentials:")
    print("  system_admin  → admin@demo.com    / Demo@1234")
    print("  content_admin → content@demo.com  / Demo@1234")
    print("  end_user      → user@demo.com     / Demo@1234")
    print("\nProducts seeded:")
    for p in PRODUCTS:
        print(f"  · {p['name']} ({p['category']})")
    print("\nDocuments seeded:")
    for d in DOCUMENTS:
        print(f"  · {d['title']}")
    print("\nRFPs seeded:")
    for r in RFPS:
        print(f"  · {r['customer']} — {r['industry']}")
    print("\nAPI: http://localhost:8000")
    print("UI:  http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(seed())
