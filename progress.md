# Health RAG — Project Progress

> Feed this file to Claude at the start of a new session to resume where we left off.

---

## Current Status: Phases 1–5 Complete

All core functionality is implemented and working. The next phase is **Phase 6: Polish & Auto-Sync** from `health_rag_implementation_plan.md`.

---

## How to Run

**Backend:**
```bash
cd health-rag/backend
source venv/bin/activate
uvicorn app.main:app --reload
# Runs on http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

**Frontend:**
```bash
cd health-rag/frontend
npm run dev
# Runs on http://localhost:3000
```

**Auth flow:** Login at `http://localhost:3000` → get JWT → stored in localStorage → used as Bearer token for all API calls.

---

## Architecture Summary

- **Backend:** Python 3.9, FastAPI, `from __future__ import annotations` in all files for type union compatibility
- **Database:** Supabase (PostgreSQL + pgvector), service role key used server-side to bypass RLS
- **LLM:** `gemini-2.5-flash` via `google-generativeai`
- **Embeddings:** `text-embedding-004` (768 dimensions) → stored in `document_chunks.embedding vector(768)`
- **Frontend:** Next.js 14 App Router, TypeScript strict, Tailwind CSS, Recharts
- **Scheduler:** APScheduler AsyncIOScheduler — daily Gmail check at 09:00 if `SCHEDULED_USER_ID` is set

---

## What's Built (Phase by Phase)

### Phase 1 — Blood Test PDF Ingestion ✅

- `backend/app/services/pdf_parser.py` — Extracts biomarkers from blood test PDFs via Gemini structured JSON extraction, generates human-readable panel summaries for embedding (not raw PDF text)
- `backend/app/services/embeddings.py` — `generate_embedding()` and `embed_and_store_chunks()`; embeds summary chunks into `document_chunks`
- `backend/app/routers/ingest.py` — `POST /api/ingest/blood-test`, `GET /api/ingest/documents`
- `backend/app/routers/auth.py` — `POST /api/auth/signup`, `POST /api/auth/login`
- `backend/app/dependencies.py` — `get_current_user` JWT dependency

### Phase 2 — Apple Health + Manual Tracking ✅

- `backend/app/services/apple_health.py` — Streaming XML parser (`iterparse`) for Apple Health export ZIP. Handles: weight, resting HR, HRV, steps, active calories, exercise minutes, dietary calories, sleep stages (aggregated per night, 6 PM–12 PM window)
- `backend/app/routers/ingest.py` — `POST /api/ingest/apple-health`
- `backend/app/routers/metrics.py` — `POST /api/metrics/log`, `POST /api/metrics/log/supplement`, `GET /api/metrics`, `GET /api/metrics/latest`
- Frontend: `/upload` page with Apple Health + blood test upload sections; `/log` page with daily logging form

### Phase 3 — Nutrition (Lose It) ✅

- `backend/app/services/nutrition_parser.py` — Parses Lose It **daily macro summary CSV** (not per-meal). Columns: `Date (MM/DD/YYYY), Calories, Fat (g), Protein (g), Carbohydrates (g), Saturated Fat (g), Sugars (g), Fiber (g), Cholesterol (mg), Sodium (mg)`. Produces 9 metric rows per day + 1 RAG text chunk per day.
- `backend/app/services/gmail_watcher.py` — OAuth2 Gmail integration; `check_for_nutrition_emails()` searches for Lose It attachment emails, downloads CSV, parses, stores
- `backend/app/routers/ingest.py` — Added: `POST /api/ingest/nutrition`, `GET /api/ingest/nutrition/gmail-init`, `GET /api/ingest/nutrition/gmail-callback?code=...`, `POST /api/ingest/nutrition/check-email`
- `backend/app/main.py` — Converted to FastAPI lifespan pattern with APScheduler
- Frontend `/upload` — Added "Upload Nutrition Data" section
- **Key decisions:**
  - Lose It export is daily aggregates, NOT per-meal. `nutrition_entries` table is NOT used. Data goes into `health_metrics` with `source='lose_it'` and `category='nutrition'`
  - Metric names: `daily_calories, daily_fat_g, daily_protein_g, daily_carbs_g, daily_saturated_fat_g, daily_sugars_g, daily_fiber_g, daily_cholesterol_mg, daily_sodium_mg`
  - Gmail token stored at path set by `settings.gmail_token_file` (default `.gmail_token.json`)

