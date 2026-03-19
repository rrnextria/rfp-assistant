"""Win/Loss Learning Agent.

Responsibilities:
  - Record win/loss outcomes and compute per-product score boosts.
  - Aggregate score boosts across recent records for use in retrieval scoring.

Score boost logic (per spec):
  - Win  → +0.10 for each recommended product
  - Loss → -0.05 for each recommended product
  - Stored as ``score_boosts: {product_id: float}`` in win_loss_records.
  - ``get_score_adjustments`` sums boosts over the last 90 days.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.logging import get_logger

logger = get_logger("analytics-service.win_loss_agent")

_WIN_BOOST: float = 0.10
_LOSS_PENALTY: float = -0.05
_LOOKBACK_DAYS: int = 90


class WinLossLearningAgent:
    """Records outcomes and maintains product-level score boosts."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def learn(
        self,
        db: AsyncSession,
        rfp_id: str,
        outcome: str,
        notes: str = "",
        lessons_learned: str = "",
    ) -> str:
        """Record a win/loss outcome and compute score boosts.

        Joins with portfolio_recommendations (or rfp_answers referencing
        products) to find which products were recommended for this RFP.
        For wins, boosts each product's score by +0.10; for losses, -0.05.
        The resulting ``{product_id: boost}`` map is stored in
        ``win_loss_records.score_boosts``.

        Returns the new win_loss_records row id (UUID string).
        """
        boost_delta = _WIN_BOOST if outcome == "win" else _LOSS_PENALTY

        # Discover recommended products for this RFP.
        # Phase 8 stores recommendations in rfp_portfolio_recommendations;
        # fall back gracefully if that table doesn't exist yet.
        product_ids = await self._recommended_products(db, rfp_id)

        score_boosts: dict[str, float] = {pid: boost_delta for pid in product_ids}
        logger.info(
            "learn rfp=%s outcome=%s products=%d boosts=%s",
            rfp_id,
            outcome,
            len(product_ids),
            score_boosts,
        )

        row = await db.execute(
            text(
                """
                INSERT INTO win_loss_records
                    (rfp_id, outcome, notes, lessons_learned, score_boosts)
                VALUES
                    (:rfp_id, :outcome, :notes, :lessons_learned, :score_boosts::jsonb)
                RETURNING id
                """
            ),
            {
                "rfp_id": rfp_id,
                "outcome": outcome,
                "notes": notes,
                "lessons_learned": lessons_learned,
                "score_boosts": _json_dumps(score_boosts),
            },
        )
        await db.commit()
        record_id = str(row.scalar_one())
        logger.info("win_loss_record created id=%s", record_id)
        return record_id

    async def get_score_adjustments(self, db: AsyncSession) -> dict[str, float]:
        """Return aggregated product score adjustments for the last 90 days.

        Sums all ``score_boosts`` entries across recent win_loss_records.
        The result is a ``{product_id: total_adjustment}`` dict ready to
        pass to ``call_retrieval_service`` / ``reciprocal_rank_fusion``.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_LOOKBACK_DAYS)

        rows = await db.execute(
            text(
                """
                SELECT score_boosts
                FROM win_loss_records
                WHERE created_at >= :cutoff
                  AND score_boosts != '{}'::jsonb
                """
            ),
            {"cutoff": cutoff},
        )

        totals: dict[str, float] = {}
        for (boosts_json,) in rows:
            if not boosts_json:
                continue
            boosts: dict[str, float] = boosts_json if isinstance(boosts_json, dict) else {}
            for pid, delta in boosts.items():
                totals[pid] = totals.get(pid, 0.0) + delta

        logger.debug("score_adjustments aggregated products=%d", len(totals))
        return totals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _recommended_products(
        self, db: AsyncSession, rfp_id: str
    ) -> list[str]:
        """Return product IDs recommended for *rfp_id*.

        Tries ``rfp_portfolio_recommendations`` first (Phase 8); if the
        table doesn't exist, returns an empty list gracefully.
        """
        try:
            rows = await db.execute(
                text(
                    """
                    SELECT DISTINCT product_id::text
                    FROM rfp_portfolio_recommendations
                    WHERE rfp_id = :rfp_id
                    """
                ),
                {"rfp_id": rfp_id},
            )
            return [r[0] for r in rows]
        except Exception as exc:
            logger.warning(
                "Could not query rfp_portfolio_recommendations (Phase 8 not deployed?): %s",
                exc,
            )
            await db.rollback()
            return []


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

win_loss_agent = WinLossLearningAgent()


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def _json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj)
