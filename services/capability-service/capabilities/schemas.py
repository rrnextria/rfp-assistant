"""Pydantic schemas for capability profile endpoints."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# --- service_lines ---

class ServiceLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    parent_id: str | None = None
    industry_ids: list[str] = Field(default_factory=list)
    geography_ids: list[str] = Field(default_factory=list)


class ServiceLineOut(BaseModel):
    id: str
    name: str
    description: str | None
    parent_id: str | None
    industry_ids: list[str]
    geography_ids: list[str]


# --- industries ---

class IndustryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class IndustryOut(BaseModel):
    id: str
    name: str


# --- geographies ---

class GeographyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["country", "region", "city"]
    parent_id: str | None = None


class GeographyOut(BaseModel):
    id: str
    name: str
    type: str
    parent_id: str | None


# --- certifications ---

class CertificationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuing_body: str | None = None
    scope: str | None = None
    expires_at: date | None = None
    evidence_doc_id: str | None = None


class CertificationOut(BaseModel):
    id: str
    name: str
    issuing_body: str | None
    scope: str | None
    expires_at: date | None
    evidence_doc_id: str | None