### Phase 4 — RAG Chat Interface ✅

- `backend/app/services/query_router.py` — Classifies queries as `structured | semantic | hybrid` using Gemini; extracts `metric_names`, `categories`, `date_range`, `aggregation` for structured queries; generates optimized semantic search queries
- `backend/app/services/rag.py` — Full RAG pipeline: parallel retrieval + data coverage header + last 5 chat messages as conversation context → Gemini answer generation
- `backend/app/routers/query.py` — `POST /api/chat`, `GET /api/chat/history`, `DELETE /api/chat/history`
- Frontend: `ChatWindow.tsx`, `MessageBubble.tsx` — embedded in dashboard (not a separate page)

#### RAG-specific implementation details:

**Data coverage header** — Every RAG context starts with date ranges of all ingested data so the LLM knows what time period it has access to:
```
DATA COVERAGE (full date ranges of your health data):
- Nutrition (Lose It): 2026-02-26 through 2026-05-26
- Apple Health: 2024-01-01 through 2026-05-26
- Blood Tests: 2026-01-15 through 2026-01-15
```

**Query routing for trend/coverage queries** — Questions like "what food logs do I have?" or "how far back does my data go?" are classified as `structured` with `aggregation="trend"`, which triggers `limit=500, ascending=True` in `get_metrics`. Without this, the LLM only saw the most recent 50 rows.

**Conversation history** — Last 5 messages prepended to every prompt for follow-up question support.

### Phase 5 — Visualizations & Dashboard ✅

- `backend/app/routers/metrics.py` — Added: `GET /api/metrics/timeseries`, `GET /api/metrics/summary`, `GET /api/metrics/biomarkers/latest`, `GET /api/metrics/correlate` (Pearson r)
- `backend/app/db/queries.py` — Added `ascending` param to `get_metrics`, `get_data_coverage()`, `get_latest_metrics()`
- Frontend `dashboard/page.tsx` — Full split-pane layout (see below)
- Frontend components: `MetricChart.tsx`, `BiomarkerTable.tsx`

#### Dashboard layout (current):

```
┌─ Navbar ─────────────────────────────────────────────────────────┐
├─ Left panel (flex-1, scrollable) ─┬─ Right panel (w-[400px]) ──┤
│  ┌── Latest Metrics ───────────┐  │  ┌── Ask your data ───────┐ │
│  │  Weight│HR│HRV│Sleep│Cal   │  │  │  ChatWindow            │ │
│  └─────────────────────────────┘  │  │  (full chat history,   │ │
│  ┌── Trend Chart ───────────────┐  │  │   suggested questions, │ │
│  │  [metric tabs][date range]   │  │  │   input bar)           │ │
│  │  [line chart]                │  │  └────────────────────────┘ │
│  └─────────────────────────────┘  │                              │
│  ┌── Raw Data ──────────────────┐  │                              │
│  │  Blood Test│Nutrition│Fitness│  │                              │
│  │  [tab content]               │  │                              │
│  └─────────────────────────────┘  │                              │
│  ┌── Correlation Explorer ──────┐  │                              │
│  │  [dropdown] vs [dropdown]    │  │                              │
│  │  [scatter plot + Pearson r]  │  │                              │
│  └─────────────────────────────┘  │                              │
└────────────────────────────────────┴──────────────────────────────┘
```

**Raw Data tabs:**
- **Blood Test** — dropdown to select uploaded report → fetches `GET /api/metrics?document_id={id}` → shows `BiomarkerTable`
- **Nutrition** — pivot table (Date | Calories | Protein | Carbs | Fat | Sodium | Fiber), 90-day default, "Load earlier data" loads 90 more days
- **Fitness** — pivot table (Date | Steps | Active Cal | Exercise Min | Resting HR | HRV | Sleep), 90-day default, same load-more pattern

