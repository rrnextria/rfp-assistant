"""Pydantic schemas for the bid-assessment pipeline.

Agents are pure functions over these types; the pipeline owns DB writes.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Citation(BaseModel):
    document_id: UUID
    chunk_id: UUID
    position: int
    excerpt: str | None = None


class ComplianceItem(BaseModel):
    requirement_id: UUID | None = None
    category: Literal["security", "privacy", "operational", "commercial", "legal", "other"]
    label: str
    mandatory: bool
    status: Literal["pass", "fail", "partial", "unknown"]
    evidence: dict
    citations: list[Citation] = []


class EligibilityCheck(BaseModel):
    label: str
    kind: Literal["geography", "contract_vehicle", "certification", "financial",
                   "exclusion", "other"]
    expected: str | None = None
    actual: str | None = None
    status: Literal["pass", "fail", "partial", "unknown"]
    citations: list[Citation] = []


class Risk(BaseModel):
    category: Literal["commercial", "delivery", "legal", "technical", "reputational"]
    title: str
    description: str
    severity: Literal["low", "medium", "high"]
    likelihood: Literal["low", "medium", "high"]
    mitigation: str | None = None
    citations: list[Citation] = []


class CapabilityMatch(BaseModel):
    requirement_id: UUID
    offering_type: Literal["service_line", "product"]
    offering_id: UUID | None = None
    match_score: float
    gap_notes: str | None = None


class AssessmentRollup(BaseModel):
    fit_score: float
    win_probability: float
    verdict: Literal["bid", "no_bid", "review"]
    summary: str
