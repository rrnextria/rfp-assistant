# Phase 8: Portfolio Orchestration

**Status:** Pending
**Planned Start:** 2026-05-13
**Target End:** 2026-05-21
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_8_portfolio_orchestration.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 7 | Next: Phase 9

---

## Detailed Objective

This phase implements the full portfolio orchestration capability from spec_additional §2.2 and §3: the Product Knowledge Agent, Portfolio Orchestration Agent, and Solution Recommendation Agent. Together they allow the system to evaluate a VAR's complete product and services catalog against RFP requirements, and recommend single or multi-vendor solutions with a unified architecture narrative.

The product catalog is stored in the `products` and `tenant_products` tables created in Phase 1 (Task 5). The Product Knowledge Agent retrieves relevant products for a given set of requirements using the same retrieval pipeline as Phase 3, but operating on the product knowledge base rather than document chunks. The Portfolio Orchestration Agent scores each product against each requirement and identifies coverage gaps. The Solution Recommendation Agent synthesizes scored matches into a complete solution architecture — potentially combining multiple vendors.

Domain isolation is enforced: each tenant's portfolio is scoped to their `tenant_products` assignments; no cross-tenant product data leaks regardless of how requirements are structured.

Success is defined as: given an RFP with extracted requirements, the system can produce a recommended solution architecture identifying which products cover which requirements, flagging gaps, and providing a narrative explanation with confidence scores.

---

## Deliverables Snapshot

1. `POST /admin/products` and `GET /products` endpoints for managing the product catalog (system_admin only for write).
2. `services/adapters/product_knowledge_agent.py` — retrieves relevant products for a given requirement using pgvector similarity on product descriptions/features.
3. `services/orchestrator/portfolio_agent.py` — scores each product against each extracted RFP requirement; produces a coverage matrix.
4. `services/orchestrator/solution_recommender.py` — selects optimal single/multi-vendor combination minimizing gaps; produces solution architecture JSON with narrative.
5. `POST /rfps/{id}/recommend-solution` endpoint returning solution architecture with per-requirement coverage and an overall confidence score.

---

## Acceptance Gates

- [ ] Gate 1: `POST /admin/products` creates a product record; `GET /products` returns the tenant's assigned products; a product with `features JSONB` is searchable by the Product Knowledge Agent.
- [ ] Gate 2: Given 5 extracted RFP requirements and a catalog of 10 products, `POST /rfps/{id}/recommend-solution` returns a coverage matrix mapping each requirement to one or more products.
- [ ] Gate 3: Requirements with no matching product in the catalog are returned in a `coverage_gaps` list in the response.
- [ ] Gate 4: Domain isolation enforced: tenant A's product recommendations do not include tenant B's `tenant_products` entries, verified by integration test.

---

## Scope

- In Scope:
  1. Product catalog CRUD (`products`, `tenant_products`).
  2. Product Knowledge Agent: vector search on product descriptions + feature JSONB matching.
  3. Portfolio Orchestration Agent: requirement-to-product scoring matrix.
  4. Solution Recommendation Agent: optimal combination selection and narrative generation.
  5. `POST /rfps/{id}/recommend-solution` endpoint with coverage matrix and gap list.
  6. Domain isolation per tenant.
- Out of Scope:
  1. Automatic product catalog import from vendor portals (post-MVP).
  2. Real-time pricing/availability data (post-MVP).
  3. Multi-level BOM (bill of materials) nesting (post-MVP).
  4. Frontend solution recommendation UI (Phase 6 follow-up; add to /rfp/[id] page post-MVP).

---

## Interfaces & Dependencies

- Internal: Phase 1 (Task 5) — `products`, `tenant_products` tables. Phase 3 — retrieval service and `EmbedderInterface`. Phase 4 — `AgentPipeline`, `AgentInput/Output` schemas. Phase 5 — `rfp_requirements` table.
- External: No new external dependencies — reuses existing SQLAlchemy, pgvector, and FastAPI stack.
- Artifacts: `services/content-service/product_routes.py`; `services/orchestrator/portfolio_agent.py`; `services/orchestrator/solution_recommender.py`; `tests/test_portfolio.py`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Product catalog is empty at demo time | No recommendations generated | Seed script `scripts/seed_products.py` with sample VAR catalog for dev/demo |
| Product feature JSONB schema varies by vendor | Agent can't normalize | Define canonical feature schema in `common/product_schema.py`; validate on import |
| Combinatorial explosion for large catalogs (100+ products × 50+ requirements) | Slow recommendation | Cap Product Knowledge Agent to top 20 products per requirement; apply timeout 60s |
| Domain isolation breach via SQL injection in feature JSONB | Cross-tenant data leak | Use parameterized queries only; validated by adversarial integration test |

---

## Decision Log

