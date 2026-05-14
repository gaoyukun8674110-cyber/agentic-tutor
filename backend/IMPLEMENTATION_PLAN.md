# AI Tutor Backend Master Plan

## Purpose
This is the only active backend planning file.
All backend spec and progress documents have been consolidated into this file.

## Current Status
- Status: multi-user authentication and backend data isolation are implemented.
- Mandatory backend backlog from the archived planning set: none.
- Verification baseline now includes local `compileall` and the full backend `unittest` suite.

## Backend Responsibilities
- Own provider configuration, prompt profiles, and LLM API calls.
- Persist Tutor conversation history, summaries, and context handoff.
- Ingest study materials, generate embeddings, and serve filtered retrieval.
- Expose public error contracts, auth boundaries, and baseline security headers.
- Own user registration, login, access-token validation, refresh-token rotation, logout, and per-user data isolation.

## Consolidated Delivery Scope

### 1. Tutor Chat Platform
- Added provider configuration, safe provider metadata, prompt-profile metadata, and OpenAI-compatible chat orchestration.
- Exposed `GET /api/llm/providers`, `GET /api/llm/prompt-profiles`, and `POST /api/llm/chat`.
- Moved `LLMService` to an application-scoped lifecycle and added provider-client reuse guards.
- Added sanitized API error responses and trace IDs for public-facing failures.

### 2. Conversation History and Context Control
- Added persistent Tutor conversation and message storage.
- Added conversation list, detail, and delete APIs under `/api/llm/conversations`.
- Extended chat requests and responses to support `conversation_id`.
- Implemented a context-window policy:
  - 0-10 exchanges: normal conversation.
  - 10-15 exchanges: frontend warning threshold.
  - 15+ exchanges: backend summary generation and compact context mode.
- Persisted Tutor summaries and compacted later model calls to summary plus recent exchanges plus current input.

### 3. Three-Stage Learning Method
- Added the `three_stage` Tutor profile as the default learning strategy.
- Added backend phase detection for planning, understanding, Feynman check, and general support.
- Returned `learning_phase` metadata from chat responses.
- Preserved learning-state details inside long-conversation summaries so later sessions keep useful educational context.

### 4. Materials, Upload Safety, and Retrieval
- Added upload size and file-signature validation before unbounded reads.
- Changed material ingestion to create pending records first and fill embeddings asynchronously.
- Exposed `embedding_mode` in material payloads and retrieval responses.
- Added baseline FastAPI security headers.
- Replaced recent-record RAG candidate scanning with a persistent VP-tree vector index.
- Preserved user scoping and `material_ids` filtering on indexed retrieval.

### 5. Validation Baseline
- Backend run: `python start.py`
- Backend migrations: `python -m alembic upgrade head`
- Backend tests: `python -m unittest discover -s tests -v`
- Backend import validation: `python -m compileall app tests`
- Focused regression suites from the archived work covered:
  - provider metadata and Tutor chat behavior,
  - conversation persistence and compact context,
  - auth, CORS, upload validation, and public error schema,
  - indexed material retrieval and provider-client reuse.

### 6. Multi-User Authentication and Isolation
- Added `app/auth/`, `app/api/auth.py`, `User`, and `RefreshToken`.
- Replaced `X-API-Key` app authentication with JWT bearer access tokens and HttpOnly refresh cookies.
- Updated dashboard, Tutor history, materials, training, and student APIs to scope reads and writes to `current_user.username`.
- Added Alembic migrations for `users`, `refresh_tokens`, legacy data backfill to `test-01`, non-null user ownership on migrated tables, and a final verification revision for the demo user and legacy ownership.
- Added auth and isolation regression coverage, including cross-user dashboard, student, Tutor conversation, and material scoping tests.

## Remaining Backend Follow-Up
- No mandatory backend implementation item remains open from the archived planning set.
- Run `ruff` and `mypy` before the next production hardening pass if typing/style gates are required by CI.

## Consolidated Sources
The following backend planning documents were consolidated into this file and then removed to avoid duplicate planning inputs:
- `backend/PROGRESS.md`
- `backend/specs/ai-tutor-chat.md`
- `backend/specs/tutor-conversation-history.md`
- `backend/specs/tutor-context-window.md`
- `backend/specs/three-stage-learning.md`
- `backend/specs/p1-audit-remediation.md`
