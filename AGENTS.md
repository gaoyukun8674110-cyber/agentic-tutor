# Project Operations

## Repository Layout

- Canonical workspace: `H:\ai-tutor`. Treat old sibling folders such as `H:\AI Tutor Backed` and `H:\AI Tutor front end` as historical sources only; do not land new fixes there.
- `backend/` contains the FastAPI service, SQLAlchemy models, Alembic setup, RAG/material services, LLM proxy, eval scaffold, and Python tests.
- `frontend/` contains the Vite + React application, UI components, API client, frontend scripts, and TypeScript configuration.
- `docs/` is for cross-project notes that apply to the whole monorepo.
- `scripts/` is for root-level helper scripts that orchestrate both projects.

## Backend

- Install: `cd backend; pip install -r requirements.txt`
- Migrate: `cd backend; python -m alembic upgrade head`
- Run: `cd backend; python start.py`
- Validate imports: `cd backend; python -m compileall app tests`
- Unit tests: `cd backend; python -m unittest discover -s tests -v`

## Frontend

- Install: `cd frontend; npm install`
- Run: `cd frontend; npm run dev`
- Type check: `cd frontend; npm run type-check`
- Build: `cd frontend; npm run build`
- Lint: `cd frontend; npm run lint`

## Operational Notes

- API keys must stay in backend `.env` files, never in frontend code.
- Browser calls must go through `frontend/src/utils/apiClient.ts`; app auth uses bearer access tokens plus the HttpOnly `/api/auth` refresh cookie, not `X-API-Key`.
- Local/demo migrations may create a development account; production operators must replace or disable any default credentials before exposing a deployment.
- The frontend defaults to `http://localhost:8001`, matching `backend/start.py`; the backend defaults to allowing `http://localhost:4173`.
- Keep backend and frontend API contract changes in the same commit when they depend on each other.
- Do not commit local databases, uploaded materials, virtual environments, dependency directories, or build output.
