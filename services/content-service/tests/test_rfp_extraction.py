from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/content-service")


def test_requirement_extraction():
    from agents import RequirementExtractionAgent

    rfp_text = """
TECHNICAL REQUIREMENTS
The vendor shall provide 24/7 support.
The system shall support SSO authentication.
Must provide SLA of 99.9% uptime.

SECURITY
The vendor shall implement AES-256 encryption.
Should provide audit logging capabilities.
"""
    agent = RequirementExtractionAgent()
    requirements = agent.extract(rfp_text)
    assert len(requirements) >= 3
    categories = {r.category for r in requirements}
    assert len(categories) >= 1


def test_questionnaire_extraction():
    from agents import QuestionnaireExtractionAgent

    rfp_text = """
Does your solution support SSO? (yes/no)
How many concurrent users can your system support?
Can your solution integrate with Salesforce?
What is your uptime SLA?
"""
    agent = QuestionnaireExtractionAgent()
    items = agent.extract(rfp_text)
    assert len(items) >= 2
    types = {i.question_type for i in items}
    assert "yes_no" in types or "numeric" in types or "text" in types
