# AI Tutor Monorepo

Portfolio project: do not deploy as-is to production without replacing local demo data, secrets, and runtime settings.

This repository contains the AI Tutor backend and frontend in one workspace.

## Layout

```text
backend/   FastAPI service, database models, RAG/material ingestion, LLM proxy, tests
frontend/  Vite + React application for the tutor workspace and dashboard
docs/      Cross-project notes and migration records
scripts/   Root-level helper scripts for local development and validation
```

## Local Development

Start the backend:

```powershell
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe start.py
```

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Defaults:

- Backend: `http://localhost:8001`
- Frontend: `http://localhost:4173`
- Frontend API base: `VITE_API_BASE_URL`, defaulting to `http://localhost:8001`
- Database: PostgreSQL + pgvector, default `postgresql+psycopg://tutor:tutor@localhost:55432/tutor`
- RAG embeddings use `RAG_EMBEDDING_API_KEY` and `RAG_EMBEDDING_BASE_URL=https://api.openai.com/v1`, independent of chat provider settings.
- Local migrations may create a demo account for development. Replace or disable any seeded demo credentials before exposing a deployment.
- Auth transport: short-lived JWT access tokens in `Authorization: Bearer ...`, plus an HttpOnly refresh cookie scoped to `/api/auth`.

## Validation

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Frontend:

```powershell
cd frontend
npm run type-check
npm run lint
npm run test:run
npm run build
```

Root helper scripts are also available:

```powershell
.\scripts\test.ps1
```

## Notes

The old sibling directories were copied into this monorepo without deleting the originals. Local-only files such as `.env`, virtual environments, `node_modules`, build outputs, SQLite databases, and runtime storage were intentionally excluded.
