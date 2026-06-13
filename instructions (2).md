# INSTRUCTIONS.md — Health RAG Project

## What You Are Building

A personal health knowledgebase with RAG (Retrieval-Augmented Generation) capabilities. It ingests health records (blood tests, Apple Watch data, nutrition logs, manual daily tracking), stores data in both structured and vector formats, and exposes it through a chat interface and visualization dashboard.

The full specification is in `PLAN.md`. This file tells you how to work. `PLAN.md` tells you what to build.

---

## Ground Rules

- **Never work outside the current phase.** Complete and verify the current phase fully before moving to the next.
- **Never skip a verification checklist.** Every phase ends with a checklist. All items must pass before proceeding.
- **Never hardcode credentials.** All API keys, URLs, and secrets must come from environment variables via `config.py`.
- **Never guess at requirements.** If something is ambiguous, stop and ask before writing code.
- **Always write async code** for any database operation, HTTP call, or file I/O. This is a FastAPI project — sync blocking calls are not acceptable.
- **Always handle errors explicitly.** Every endpoint and every service function must catch exceptions and return a structured error response. No bare `except: pass` blocks.
- **One file at a time.** Create or edit one file, confirm it is correct, then move to the next. Do not generate multiple files in one response without confirming each.

---

## Project Structure

All code lives in the `health-rag/` root directory. The two top-level directories are `backend/` and `frontend/`. Never create files outside this structure without asking first.

```
health-rag/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── models/
│   │   ├── routers/
│   │   ├── services/
│   │   └── db/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── .env.local.example
├── PLAN.md
└── INSTRUCTIONS.md
```

The purpose of every file in this structure is documented in `PLAN.md`. Follow it exactly. Do not rename files or reorganize the structure.

---

## Tech Stack — Do Not Deviate

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend language | Python | 3.11+ |
| Backend framework | FastAPI | 0.115.0 |
| Backend server | Uvicorn | 0.30.0 |
| Data validation | Pydantic + pydantic-settings | 2.x |
| Database client | supabase-py | 2.9.0 |
| LLM + embeddings | google-generativeai | 0.8.0 |
| PDF parsing | PyPDF2 | 3.0.1 |
| HTTP client | httpx | 0.27.0 — never use `requests` |
| Excel/CSV parsing | openpyxl | 3.1.5 |
| Scheduling | APScheduler | 3.10.4 |
| Gmail integration | google-api-python-client | 2.149.0 |
| Frontend framework | Next.js | 14 (App Router) |
| Frontend language | TypeScript | strict mode |
| Frontend styling | Tailwind CSS | latest |
| Frontend charts | Recharts | latest |

If a library is not in this list and not in `requirements.txt`, ask before adding it.

---

## Environment Variables

### Backend — `backend/.env`

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
GEMINI_API_KEY=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
```

### Frontend — `frontend/.env.local`

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

All environment variables are read through `app/config.py` using `pydantic-settings`. Never read `os.environ` directly anywhere else in the codebase.

---

## Code Conventions

### Python

**Config access:**
```python
# Correct — always import settings from config
from app.config import settings

supabase_url = settings.supabase_url
```

**Async pattern:**
```python
# All route handlers and service functions must be async
@router.post("/api/ingest/blood-test")
async def upload_blood_test(file: UploadFile, user=Depends(get_current_user)):
    ...
```

**Error handling pattern:**
```python
# Every endpoint must return structured errors
from fastapi import HTTPException

try:
    result = await some_service.do_something()
except SomeSpecificException as e:
    raise HTTPException(status_code=422, detail=f"Processing failed: {str(e)}")
except Exception as e:
    # Log the full traceback, return a safe message to the client
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

**Supabase client — use service role for all backend operations:**
```python
from app.db.supabase_client import get_supabase_client

client = get_supabase_client()  # Uses service_role_key — bypasses RLS
```

**Logging:**
```python
import logging
logger = logging.getLogger(__name__)

# Use logger, never print()
logger.info("Processing blood test PDF")
logger.error("Failed to parse PDF", exc_info=True)
```

**Retry logic for Gemini API calls** (required for embedding generation):
```python
import asyncio

async def call_with_retry(fn, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
```

### TypeScript / Next.js

**API calls — always use `src/lib/api.ts`:**
```typescript
// Never use raw fetch in components
// Always go through the API client in lib/api.ts
import { apiClient } from '@/lib/api'

const data = await apiClient.post('/api/chat', { message })
```

**Type safety:**
```typescript
// All API response shapes must have a corresponding type in src/lib/types.ts
// Never use `any`
import type { ChatMessage, HealthMetric } from '@/lib/types'
```

**State management:**
```typescript
// Use useState and useContext only — no Redux, no Zustand, no external state libraries
const [messages, setMessages] = useState<ChatMessage[]>([])
```

**No HTML form tags:**
```tsx
// Wrong
<form onSubmit={handleSubmit}>...</form>

// Correct
<div>
  <input onChange={...} />
  <button onClick={handleSubmit}>Submit</button>
</div>
```

---

## Database Rules