- D1: Product embeddings stored as separate `product_embeddings(product_id, embedding VECTOR)` table rather than on `products` — allows re-embedding on model change without touching product records — Status: Closed — Date: 2026-03-18
- D2: Portfolio Orchestration Agent scores as cosine similarity (0.0–1.0); threshold 0.5 = "covers requirement" — Status: Closed — Date: 2026-03-18
- D3: Solution narrative generated by the Response Generation Agent (Phase 4) with a specialized prompt, not a separate LLM call — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec_additional.md` — §2.2 Full Portfolio Orchestration, §3 System Architecture, §5 Agent Definitions
- `migrations/versions/0005_portfolio_schema.py` — `products`, `tenant_products` tables (Phase 1 Task 5)
- `services/retrieval-service/vector_search.py` — Reused for product knowledge retrieval (Phase 3)
- `services/orchestrator/pipeline.py` — `AgentPipeline` (Phase 4 Task 5)

### Destination Files (new files this phase creates)
- `services/content-service/product_routes.py` — Product catalog CRUD
- `services/orchestrator/portfolio_agent.py` — Coverage matrix scorer
- `services/orchestrator/solution_recommender.py` — Solution selection and narrative
- `tests/test_portfolio.py` — Coverage matrix and domain isolation tests

### Related Documentation (context only)
- `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md` — AgentPipeline
- `active_plans/rfp_assistant/phases/phase_5_rfp_service.md` — rfp_requirements source
- `spec_additional.md` — Full Keystone spec

---

## Tasks

### [✅] 1 Implement Product Catalog Management
Build the product catalog CRUD and embed product descriptions for semantic retrieval.

  - [✅] 1.1 Implement `POST /admin/products` (system_admin) — accept `{name, vendor, category, description, features: JSONB}`; insert `products` row; generate and store embedding in `product_embeddings(product_id, embedding VECTOR(384))`
  - [✅] 1.2 Implement `POST /admin/tenants/{id}/products` — assign a product to a tenant via `tenant_products`; implement `GET /products` — return tenant-scoped product list
  - [✅] 1.3 Write `tests/test_product_catalog.py` — assert product created with embedding; assert tenant scoping (tenant A cannot see tenant B's products)

### [✅] 2 Implement Product Knowledge Agent
Retrieve relevant products for a set of extracted requirements using semantic search on the product catalog.

  - [✅] 2.1 Implement `ProductKnowledgeAgent.retrieve(requirements: list[Requirement], tenant_id) -> dict[requirement_id, list[Product]]` — for each requirement, run vector search on `product_embeddings` filtered by `tenant_products.tenant_id`; return top 5 products per requirement
  - [✅] 2.2 Implement feature matching: supplement vector similarity with exact JSONB key overlap between `requirement.scoring_criteria` and `product.features`; combine scores 70% vector + 30% feature overlap
  - [✅] 2.3 Write `tests/test_product_knowledge_agent.py` — seed 10 products and 3 requirements; assert each requirement maps to at least 1 product; assert tenant isolation

### [✅] 3 Implement Portfolio Orchestration Agent
Score the full product catalog against all RFP requirements and build a coverage matrix.

  - [✅] 3.1 Implement `PortfolioOrchestrationAgent.score(requirements, tenant_products) -> CoverageMatrix` — for each requirement, assign the best-matching product and a coverage score (0.0–1.0); requirement with coverage < 0.5 is marked as a gap in `coverage_gaps: list[requirement_id]`
  - [✅] 3.2 Implement multi-vendor combination: if no single product covers a requirement, check if two products together exceed 0.5 threshold (feature union); flag as `multi_vendor=true`
  - [✅] 3.3 Write `tests/test_portfolio_agent.py` — assert requirements covered by product A are not in `coverage_gaps`; assert uncoverable requirements are in `coverage_gaps`

### [✅] 4 Implement Solution Recommendation Agent and Endpoint
Synthesize the coverage matrix into a complete solution architecture with narrative.

  - [✅] 4.1 Implement `SolutionRecommendationAgent.recommend(coverage_matrix) -> SolutionArchitecture` — select the minimal set of products that maximizes requirement coverage; generate a solution architecture JSON `{products: [{product_id, role, covers_requirements: [ids]}], gaps: [ids], confidence: float}`
  - [✅] 4.2 Generate solution narrative by calling `ResponseGenerationAgent` with a specialized portfolio prompt: summarize chosen products, explain coverage of key requirements, list gaps; attach narrative to `SolutionArchitecture.narrative`
  - [✅] 4.3 Implement `POST /rfps/{id}/recommend-solution` — run `ProductKnowledgeAgent` → `PortfolioOrchestrationAgent` → `SolutionRecommendationAgent` pipeline; return full `SolutionArchitecture` with per-requirement coverage and narrative
  - [✅] 4.4 Write `tests/test_solution_recommender.py` — assert returned architecture covers maximum requirements; assert `coverage_gaps` present; assert narrative non-empty

---

## Completion Step (Required)
After the reviewer approves a task, `plan-sync` automatically updates checkmarks. Do NOT manually edit checkmarks.

To verify plan structure is correct:
- Run `./how_to/maistro plan-verify <this-phase-file> --no-cross-file` before requesting review. Do not proceed until zero errors.
- Use `./how_to/maistro plan-reconcile rfp_assistant` if checkmarks appear stale.

## Reviewer Checklist

### Structure & Numbering

- [ ] All top-level tasks use `### [ ] N` format.
- [ ] All sub-tasks use `- [ ] N.1` format.
- [ ] Optional deeper tasks use `- [ ] N.1.1` and never headings.
- [ ] No numbering deeper than `1.1.1`.
- [ ] No skipped numbers.

### Traceability

- [ ] All tasks reflect Detailed Objective and Scope.
- [ ] Task titles match what will appear in the master plan.
- [ ] No invented tasks.

### Consistency

- [ ] Section ordering follows the template.
- [ ] All metadata fields are present in the Header.
- [ ] Deliverables Snapshot, Acceptance Gates, and Scope refer to real tasks.

### References

- [ ] Source, Destination, and Related Documentation sections appear.
