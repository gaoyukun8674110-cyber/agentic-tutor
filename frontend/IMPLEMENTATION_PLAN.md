# AI Tutor Frontend Master Plan

## Purpose
This is the only active frontend planning file.
All frontend spec, theme-plan, and progress documents have been consolidated into this file.

## Current Status
- Status: frontend multi-user auth UX and authenticated API transport are implemented.
- Active frontend backlog from the archived planning set: add richer end-to-end UI coverage once the project adopts a first-class frontend E2E runner.

## Frontend Responsibilities
- Own dashboard and Tutor workspace UX.
- Consume backend APIs through shared frontend API clients.
- Own login, registration, route guarding, access-token memory state, refresh retry, and logout UX.
- Maintain routed application structure, persisted settings, and shared Pomodoro state.
- Render Tutor messages safely, including Markdown and math notation.

## Consolidated Delivery Scope

### 1. Tutor Workspace Foundations
- Added a route-based app shell with dedicated dashboard and Tutor pages.
- Moved Tutor profiles, history, and materials loading onto stable query keys and domain hooks.
- Reduced `TutorChatWorkspace` to a thinner composition layer over domain hooks and shared state.
- Unified Pomodoro ownership across dashboard and Tutor so timer state persists through route changes and reloads.

### 2. Math Rendering
- Added Markdown plus KaTeX rendering for Tutor chat messages.
- Normalized common inline and block LaTeX delimiters.
- Preserved readable chat layout for both math content and Chinese text.
- Completed the KaTeX-safe sanitization pass so allowed math markup survives while unsafe HTML is stripped.

### 3. P1 and P2 Audit Remediation
- Added a shared `apiClient` for base URL handling, API-key transport, parsing, uploads, and abort support.
- Added React Query caching and invalidation for dashboard and Tutor data.
- Changed Tutor failures from fake assistant messages to visible UI error states.
- Persisted language and theme settings.
- Added API error classification, debounce support for history search, and cleanup of placeholder or dead UI behaviors.

### 4. Theme-System Consolidation
- Moved light and dark theme values into CSS variables.
- Expanded semantic theme tokens for surfaces, text, status, actions, charts, and chat bubbles.
- Added reusable glass-style helpers for panels, inputs, actions, and Tutor chat surfaces.
- Migrated dashboard and Tutor hardcoded colors to tokens while keeping intentional dynamic exceptions centralized.

### 5. Additional Frontend Delivery
- Added month navigation and viewed-month state control to `StudyCalendar`.
- Eliminated router future warnings and oversized bundle warnings through lazy routes and targeted chunking.
- Fixed the Select menu opacity regression after theme refactoring.

### 6. Multi-User Authentication UX
- Added `/login` and `/register` pages plus `AuthProvider` and `ProtectedRoute`.
- Replaced shared `X-API-Key` requests with bearer access tokens, `credentials: include`, single-flight refresh, and one-time request replay after 401.
- Removed hardcoded `local` user usage from dashboard, Tutor, task, and Pomodoro calls.
- Updated the top navigation to show the authenticated user and expose logout.
- Added API client regression tests for auth localization, cookie transport, refresh retry, and concurrent refresh deduplication.

## Validation Baseline
- Frontend run: `npm run dev`
- Frontend type check: `npm run type-check`
- Frontend lint: `npm run lint`
- Frontend unit tests: `npm run test:run`
- Frontend build: `npm run build`
- Archived validation also covered targeted regression scripts for:
  - math rendering,
  - Pomodoro persistence,
  - P0/P1/P2 audit fixes,
  - Tutor and dashboard UI regressions tied to recent remediation work.

## Remaining Frontend Follow-Up
- Add richer end-to-end UI coverage when a first-class frontend E2E runner is established.

## Consolidated Sources
The following frontend planning documents were consolidated into this file and then removed to avoid duplicate planning inputs:
- `frontend/PROGRESS.md`
- `frontend/specs/math-rendering.md`
- `frontend/specs/p1-audit-remediation.md`
- `frontend/docs/superpowers/specs/2026-05-07-t8-theme-system-design.md`
- `frontend/docs/superpowers/plans/2026-05-07-t8-theme-system.md`