- **Never write raw SQL in route handlers.** All queries go in `app/db/queries.py` or via the Supabase client.
- **Always use `ON CONFLICT DO NOTHING`** for batch inserts where duplicates are possible (Apple Health imports, nutrition imports).
- **Embedding dimension is 768.** The `document_chunks.embedding` column is `vector(768)`. Gemini `text-embedding-004` outputs 768 dimensions. These must always match. Never change this without updating both the schema and the model call.
- **The `document_chunks` table stores semantic text, not raw data strings.** Only human-readable, contextually meaningful text goes in this table. See embedding rules below.

---

## Embedding Rules

This is the most important architectural rule in the project. Follow it exactly.

**What gets embedded and what does not:**

| Data Type | Embed? | What to Embed |
|-----------|--------|---------------|
| Blood test biomarkers | YES | LLM-generated text summaries grouped by biomarker panel (lipids, thyroid, vitamins, etc.) — NOT the raw PDF text |
| Blood test doctor notes | YES | The notes text directly, chunked by sentence |
| Apple Health metrics (HR, sleep, steps) | NO | Query these via SQL only |
| Nutrition daily summaries | YES | Generated text like "On Jan 15, you ate oatmeal for breakfast (350 cal), chicken salad for lunch (520 cal)..." |
| Individual food entries | YES | Food name + meal context as short text |
| Supplement logs | NO | Query these via SQL only |
| Weight / body composition | NO | Query these via SQL only |
| Manual subjective logs (energy, mood) | YES | Generated text like "On Jan 15, energy level was 2/5. Noted shoulder tightness." |

**Blood test embedding — specific process:**

1. LLM extracts structured JSON from PDF (biomarkers + values + reference ranges)
2. From that JSON, generate human-readable summary strings — one overall summary + one per biomarker group
3. Embed the summary strings, NOT the raw PDF text
4. Example of a correctly generated chunk:

```
Lipid panel — LifeLabs, January 15, 2026.
LDL cholesterol: 3.8 mmol/L — above reference range of 0.0–3.4, flagged HIGH.
HDL cholesterol: 1.6 mmol/L — within reference range of 1.0–1.9, normal.
Total cholesterol: 5.9 mmol/L — above reference range of 0.0–5.2, flagged HIGH.
Triglycerides: 1.1 mmol/L — within reference range of 0.0–1.7, normal.
```

**Never embed:**
- Raw numbers without units or context
- Raw PDF text
- Tabular data formatted as strings (e.g. `"LDL-C 3.2 mmol/L [2.0–3.4]"`)
- Any data that is better answered by a SQL query (exact values, specific dates, counts)

---

## The RAG Pipeline — How It Works

When a user sends a chat message, the system must:

1. **Classify the query** — send it to Gemini to determine if it needs structured data (SQL), semantic search (vector), or both
2. **Retrieve context** based on classification:
   - Structured: query `health_metrics` or `nutrition_entries` via SQL
   - Semantic: embed the query, run `match_document_chunks` Supabase function
   - Hybrid: do both, combine results
3. **Generate the answer** — send the retrieved context + question to Gemini with the system prompt defined in `PLAN.md`
4. **Store** the question and answer in `chat_messages`
5. **Return** the answer and source references to the frontend

The query classification step is not optional. Do not skip it and default to semantic search for all queries — this will produce wrong answers for numeric/date questions.

---

## Phase Workflow

Each phase in `PLAN.md` must be completed in this order:

```
1. Read the full phase spec in PLAN.md before writing any code
2. Identify all files to be created or modified
3. Create/modify files one at a time, confirming each
4. Run the verification checklist at the end of the phase
5. Fix any failing checks before moving to the next phase
6. Confirm with the user that the phase is complete
```

**Do not begin a new phase until the user explicitly confirms the current phase is done.**

---

## Starting Each Session

At the start of every new conversation, state:

1. Which phase you are currently on
2. Which step within that phase you are on
3. What the next action is
4. Any blockers or open questions

Example:
```
Currently on Phase 1, Step 1.3 — Embedding Pipeline.
Next action: create app/services/embeddings.py with generate_embedding() and embed_and_store_chunks() functions.
No blockers.
```

If you do not know what phase/step you are on, ask the user before doing anything else.

---

## What to Do When Stuck

1. **If a library behaves unexpectedly:** Check the installed version against `requirements.txt`. Try the simplest possible usage first. Ask before switching to a different library.
2. **If the Gemini API returns an unexpected format:** Log the full raw response. Adjust the prompt before changing the parsing code.
3. **If a Supabase query fails:** Check the RLS policies first. Confirm the client is using the service role key for backend operations.
4. **If a type error occurs in TypeScript:** Fix the type, do not use `as any` to suppress it.
5. **If you are unsure whether something is in scope for the current phase:** Check `PLAN.md`. If it is not described in the current phase, do not build it.

---

## Out of Scope for This Project

Do not build any of the following unless explicitly added to `PLAN.md`:

- User accounts for multiple users (this is a single-user personal tool)
- Native mobile app (the web UI should be mobile-responsive, but no React Native)
- Real-time websockets (streaming responses in Phase 6 use SSE, not websockets)
- Custom embedding model fine-tuning
- On-device / local LLM inference
- Any integration not listed in `PLAN.md` (no Oura, Whoop, Garmin, MyFitnessPal until post-MVP)