---

## Complete File Inventory

### Backend

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app + lifespan + APScheduler |
| `app/config.py` | Settings via pydantic-settings; includes `gmail_redirect_uri`, `gmail_token_file`, `lose_it_sender_email`, `scheduled_user_id` |
| `app/dependencies.py` | `get_current_user` JWT dependency |
| `app/db/supabase_client.py` | Supabase client (service role) |
| `app/db/queries.py` | All DB queries: `insert_health_metrics`, `get_metrics` (with category/source/document_id/date/limit/ascending filters), `get_latest_metrics`, `get_data_coverage`, `semantic_search`, `save_chat_message`, `get_chat_history`, `clear_chat_history`, `insert_document`, `get_documents`, `get_document_by_hash`, `delete_document`, `insert_document_chunks` |
| `app/models/health_metrics.py` | Pydantic models |
| `app/models/chat.py` | Chat request/response models |
| `app/routers/auth.py` | Signup + login |
| `app/routers/ingest.py` | Blood test, Apple Health, nutrition upload; Gmail OAuth + trigger endpoints |
| `app/routers/metrics.py` | Log, list (with source + document_id filters), latest, timeseries, summary, biomarkers/latest, correlate |
| `app/routers/query.py` | Chat endpoints |
| `app/services/pdf_parser.py` | Blood test PDF extraction + biomarker summary generation |
| `app/services/apple_health.py` | Apple Health XML streaming parser |
| `app/services/nutrition_parser.py` | Lose It daily CSV parser |
| `app/services/embeddings.py` | Gemini embedding generation + chunk storage |
| `app/services/rag.py` | RAG pipeline (classify → retrieve → coverage header → generate) |
| `app/services/query_router.py` | Query classification + structured/semantic/hybrid retrieval |
| `app/services/gmail_watcher.py` | Gmail OAuth2 + email-based CSV ingestion |

### Frontend

| File | Purpose |
|------|---------|
| `src/app/page.tsx` | Login page |
| `src/app/dashboard/page.tsx` | Split-pane dashboard with chat, charts, raw data tabs |
| `src/app/upload/page.tsx` | Blood test + Apple Health + Nutrition upload |
| `src/app/log/page.tsx` | Daily manual logging |
| `src/app/chat/page.tsx` | Standalone chat page (exists but Chat removed from Navbar; dashboard is primary) |
| `src/components/Navbar.tsx` | Nav links: Dashboard, Upload, Daily Log (Chat removed) |
| `src/components/ChatWindow.tsx` | Full chat UI, embedded in dashboard right panel |
| `src/components/MessageBubble.tsx` | User/assistant message rendering with expandable sources |
| `src/components/MetricChart.tsx` | Recharts line chart for time series |
| `src/components/BiomarkerTable.tsx` | Blood test results table with reference range color coding |
| `src/components/FileUploader.tsx` | Drag-and-drop file upload component |
| `src/components/DailyLogForm.tsx` | Daily log form |
| `src/lib/api.ts` | API client (prepends base URL, attaches Bearer token) |
| `src/lib/types.ts` | All TypeScript types: `HealthMetric, ChatMessage, ChatSource, Document, AuthResponse, BloodTestUploadResult, AppleHealthUploadResult, NutritionUploadResult, CorrelateResult, TimeSeriesPoint, ApiError` |

---

## Key Bugs Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Dashboard Calories card showed `—` | `SUMMARY_METRICS` used `dietary_calories` (Apple Health name) but Lose It stores as `daily_calories` | Changed to `daily_calories` in both frontend and backend summary endpoint |
| RAG only returning recent nutrition data | Trend queries used `limit=50, desc` so LLM only saw the latest 50 days | Three-part fix: `ascending` param, `get_data_coverage` header, trend queries use `limit=500, ascending=True` |
| `asyncio` not imported | Added `asyncio.gather()` calls without importing | Added `import asyncio` to `rag.py` and `metrics.py` |

