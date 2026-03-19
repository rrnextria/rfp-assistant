# Phase 7: Copilot Channel Adapter

**Status:** Pending
**Planned Start:** 2026-05-06
**Target End:** 2026-05-12
**Last Updated:** 2026-03-18 by Ravi (Architect)
**File:** `active_plans/rfp_assistant/phases/phase_7_copilot_adapter.md`
**Related:** Master Plan (`active_plans/rfp_assistant/rfp_assistant_master_plan.md`) | Prev: Phase 6 | Next: None

---

## Detailed Objective

This phase delivers the Microsoft Teams / Copilot channel adapter that enables users to ask RFP questions directly within Teams chat. The adapter conforms to the Bot Framework v3 protocol, receives incoming messages, translates them to `POST /ask` calls against the orchestrator (with the user's identity resolved via an MSAL token exchange), and returns formatted adaptive card responses with citations.

This is the final MVP deliverable from spec §13. The adapter is an independent Python FastAPI service (`services/adapters/copilot.py`) deployed behind its own container, registered as a Bot Framework bot in Azure. The channel adapter pattern means the orchestrator is completely unaware of Teams — it only sees authenticated `POST /ask` calls.

Auth in the Teams context is handled by Bot Framework's OAuth card: the bot sends an OAuth card to the user on first interaction; after the user authenticates, the adapter receives a user token and exchanges it for a service JWT to call the orchestrator. User identity is mapped via email (Teams UPN → `users.email`).

Success is defined as: a Teams user can @mention the bot with an RFP question, receive a formatted answer with citations as an adaptive card reply, all within the Teams conversation — with RBAC enforced end-to-end.

---

## Deliverables Snapshot

1. `services/adapters/copilot/main.py` — FastAPI service exposing `POST /api/messages` (Bot Framework webhook endpoint).
2. `services/adapters/copilot/auth.py` — MSAL token validation and user identity resolution (Teams UPN → `users.email` → JWT exchange).
3. `services/adapters/copilot/handler.py` — Conversation turn handler: parse message → call `POST /ask` → format adaptive card response.
4. `services/adapters/copilot/adaptive_card.py` — Adaptive card builder for answer + citations display.
5. Teams app manifest (`manifest.json`) and packaging instructions in `services/adapters/copilot/README.md`.

---

## Acceptance Gates

- [ ] Gate 1: `POST /api/messages` with a valid Bot Framework activity payload (signed by Microsoft) returns HTTP 200 and sends a reply to the Teams channel.
- [ ] Gate 2: A Teams user who is registered in `users` table receives an answer to their question with citations rendered in an adaptive card.
- [ ] Gate 3: A Teams user NOT registered in `users` table receives a friendly "not authorised" adaptive card (no internal error exposed).
- [ ] Gate 4: Bot Framework activity signature validation rejects unsigned/tampered requests with HTTP 401.

---

## Scope

- In Scope:
  1. Bot Framework v3 webhook (`POST /api/messages`) with JWT signature validation.
  2. MSAL token validation for incoming Bot Framework tokens.
  3. User identity mapping (Teams UPN → RFP assistant user → service JWT).
  4. Single-turn Q&A: user sends message → bot replies with answer + citations.
  5. Adaptive card response with answer text and citation list.
  6. Teams app manifest and sideloading instructions.
- Out of Scope:
  1. Multi-turn conversation state / proactive messages (post-MVP).
  2. Copilot Studio integration (post-MVP).
  3. Slack or other channel adapters (post-MVP).
  4. RFP workspace actions within Teams (post-MVP).

---

## Interfaces & Dependencies

- Internal: Phase 4 — `POST /ask` orchestrator endpoint (authenticated with service JWT); Phase 1 — `users.email` lookup.
- External: `botframework-connector` Python SDK (Bot Framework auth); `msal` (MSAL token validation); `httpx` (calls to orchestrator); Azure Bot registration (external service).
- Artifacts: `services/adapters/copilot/` directory; `services/adapters/copilot/manifest.json`.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Azure Bot registration not available in dev | Can't test end-to-end | Use Bot Framework Emulator for local testing; document setup in README |
| MSAL token exchange requires Azure tenant configuration | Auth broken without Azure setup | Provide mock token path controlled by `COPILOT_DEV_MODE=true` env var for integration tests |
| Teams adaptive card schema version mismatch | Card renders blank | Pin adaptive card schema to version 1.5; test with Teams Developer Portal card tester |
| User's Teams UPN does not match `users.email` | Auth fails silently | Log UPN lookup misses as warnings; return clear "not registered" card |

---

## Decision Log

- D1: Python FastAPI for the adapter service (consistent with all other services) — Status: Closed — Date: 2026-03-18
- D2: Service-to-service JWT (not user JWT) for adapter→orchestrator calls — adapter holds a `system_admin` service account JWT — Status: Closed — Date: 2026-03-18
- D3: Adaptive Card v1.5 for answer display — widely supported in Teams without preview features — Status: Closed — Date: 2026-03-18
- D4: Bot Framework Emulator for local dev testing; real Azure bot for staging/prod — Status: Closed — Date: 2026-03-18

---

## References

**Purpose:** Files listed here authorize the reviewer to read them to validate this phase's accuracy and completeness.

### Source Files (existing code/docs being modified)
- `spec.md` — §13 MVP Checklist (Copilot channel adapter), §8 Model Adapter Interface
- `services/orchestrator/routes.py` — `POST /ask` endpoint (Phase 4)

### Destination Files (new files this phase creates)
- `services/adapters/copilot/main.py` — FastAPI app with Bot Framework webhook
- `services/adapters/copilot/auth.py` — MSAL + UPN resolution
- `services/adapters/copilot/handler.py` — Conversation turn handler
- `services/adapters/copilot/adaptive_card.py` — Adaptive card builder
- `services/adapters/copilot/manifest.json` — Teams app manifest
- `services/adapters/copilot/README.md` — Setup and deployment guide
- `tests/test_copilot_adapter.py` — Integration tests with mock Bot Framework activities

### Related Documentation (context only)
- `spec.md` — §13 MVP Checklist
- `active_plans/rfp_assistant/phases/phase_4_orchestrator_models.md` — POST /ask endpoint

---

## Tasks

### [✅] 1 Implement Bot Framework Webhook and Auth Validation
Stand up the adapter service with Bot Framework signature validation.

  - [✅] 1.1 Create `services/adapters/copilot/main.py` FastAPI app with `POST /api/messages` endpoint; implement Bot Framework JWT signature validation using `botframework-connector` (`JwtTokenValidation.validate_auth_header`) — reject unsigned requests with HTTP 401
  - [✅] 1.2 Implement `GET /healthz` for the copilot adapter service; add service to `docker-compose.yml`
  - [✅] 1.3 Write `tests/test_copilot_adapter.py` with a mock Bot Framework activity payload (signed with test key) — assert HTTP 200 returned; assert unsigned payload → HTTP 401

### [✅] 2 Implement User Identity Resolution
Map Teams UPN to the RFP assistant user and obtain a service JWT for orchestrator calls.

  - [✅] 2.1 Implement `resolve_user(upn: str) -> str | None` in `auth.py` — query `users.email = upn`; return `user_id` or `None`
  - [✅] 2.2 Implement `get_service_jwt() -> str` — returns a cached, auto-renewed JWT for the copilot adapter's service account (pre-created `system_admin` user); use `python-jose` to generate and validate
  - [✅] 2.3 Implement `build_user_context_header(user_id) -> dict` — constructs `X-User-Id` header so the orchestrator can log the real user in audit logs (not the service account)

### [✅] 3 Implement Conversation Turn Handler
Parse incoming Teams messages, call the orchestrator, and format the adaptive card reply.

  - [✅] 3.1 Implement `handle_turn(activity: Activity)` in `handler.py` — extract message text from `activity.text`; resolve user via UPN; if not found, send "not registered" card; otherwise call `POST /ask` with `{question: text, mode: "answer"}`
  - [✅] 3.2 Call `POST /ask` via `httpx.AsyncClient` with service JWT and `X-User-Id` header; handle HTTP errors and timeouts (30s); on error send "service unavailable" card
  - [✅] 3.3 Implement `build_answer_card(answer, citations) -> dict` in `adaptive_card.py` — Adaptive Card v1.5 JSON with `TextBlock` for answer, `FactSet` for citations (snippet + doc_id); send card via Bot Framework connector

### [✅] 4 Package and Document the Teams App
Create the Teams app manifest and deployment documentation.

  - [✅] 4.1 Create `manifest.json` with bot ID placeholder, valid `bots` array pointing to the adapter's messaging endpoint, and required permissions (`User.Read`)
  - [✅] 4.2 Write `services/adapters/copilot/README.md` covering: Azure Bot registration, environment variables (`BOT_APP_ID`, `BOT_APP_PASSWORD`, `ORCHESTRATOR_URL`), local testing with Bot Framework Emulator, Teams sideloading steps
  - [✅] 4.3 Write end-to-end integration test using Bot Framework Emulator protocol: simulate a full activity cycle (message in → answer adaptive card out) with mocked orchestrator response


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
