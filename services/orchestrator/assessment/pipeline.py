"""BidAssessmentPipeline — coordinates the 5 agents, writes to DB, emits SSE."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .agents_summary import compute_rollup
from . import stream as sse


def _cit(c) -> dict:
    return {"document_id": str(c.document_id), "chunk_id": str(c.chunk_id),
            "position": c.position, "excerpt": c.excerpt}


class BidAssessmentPipeline:
    """The pipeline owns DB writes. Agents are passed in as async callables
    so tests can stub them without touching network or LLM."""

    def __init__(self, *, compliance_agent, eligibility_agent, bestfit_agent,
                  risk_agent, summary_agent,
                  analytics_boost: float,
                  thresholds: dict,
                  mandatory_penalty: float):
        self._compliance = compliance_agent
        self._eligibility = eligibility_agent
        self._bestfit = bestfit_agent
        self._risk = risk_agent
        self._summary = summary_agent
        self._boost = analytics_boost
        self._thresholds = thresholds
        self._penalty = mandatory_penalty

    async def run(self, *, db: AsyncSession, rfp_id: str,
                   tenant_id: str, user_id: str | None) -> dict:
        version = await self._next_version(db, rfp_id)
        assessment_id = str(uuid4())
        await self._insert_assessment_row(
            db, assessment_id=assessment_id, tenant_id=tenant_id, rfp_id=rfp_id,
            version=version, user_id=user_id)
        await db.commit()

        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "started", "pct": 0,
                  "assessment_id": assessment_id, "version": version})

        # Load requirements + raw text
        req_rows = await db.execute(
            text("SELECT id::text AS id, text, "
                 "(scoring_criteria->>'mandatory')::boolean AS mandatory "
                 "FROM rfp_requirements WHERE rfp_id = :r"),
            {"r": rfp_id})
        requirements = [dict(r) for r in req_rows.mappings().all()]
        raw_row = await db.execute(
            text("SELECT raw_text FROM rfps WHERE id = :r"),
            {"r": rfp_id})
        raw = (raw_row.scalar() or "")

        # Three parallel agents
        compliance_task = asyncio.create_task(
            self._compliance(requirements=requirements, tenant_id=tenant_id))
        elig_task = asyncio.create_task(
            self._eligibility(raw_text=raw, tenant_id=tenant_id))
        bestfit_task = asyncio.create_task(
            self._bestfit(requirements=requirements, tenant_id=tenant_id))

        results = await asyncio.gather(
            compliance_task, elig_task, bestfit_task, return_exceptions=True)
        compliance = results[0] if not isinstance(results[0], Exception) else []
        eligibility = results[1] if not isinstance(results[1], Exception) else []
        best_fit = results[2] if not isinstance(results[2], Exception) else []
        partial = any(isinstance(r, Exception) for r in results)

        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "parallel_done", "pct": 60,
                  "partial": partial})

        await self._persist_children(db, assessment_id, compliance, eligibility,
                                       best_fit, requirements)
        await db.commit()

        # Risk
        try:
            risks = await self._risk(raw_text=raw, requirements=requirements,
                                       compliance=compliance, eligibility=eligibility,
                                       best_fit=best_fit)
        except Exception:
            risks = []
            partial = True
        await self._persist_risks(db, assessment_id, risks)
        await db.commit()
        sse.push(rfp_id, version,
                 {"event": "stage", "stage": "risk_done", "pct": 80})

        # Rollup + summary prose
        rollup = compute_rollup(best_fit, compliance,
                                  thresholds=self._thresholds,
                                  mandatory_penalty=self._penalty,
                                  analytics_boost=self._boost)
        try:
            summary_text = await self._summary(
                rollup=rollup, compliance=compliance,
                eligibility=eligibility, risks=risks)
            verdict = "review" if partial else rollup["verdict"]
            status = "partial" if partial else "complete"
        except Exception:
            summary_text = "Assessment failed during summary."
            verdict = "review"
            status = "failed"

        await db.execute(
            text("UPDATE bid_assessments SET fit_score=:fs, win_probability=:wp, "
                 "verdict=:v, summary=:s, status=:st, completed_at=now() "
                 "WHERE id=:id"),
            {"fs": rollup["fit_score"], "wp": rollup["win_probability"],
             "v": verdict, "s": summary_text, "st": status, "id": assessment_id})
        await db.commit()

        sse.push(rfp_id, version,
                 {"event": "complete", "assessment_id": assessment_id,
                  "verdict": verdict, "status": status,
                  "fit_score": rollup["fit_score"],
                  "win_probability": rollup["win_probability"]})
        sse.close_stream(rfp_id, version)

        return {
            "assessment_id": assessment_id,
            "version": version,
            "status": status,
            "verdict": verdict,  # final, after partial-handling override
            "fit_score": rollup["fit_score"],
            "win_probability": rollup["win_probability"],
            "summary": summary_text,
        }

    async def _next_version(self, db, rfp_id: str) -> int:
        row = await db.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM bid_assessments WHERE rfp_id = :r"),
            {"r": rfp_id})
        return int(row.scalar() or 0) + 1

    async def _insert_assessment_row(self, db, *, assessment_id, tenant_id,
                                       rfp_id, version, user_id):
        await db.execute(
            text("INSERT INTO bid_assessments (id, tenant_id, rfp_id, version, "
                 "status, model_version, generated_by) "
                 "VALUES (:id, :t, :r, :v, 'running', 'orchestrator-v1', :u)"),
            {"id": assessment_id, "t": tenant_id, "r": rfp_id, "v": version,
             "u": user_id})

    async def _persist_children(self, db, assessment_id, compliance, eligibility,
                                  best_fit, requirements):
        for c in compliance:
            await db.execute(
                text("INSERT INTO compliance_items (id, assessment_id, requirement_id, "
                     "category, label, mandatory, status, evidence, citations) "
                     "VALUES (gen_random_uuid(), :a, :rq, :cat, :lbl, :m, :st, "
                     "CAST(:ev AS jsonb), CAST(:ci AS jsonb))"),
                {"a": assessment_id,
                 "rq": str(c.requirement_id) if c.requirement_id else None,
                 "cat": c.category, "lbl": c.label, "m": c.mandatory,
                 "st": c.status,
                 "ev": json.dumps(c.evidence),
                 "ci": json.dumps([_cit(x) for x in c.citations])})
        for e in eligibility:
            await db.execute(
                text("INSERT INTO eligibility_checks (id, assessment_id, label, "
                     "kind, expected, actual, status, citations) "
                     "VALUES (gen_random_uuid(), :a, :lbl, :k, :ex, :ac, :st, "
                     "CAST(:ci AS jsonb))"),
                {"a": assessment_id, "lbl": e.label, "k": e.kind,
                 "ex": e.expected, "ac": e.actual, "st": e.status,
                 "ci": json.dumps([_cit(x) for x in e.citations])})
        for m in best_fit:
            await db.execute(
                text("INSERT INTO capability_matches (id, assessment_id, requirement_id, "
                     "offering_type, offering_id, match_score, gap_notes) "
                     "VALUES (gen_random_uuid(), :a, :rq, :ot, :oi, :sc, :g)"),
                {"a": assessment_id, "rq": str(m.requirement_id),
                 "ot": m.offering_type,
                 "oi": str(m.offering_id) if m.offering_id else None,
                 "sc": m.match_score, "g": m.gap_notes})

    async def _persist_risks(self, db, assessment_id, risks):
        for r in risks:
            await db.execute(
                text("INSERT INTO risks (id, assessment_id, category, title, "
                     "description, severity, likelihood, mitigation, citations, "
                     "authored_by) VALUES (gen_random_uuid(), :a, :cat, :t, :d, "
                     ":sv, :lk, :m, CAST(:ci AS jsonb), 'ai')"),
                {"a": assessment_id, "cat": r.category, "t": r.title,
                 "d": r.description, "sv": r.severity, "lk": r.likelihood,
                 "m": r.mitigation,
                 "ci": json.dumps([_cit(x) for x in r.citations])})
