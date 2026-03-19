"""Portfolio Orchestration agents.

Three agents handle product knowledge indexing, requirement-to-product matching,
and solution recommendation:

- ProductKnowledgeAgent: embeds product description + features into product_embeddings
- PortfolioOrchestrationAgent: finds top-3 matching products per requirement via cosine similarity
- SolutionRecommendationAgent: selects best product per requirement; marks gaps (similarity < 0.5)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common.embedder import SentenceTransformerEmbedder
from common.logging import get_logger

logger = get_logger("portfolio-service.agents")

_embedder = SentenceTransformerEmbedder()

# Gap threshold from D2 / spec
COVERAGE_THRESHOLD = 0.5

# Maximum candidates per requirement to keep scoring fast
TOP_K = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ProductMatch:
    product_id: str
    name: str
    vendor: str | None
    category: str | None
    similarity: float  # 1 - cosine_distance; range [0, 1]


@dataclass
class RequirementCoverage:
    requirement_id: str
    matches: list[ProductMatch] = field(default_factory=list)


@dataclass
class Recommendation:
    requirement_id: str
    product_id: str | None  # None when gap
    similarity: float
    is_gap: bool


# ---------------------------------------------------------------------------
# ProductKnowledgeAgent
# ---------------------------------------------------------------------------

class ProductKnowledgeAgent:
    """Embeds a product's description + serialised features into product_embeddings."""

    async def index_product(self, db: AsyncSession, product_id: str) -> None:
        """Embed the product text and upsert into product_embeddings."""
        row = await db.execute(
            text(
                "SELECT name, description, features FROM products WHERE id = :id"
            ),
            {"id": product_id},
        )
        product = row.mappings().first()
        if product is None:
            raise ValueError(f"Product {product_id} not found")

        # Build a rich text representation for embedding
        parts: list[str] = []
        if product["name"]:
            parts.append(product["name"])
        if product["description"]:
            parts.append(product["description"])
        features = product["features"]
        if isinstance(features, str):
            features = json.loads(features)
        if features:
            # Serialise feature keys and values as flat text
            feature_text = " ".join(
                f"{k}: {v}" for k, v in features.items()
            )
            parts.append(feature_text)

        combined_text = " ".join(parts)
        if not combined_text.strip():
            logger.warning(f"Product {product_id} has no indexable text; skipping")
            return

        [embedding] = _embedder.embed([combined_text])
        vec_str = f"[{','.join(str(v) for v in embedding)}]"

        # Upsert: delete existing then insert
        await db.execute(
            text("DELETE FROM product_embeddings WHERE product_id = :pid"),
            {"pid": product_id},
        )
        await db.execute(
            text(
                "INSERT INTO product_embeddings (product_id, embedding) "
                "VALUES (:pid, :emb::vector)"
            ),
            {"pid": product_id, "emb": vec_str},
        )
        await db.commit()
        logger.info(f"Indexed product {product_id}")


# ---------------------------------------------------------------------------
# PortfolioOrchestrationAgent
# ---------------------------------------------------------------------------

class PortfolioOrchestrationAgent:
    """Finds the top-K matching products for each RFP requirement."""

    async def match(
        self,
        db: AsyncSession,
        requirement_texts: dict[str, str],  # {requirement_id: text}
        tenant_id: str,
        top_k: int = TOP_K,
    ) -> list[RequirementCoverage]:
        """
        For each requirement, run cosine similarity against tenant-scoped
        product embeddings and return up to top_k matches.

        Uses pgvector <=> (cosine distance); similarity = 1 - distance.
        """
        coverages: list[RequirementCoverage] = []

        for req_id, req_text in requirement_texts.items():
            [query_vec] = _embedder.embed([req_text])
            vec_str = f"[{','.join(str(v) for v in query_vec)}]"

            sql = text(
                """
                SELECT
                    p.id::text          AS product_id,
                    p.name              AS name,
                    p.vendor            AS vendor,
                    p.category          AS category,
                    1 - (pe.embedding <=> :vec::vector) AS similarity
                FROM product_embeddings pe
                JOIN products p ON p.id = pe.product_id
                JOIN tenant_products tp ON tp.product_id = p.id
                WHERE tp.tenant_id = :tenant_id::uuid
                ORDER BY similarity DESC
                LIMIT :top_k
                """
            )
            result = await db.execute(
                sql,
                {"vec": vec_str, "tenant_id": tenant_id, "top_k": top_k},
            )
            rows = result.mappings().all()

            matches = [
                ProductMatch(
                    product_id=row["product_id"],
                    name=row["name"],
                    vendor=row["vendor"],
                    category=row["category"],
                    similarity=float(row["similarity"]),
                )
                for row in rows
            ]
            coverages.append(RequirementCoverage(requirement_id=req_id, matches=matches))

        return coverages


# ---------------------------------------------------------------------------
# SolutionRecommendationAgent
# ---------------------------------------------------------------------------

class SolutionRecommendationAgent:
    """Selects the best product per requirement; marks gaps when similarity < threshold."""

    def recommend(
        self,
        coverages: list[RequirementCoverage],
        threshold: float = COVERAGE_THRESHOLD,
    ) -> list[Recommendation]:
        """
        For each RequirementCoverage, pick the top match.
        If the top similarity is below *threshold*, mark as a gap (is_gap=True,
        product_id=None).
        """
        recommendations: list[Recommendation] = []

        for coverage in coverages:
            if not coverage.matches:
                recommendations.append(
                    Recommendation(
                        requirement_id=coverage.requirement_id,
                        product_id=None,
                        similarity=0.0,
                        is_gap=True,
                    )
                )
                continue

            best = coverage.matches[0]  # already sorted DESC by PortfolioOrchestrationAgent
            is_gap = best.similarity < threshold
            recommendations.append(
                Recommendation(
                    requirement_id=coverage.requirement_id,
                    product_id=None if is_gap else best.product_id,
                    similarity=best.similarity,
                    is_gap=is_gap,
                )
            )

        return recommendations
