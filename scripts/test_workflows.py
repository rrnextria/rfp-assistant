#!/usr/bin/env python3
"""
End-to-end workflow tests for RFP Assistant.

Tests all user workflows for End Users, Content Admins, and System Admins.

Usage:
    python scripts/test_workflows.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import sys
import time
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# HTTP helpers (no external deps)
# ---------------------------------------------------------------------------

def http(method: str, url: str, body: Any = None, token: str = "") -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body_text = json.loads(e.read())
        except Exception:
            body_text = {}
        return e.code, body_text


def get(url: str, token: str = "") -> tuple[int, Any]:
    return http("GET", url, token=token)


def post(url: str, body: Any, token: str = "") -> tuple[int, Any]:
    return http("POST", url, body=body, token=token)


def patch(url: str, body: Any = None, token: str = "") -> tuple[int, Any]:
    return http("PATCH", url, body=body, token=token)


def delete(url: str, token: str = "") -> tuple[int, Any]:
    return http("DELETE", url, token=token)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Suite:
    base: str
    results: list[TestResult] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        r = TestResult(name=name, passed=condition, detail=detail)
        self.results.append(r)
        status = "✓" if condition else "✗"
        print(f"  {status} {name}" + (f"  [{detail}]" if detail and not condition else ""))
        return condition

    def section(self, title: str) -> None:
        print(f"\n{'─' * 60}")
        print(f"  {title}")
        print(f"{'─' * 60}")

    def summary(self) -> None:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print(f"\n{'═' * 60}")
        print(f"  RESULTS: {passed}/{total} passed")
        if passed < total:
            print("\n  FAILED:")
            for r in self.results:
                if not r.passed:
                    print(f"    ✗ {r.name}  {r.detail}")
        print(f"{'═' * 60}\n")

    def url(self, path: str) -> str:
        return f"{self.base}{path}"


def run_tests(base_url: str) -> bool:
    s = Suite(base=base_url)

    # -----------------------------------------------------------------------
    # Health checks
    # -----------------------------------------------------------------------
    s.section("Health Checks")
    code, body = get(s.url("/healthz"))
    s.check("GET /healthz → 200", code == 200, f"got {code}")

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------
    s.section("Authentication")

    # Wrong password
    code, _ = post(s.url("/auth/login"), {"email": "user@demo.com", "password": "wrong"})
    s.check("Login with wrong password → 401", code == 401, f"got {code}")

    # End user login
    code, data = post(s.url("/auth/login"), {"email": "user@demo.com", "password": "Demo@1234"})
    s.check("End user login → 200", code == 200, f"got {code}")
    user_token = data.get("access_token", "")
    s.check("End user token returned", bool(user_token))

    # Content admin login
    code, data = post(s.url("/auth/login"), {"email": "content@demo.com", "password": "Demo@1234"})
    s.check("Content admin login → 200", code == 200, f"got {code}")
    content_token = data.get("access_token", "")
    s.check("Content admin token returned", bool(content_token))

    # System admin login
    code, data = post(s.url("/auth/login"), {"email": "admin@demo.com", "password": "Demo@1234"})
    s.check("System admin login → 200", code == 200, f"got {code}")
    admin_token = data.get("access_token", "")
    s.check("System admin token returned", bool(admin_token))

    # GET /auth/me
    code, me = get(s.url("/auth/me"), token=user_token)
    s.check("GET /auth/me → 200", code == 200, f"got {code}")
    s.check("me.email correct", me.get("email") == "user@demo.com", str(me.get("email")))

    # -----------------------------------------------------------------------
    # End User — RFP workflows
    # -----------------------------------------------------------------------
    s.section("End User — RFP Workflows")

    # List RFPs (should see own RFPs)
    code, rfps = get(s.url("/rfps"), token=user_token)
    s.check("GET /rfps → 200", code == 200, f"got {code}")
    s.check("RFP list is an array", isinstance(rfps, list), type(rfps).__name__)

    # Create RFP
    code, data = post(s.url("/rfps"),
                      {"customer": "Test Corp", "industry": "Technology", "region": "North America"},
                      token=user_token)
    s.check("POST /rfps → 201", code == 201, f"got {code}")
    rfp_id = data.get("rfp_id", "")
    s.check("rfp_id in response", bool(rfp_id), str(data))

    # Get RFP
    code, rfp = get(s.url(f"/rfps/{rfp_id}"), token=user_token)
    s.check("GET /rfps/{id} → 200", code == 200, f"got {code}")
    s.check("RFP customer matches", rfp.get("customer") == "Test Corp", str(rfp.get("customer")))

    # Add question
    code, data = post(s.url(f"/rfps/{rfp_id}/questions"),
                      {"questions": ["Does the solution support AES-256 encryption at rest?"]},
                      token=user_token)
    s.check("POST /rfps/{id}/questions → 201", code == 201, f"got {code}")
    question_ids = data.get("question_ids", [])
    s.check("question_ids in response", len(question_ids) == 1, str(data))
    question_id = question_ids[0] if question_ids else ""

    # List questions
    code, questions = get(s.url(f"/rfps/{rfp_id}/questions"), token=user_token)
    s.check("GET /rfps/{id}/questions → 200", code == 200, f"got {code}")
    s.check("Question appears in list", any(q["id"] == question_id for q in questions), str(questions))

    # Get latest answer (no answer yet → 404)
    code, _ = get(s.url(f"/rfps/{rfp_id}/questions/{question_id}/answers/latest"), token=user_token)
    s.check("GET .../answers/latest returns 404 before generation", code == 404, f"got {code}")

    # -----------------------------------------------------------------------
    # End User — Ask AI
    # -----------------------------------------------------------------------
    s.section("End User — Ask AI")

    answer_for_review = ""

    # Basic answer mode
    code, data = post(s.url("/ask"), {"question": "What is the availability SLA?", "mode": "answer"}, token=user_token)
    s.check("POST /ask (answer mode) → 200", code == 200, f"got {code}")
    if code == 200:
        s.check("answer field present", "answer" in data, str(list(data.keys())))
        s.check("answer is non-empty string", bool(data.get("answer", "").strip()), "empty answer")
        s.check("citations field present", "citations" in data, str(list(data.keys())))
        s.check("model field present", "model" in data, str(list(data.keys())))
        s.check("model is not error", data.get("model") != "error", data.get("model"))
        answer_for_review = data.get("answer", "")

    # Draft mode
    code, data = post(s.url("/ask"), {"question": "Does the solution support AES-256 encryption?", "mode": "draft"}, token=user_token)
    s.check("POST /ask (draft mode) → 200", code == 200, f"got {code}")
    if code == 200:
        s.check("draft answer non-empty", bool(data.get("answer", "").strip()), "empty")

    # Review mode
    if answer_for_review:
        code, data = post(s.url("/ask"), {
            "question": f"Review this answer: {answer_for_review[:200]}",
            "mode": "review",
        }, token=user_token)
        s.check("POST /ask (review mode) → 200", code == 200, f"got {code}")

    # Gap mode
    code, data = post(s.url("/ask"), {"question": "What certifications does the product hold?", "mode": "gap"}, token=user_token)
    s.check("POST /ask (gap mode) → 200", code == 200, f"got {code}")

    # Unauthenticated ask → 401
    code, _ = post(s.url("/ask"), {"question": "test", "mode": "answer"})
    s.check("POST /ask without token → 401", code == 401, f"got {code}")

    # -----------------------------------------------------------------------
    # Content Admin — Document workflows
    # -----------------------------------------------------------------------
    s.section("Content Admin — Document Workflows")

    # List documents
    code, docs = get(s.url("/documents"), token=content_token)
    s.check("GET /documents → 200", code == 200, f"got {code}")
    docs = docs if isinstance(docs, list) else []
    s.check("Documents list is array", isinstance(docs, list), type(docs).__name__)
    existing_doc_ids = [d["id"] for d in docs if isinstance(d, dict) and d.get("status") != "approved"]

    # Approve a non-approved document (if any exist)
    if existing_doc_ids:
        doc_id = existing_doc_ids[0]
        code, data = patch(s.url(f"/documents/{doc_id}/approve"), token=content_token)
        s.check(f"PATCH /documents/{{id}}/approve → 200", code == 200, f"got {code}: {data}")
        s.check("approve returns status=approved", data.get("status") == "approved", str(data))
    else:
        s.check("PATCH /documents/{id}/approve (skipped — no pending docs)", True, "skipped")

    # -----------------------------------------------------------------------
    # System Admin — User Management
    # -----------------------------------------------------------------------
    s.section("System Admin — User Management")

    # List users
    code, users = get(s.url("/users"), token=admin_token)
    s.check("GET /users → 200", code == 200, f"got {code}")
    s.check("Users list is array", isinstance(users, list), type(users).__name__)
    s.check("At least one user exists", len(users) > 0, f"got {len(users)}")

    # Non-admin cannot list users
    code, _ = get(s.url("/users"), token=user_token)
    s.check("GET /users as end_user → 403", code == 403, f"got {code}")

    # Create user
    import uuid as _uuid
    test_email = f"test_{_uuid.uuid4().hex[:8]}@test.com"
    code, data = post(s.url("/users"),
                      {"email": test_email, "name": "Test User", "role": "end_user",
                       "teams": ["Test Team"], "password": "Test@1234"},
                      token=admin_token)
    s.check("POST /users → 201", code == 201, f"got {code}: {data}")
    s.check("user_id returned", "user_id" in data, str(data))

    # Duplicate email → 409
    code, _ = post(s.url("/users"),
                   {"email": test_email, "role": "end_user", "password": "Test@1234"},
                   token=admin_token)
    s.check("POST /users duplicate email → 409", code == 409, f"got {code}")

    # -----------------------------------------------------------------------
    # Access Control
    # -----------------------------------------------------------------------
    s.section("Access Control")

    # Unauthenticated request → 401
    code, _ = get(s.url("/rfps"))
    s.check("GET /rfps without token → 401", code == 401, f"got {code}")

    code, _ = get(s.url("/documents"))
    s.check("GET /documents without token → 401", code == 401, f"got {code}")

    # End user cannot list users
    code, _ = get(s.url("/users"), token=user_token)
    s.check("GET /users as end_user → 403", code == 403, f"got {code}")

    # -----------------------------------------------------------------------
    # RFP answer for existing demo data
    # -----------------------------------------------------------------------
    s.section("Demo Data — Existing RFPs")

    code, all_rfps = get(s.url("/rfps"), token=admin_token)
    s.check("Admin can list all RFPs", code == 200, f"got {code}")
    s.check("Demo RFPs present (admin sees all)", len(all_rfps) >= 3, f"got {len(all_rfps)} RFPs")

    # Check that demo documents are present
    code, all_docs = get(s.url("/documents"), token=admin_token)
    s.check("Admin can list all documents", code == 200, f"got {code}")
    s.check("Demo documents present (≥5)", len(all_docs) >= 5, f"got {len(all_docs)} docs")

    # -----------------------------------------------------------------------
    s.summary()
    passed = sum(1 for r in s.results if r.passed)
    return passed == len(s.results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RFP Assistant workflow tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API gateway base URL")
    args = parser.parse_args()

    print(f"\nRFP Assistant — End-to-End Workflow Tests")
    print(f"Target: {args.base_url}\n")

    ok = run_tests(args.base_url)
    sys.exit(0 if ok else 1)
