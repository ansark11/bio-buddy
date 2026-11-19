# health-rag

Personal health assistant: ingests blood-test PDFs (and reports from Gmail),
extracts biomarkers with Gemini, stores them with embeddings in Supabase
(pgvector), and answers questions over them in a Next.js app. Status and next
phase: `progress.md`; full plan: `health_rag_implementation_plan.md`.

## Commands
- Test (before every commit): `./scripts/test.sh` (about 2 seconds). There are no
  unit tests yet: it checks that the backend compiles and the frontend type-checks.
- Backend: `cd backend && venv/bin/python -m uvicorn app.main:app --reload`
  (http://localhost:8000, API docs at /docs)
- Frontend: `cd frontend && npm run dev` (http://localhost:3000)

## Done means
- `./scripts/test.sh` passes.
- Backend changes: the server starts and the changed endpoint works in /docs.
- Frontend changes: `npm run build` in `frontend/` succeeds.
- `progress.md` reflects what changed, so the next session can resume from it.

## Conventions
- Backend: Python 3.9, FastAPI. Every module starts with
  `from __future__ import annotations` so `X | Y` type hints work on 3.9.
- LLM: `gemini-2.5-flash` via `google-generativeai`. Embeddings:
  `text-embedding-004`, 768 dimensions (`document_chunks.embedding vector(768)`).
- Frontend: Next.js 14 App Router, TypeScript strict, Tailwind, Recharts. The JWT
  from login is kept in localStorage and sent as a Bearer token.

## Gotchas
- `backend/venv` was moved from another folder: `source venv/bin/activate` and
  `pip` still point at the old path. Call `venv/bin/python` directly, and rebuild
  the environment before installing packages.
- The Supabase service role key bypasses row-level security. It stays in the
  backend only, never in frontend code or `NEXT_PUBLIC_*` variables.

## Boundaries
- This repo is public. Real lab reports, extracted results and anything from
  Gmail never get committed; `sample_reports/` is gitignored for that reason.
- Never commit `backend/.env` or `frontend/.env.local`.
- Ask before running the Gmail sync or the scheduler: they read the user's real inbox.