---

## Supabase Schema

Three migrations have been applied (see `health_rag_implementation_plan.md`):
1. Tables: `health_metrics`, `nutrition_entries`, `supplement_log`, `documents`, `document_chunks`, `chat_messages`
2. Row Level Security policies on all tables
3. `match_document_chunks()` function for vector similarity search

**Important:** `document_chunks.embedding` is `vector(768)` — must use `text-embedding-004` (768 dims). Never change this.

The `health_metrics` table uses `UNIQUE(user_id, metric_name, recorded_at, source)` for deduplication. All batch inserts use `upsert` with `on_conflict` to handle re-uploads.

---

## Environment Variables

**`backend/.env`:**
```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
GEMINI_API_KEY=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://localhost:8000/api/ingest/nutrition/gmail-callback
LOSE_IT_SENDER_EMAIL=         # email address Lose It sends from
SCHEDULED_USER_ID=            # Supabase user UUID for auto daily Gmail check (optional)
```

**`frontend/.env.local`:**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Metric Names Reference

**Lose It (nutrition, source=lose_it):**
`daily_calories, daily_fat_g, daily_protein_g, daily_carbs_g, daily_saturated_fat_g, daily_sugars_g, daily_fiber_g, daily_cholesterol_mg, daily_sodium_mg`

**Apple Health (source=apple_health):**
`weight_kg, heart_rate, resting_heart_rate, hrv, step_count, active_calories, exercise_minutes, dietary_calories, sleep_duration_hours, sleep_deep_minutes, sleep_rem_minutes, sleep_core_minutes`

**Blood test (source=blood_test, category=biomarker):**
`ldl_cholesterol, hdl_cholesterol, total_cholesterol, triglycerides, hba1c, fasting_glucose, tsh, free_t4, vitamin_d, vitamin_b12, iron, ferritin, hemoglobin, creatinine, egfr, alt, ast, crp, testosterone, cortisol`

**Conflict:** Both Apple Health and Lose It can store calories. Apple Health uses `dietary_calories`; Lose It uses `daily_calories`. The summary endpoint queries both and returns whichever is present. The dashboard defaults to showing `daily_calories`.

---

## Phase 6 — What's Left

From `health_rag_implementation_plan.md`:

**Step 6.1: Apple Health Auto-Sync**
- Add `POST /api/ingest/apple-health/auto` endpoint for JSON payloads from "Health Auto Export" iOS app
- User needs to install "Health Auto Export" app and configure webhook to backend URL

**Step 6.2: Data Validation & Quality**
- Input validation (physiologically impossible values, future dates)
- `GET /api/metrics/data-quality` endpoint (date ranges, gaps, record counts per source)

**Step 6.3: Chat Improvements**
- Suggested follow-up questions after each answer (already has conversation history)
- Streaming responses via `StreamingResponse` + Gemini streaming API

**Step 6.4: Mobile-Friendly UI**
- Responsive breakpoints for the split-pane dashboard (currently desktop-only)
- Touch-friendly controls

**Step 6.5: Deployment**
- Frontend → Vercel
- Backend → Railway or Fly.io (Dockerfile exists)
- Update CORS allowed origins in `main.py`

---

## Notes for Next Session

- The standalone `/chat` page still exists at `frontend/src/app/chat/page.tsx` but Chat is removed from the Navbar. Chat is now embedded in the dashboard's right panel. The `/chat` page can be kept as-is or deleted.
- `backend/venv/` uses Python 3.9; all files have `from __future__ import annotations` for compatibility with union type syntax (`str | None`, `list[dict]`).
- The query router's `CLASSIFICATION_PROMPT` in `query_router.py` has explicit examples for nutrition coverage questions and the full list of metric names. If new metric types are added, update this prompt.
- `get_data_coverage()` in `queries.py` queries three hardcoded sources: `lose_it`, `apple_health`, `blood_test`. If new sources are added, update this function.
