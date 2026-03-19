# RFP AI Assistant — Build-Ready Engineering Specification

## 0. Summary

Model-agnostic RFP assistant that retrieves permission-scoped enterprise content and generates compliant, citation-backed answers via a unified orchestration layer. Supports Copilot, Claude, Gemini, Ollama through adapters.

---

## 1. Architecture (Logical)

**Channel Adapters (Copilot/Web/API)**
→ **API Gateway (Auth, Rate Limit)**
→ **Orchestrator (policy + routing)**
→ **Retrieval Service (hybrid + RBAC filters + rerank)**
→ **Model Router → Model Adapters (Claude/Gemini/Ollama/Copilot)**
→ **Response Assembler (citations, templates)**
→ **Stores (Content, Vector, Structured Facts, Memory, Audit)**

---

## 2. Services & Repos

### 2.1 Services

* `api-gateway`
* `orchestrator`
* `retrieval-service`
* `content-service`
* `rbac-service`
* `rfp-service`
* `model-router`
* `adapters/{claude,gemini,ollama,copilot}`
* `audit-service`

### 2.2 Suggested Tech

* Backend: Node.js (NestJS) or Python (FastAPI)
* DB: Postgres (+ pgvector)
* Queue: Redis / Kafka
* Search: pgvector + BM25 (pg_trgm or Elastic optional)
* Frontend: Next.js + React

---

## 3. Data Model (Postgres)

### 3.1 Users

```
users(id, email, name, role, created_at)
```

### 3.2 Teams

```
teams(id, name)
user_teams(user_id, team_id)
```

### 3.3 Roles

* `end_user`
* `content_admin`
* `system_admin`

### 3.4 Documents

```
documents(id, title, status, created_by, created_at, version)
```

### 3.5 Chunks

```
chunks(id, document_id, text, embedding VECTOR, metadata JSONB)
```

### 3.6 Permissions (on documents/chunks via metadata)

```
metadata: {
  product, region, industry,
  approved: boolean,
  allowed_teams: string[],
  allowed_roles: string[]
}
```

### 3.7 RFPs

```
rfps(id, customer, industry, region, created_by)
rfp_questions(id, rfp_id, question)
rfp_answers(id, question_id, answer, approved, version)
```

### 3.8 Audit

```
audit_logs(id, user_id, action, payload, created_at)
```

---

## 4. Retrieval Pipeline (Deterministic)

1. Normalize query
2. Extract filters (product/industry if provided)
3. Fetch user context (teams, role)
4. Apply **RBAC filter**:

   * `approved = true`
   * `allowed_roles CONTAINS role`
   * `allowed_teams INTERSECT user_teams`
5. Hybrid search:

   * Vector: cosine similarity (top 50)
   * Keyword: BM25 (top 50)
6. Merge + dedupe
7. Rerank (cross-encoder or LLM-lite) → top 8–12
8. Return contexts (with source ids)

---

## 5. Orchestrator Flow (Sequence)

**POST /ask**

1. Auth via gateway
2. Load user + teams
3. Call retrieval-service(query, user_ctx)
4. Build prompt by mode (see §7)
5. model-router.select(tenant, mode)
6. adapter.generate(prompt, context)
7. response-assembler.attach(citations)
8. persist audit + draft
9. return

---

## 6. API Contracts

### 6.1 Ask

```
POST /ask
{
  "question": string,
  "mode": "answer|draft|review|gap",
  "rfp_id": string
}
→
{
  "answer": string,
  "citations": [{chunk_id, doc_id, snippet}]
}
```

### 6.2 Upload Document

```
POST /documents
FormData(file, metadata)
```

### 6.3 Create User

```
POST /users
{ email, role, teams[] }
```

### 6.4 Create RFP

```
POST /rfps
{ customer, industry, region }
```

---

## 7. Prompt Templates (Critical)

### 7.1 System Prompt (All)

```
You are an enterprise RFP assistant. Only answer using provided context. Do not hallucinate. If unsure, say you do not know.
```

### 7.2 Draft Mode

```
Write a formal RFP response using the context. Keep tone professional. Include only supported claims.
```

### 7.3 Review Mode

```
Review the answer. Identify gaps, unsupported claims, and improvements.
```

### 7.4 Gap Mode

```
List missing information required to answer fully.
```

---

## 8. Model Adapter Interface

```
interface ModelAdapter {
  generate(input: {prompt, context}): {text}
  stream(input): Stream
  tool_call?(...)
}
```

### Routing Logic

* tenant config → preferred provider
* fallback provider

---

## 9. Frontend (Next.js)

### Pages

* `/chat`
* `/rfp/[id]`
* `/admin/users`
* `/admin/content`

### Components

* ChatBox
* ModeSelector
* AnswerPane
* CitationsPanel
* RFPQuestionList
* Editor
* AdminTables

---

## 10. Security

* JWT auth
* RBAC enforced pre-retrieval
* No raw DB exposure to model
* Audit every request

---

## 11. Ingestion Pipeline

1. Upload
2. Parse (PDF/DOCX)
3. Chunk by headings (~500 tokens)
4. Embed
5. Store chunk + metadata
6. Mark status (approved required)

---

## 12. Deployment

* Dockerized services
* Kubernetes optional
* Multi-tenant via schema or tenant_id

---

## 13. MVP Checklist

* [ ] Auth + RBAC
* [ ] Content ingestion
* [ ] Hybrid retrieval
* [ ] Model adapters (Claude + Gemini + Ollama)
* [ ] Chat + Draft UI
* [ ] RFP workspace
* [ ] Copilot channel adapter

---

## 14. Future (Post-MVP)

* Graph relationships
* CRM sync
* Auto RFP parsing
* Answer scoring

---

## End Spec
:wq
:wq
