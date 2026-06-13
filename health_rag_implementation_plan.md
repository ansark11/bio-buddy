# Personal Health RAG — Implementation Plan

## Project Overview

Build a personal health knowledgebase with RAG (Retrieval-Augmented Generation) capabilities. The system ingests health data from multiple sources (blood tests, Apple Watch, nutrition logs, manual tracking), stores it in structured and vector formats, and exposes it through a chat interface and visualization dashboard.

**This document is the single source of truth for building this project. Follow each phase sequentially. Do not skip ahead.**

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts | Modern React framework with good deployment story |
| Backend | Python 3.11+, FastAPI | Strong ecosystem for data processing, PDF parsing, ML |
| Database | Supabase (PostgreSQL + pgvector extension) | Structured data + vector embeddings in one place |
| LLM | Google Gemini API (gemini-2.0-flash or later) | Document extraction + RAG query answering |
| Embeddings | Google Gemini embedding model (text-embedding-004) | Generate vectors for semantic search |
| Auth | Supabase Auth (email/password, single user) | Simple auth for personal use |
| Deployment | Vercel (frontend), Railway or Fly.io (backend) | Easy deployment, good free tiers |

---

## Required User Inputs / Actions

**Collect all of these before starting development.**

### API Keys & Credentials

| Item | Where to Get It | Env Variable Name |
|------|----------------|-------------------|
| Supabase Project URL | Supabase dashboard → Settings → API | `SUPABASE_URL` |
| Supabase Anon Key | Supabase dashboard → Settings → API | `SUPABASE_ANON_KEY` |
| Supabase Service Role Key | Supabase dashboard → Settings → API | `SUPABASE_SERVICE_ROLE_KEY` |
| Supabase DB Connection String | Supabase dashboard → Settings → Database → Connection string (URI) | `DATABASE_URL` |
| Google Gemini API Key | Google AI Studio → https://aistudio.google.com/apikey | `GEMINI_API_KEY` |
| Gmail OAuth2 Client ID | Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client | `GMAIL_CLIENT_ID` |
| Gmail OAuth2 Client Secret | Same as above | `GMAIL_CLIENT_SECRET` |

### User Actions Required Per Phase

**Phase 1:**
- Enable the `pgvector` extension in Supabase (SQL Editor → `CREATE EXTENSION IF NOT EXISTS vector;`)
- Upload at least 1 sample blood test PDF for testing

**Phase 3:**
- Set up a Google Cloud project with Gmail API enabled
- Complete OAuth2 consent screen setup
- Configure Lose It to send daily scheduled email exports
- Identify the sender email address Lose It uses (needed for email filtering)

**Phase 6:**
- Install "Health Auto Export" app on iPhone (paid app, ~$5) OR be prepared to do manual Apple Health exports periodically
- Configure the app to POST to your backend API endpoint

---

## Project Structure

```
health-rag/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entry point
│   │   ├── config.py                # Environment variables, settings
│   │   ├── dependencies.py          # Shared dependencies (DB sessions, etc.)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── health_metrics.py    # Pydantic models for health data
│   │   │   └── chat.py              # Pydantic models for chat requests/responses
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py            # Upload & ingestion endpoints
│   │   │   ├── query.py             # RAG chat endpoint
│   │   │   ├── metrics.py           # Manual logging + retrieval endpoints
│   │   │   └── auth.py              # Authentication endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── pdf_parser.py        # Blood test PDF extraction via LLM
│   │   │   ├── apple_health.py      # Apple Health XML parser
│   │   │   ├── nutrition_parser.py  # Lose It CSV/spreadsheet parser
│   │   │   ├── embeddings.py        # Text chunking + embedding generation
│   │   │   ├── rag.py               # RAG pipeline (retrieve + generate)
│   │   │   ├── query_router.py      # Routes questions to vector/SQL/both
│   │   │   └── gmail_watcher.py     # Gmail API integration for Lose It emails
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── supabase_client.py   # Supabase client setup
│   │       └── queries.py           # Raw SQL queries for structured data
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx             # Landing/dashboard
│   │   │   ├── chat/
│   │   │   │   └── page.tsx         # Chat interface
│   │   │   ├── dashboard/
│   │   │   │   └── page.tsx         # Visualizations
│   │   │   ├── upload/
│   │   │   │   └── page.tsx         # Manual file upload
│   │   │   └── log/
│   │   │       └── page.tsx         # Daily manual logging
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── FileUploader.tsx
│   │   │   ├── DailyLogForm.tsx
│   │   │   ├── MetricChart.tsx
│   │   │   ├── BiomarkerTable.tsx
│   │   │   └── Navbar.tsx
│   │   └── lib/
│   │       ├── api.ts               # Backend API client
│   │       └── types.ts             # TypeScript types
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── .env.local.example
├── .gitignore
├── README.md
└── PLAN.md                          # This file
```

---

## Database Schema

**Run these migrations in Supabase SQL Editor in order.**

### Migration 1: Enable pgvector and create core tables

```sql
-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enum for data sources
CREATE TYPE data_source AS ENUM (
  'blood_test',
  'apple_health',
  'lose_it',
  'manual'
);

-- Enum for metric categories
CREATE TYPE metric_category AS ENUM (
  'biomarker',        -- blood test results (cholesterol, vitamin D, etc.)
  'body_composition', -- weight, body fat %
  'cardiovascular',   -- resting HR, HRV
  'sleep',            -- duration, quality
  'nutrition',        -- calories, macros
  'activity',         -- steps, active calories, exercise minutes
  'subjective',       -- energy, mood ratings
  'supplement'        -- supplement intake tracking
);

-- Core structured metrics table
-- Every numeric health data point goes here
CREATE TABLE health_metrics (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  metric_name TEXT NOT NULL,           -- e.g. 'ldl_cholesterol', 'resting_hr', 'weight_kg'
  metric_value NUMERIC NOT NULL,       -- the actual number
  unit TEXT NOT NULL,                  -- e.g. 'mmol/L', 'bpm', 'kg'
  category metric_category NOT NULL,
  source data_source NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,    -- when the measurement was taken
  reference_range_low NUMERIC,         -- optional: lab reference range
  reference_range_high NUMERIC,
  metadata JSONB DEFAULT '{}',         -- flexible field for source-specific data
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Prevent duplicate entries
  UNIQUE(user_id, metric_name, recorded_at, source)
);

-- Index for time-series queries
CREATE INDEX idx_health_metrics_user_time ON health_metrics(user_id, recorded_at DESC);
CREATE INDEX idx_health_metrics_category ON health_metrics(user_id, category, recorded_at DESC);
CREATE INDEX idx_health_metrics_name ON health_metrics(user_id, metric_name, recorded_at DESC);

-- Nutrition log — individual food entries (more granular than metrics)
CREATE TABLE nutrition_entries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  food_name TEXT NOT NULL,
  meal_type TEXT,                       -- breakfast, lunch, dinner, snack
  calories NUMERIC,
  protein_g NUMERIC,
  carbs_g NUMERIC,
  fat_g NUMERIC,
  fiber_g NUMERIC,
  sodium_mg NUMERIC,
  sugar_g NUMERIC,
  recorded_at TIMESTAMPTZ NOT NULL,
  source data_source DEFAULT 'lose_it',
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_nutrition_user_time ON nutrition_entries(user_id, recorded_at DESC);

-- Supplement tracking
CREATE TABLE supplement_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  supplement_name TEXT NOT NULL,        -- e.g. 'Vitamin D3', 'Creatine', 'Fish Oil'
  dosage TEXT,                          -- e.g. '5000 IU', '5g'
  taken BOOLEAN DEFAULT TRUE,          -- did they actually take it today?
  recorded_at DATE NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, supplement_name, recorded_at)
);

-- Document store — original uploaded files
CREATE TABLE documents (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  filename TEXT NOT NULL,
  file_type TEXT NOT NULL,              -- 'pdf', 'xml', 'csv'
  source data_source NOT NULL,
  upload_date TIMESTAMPTZ DEFAULT NOW(),
  processed BOOLEAN DEFAULT FALSE,
  processing_error TEXT,
  metadata JSONB DEFAULT '{}',         -- e.g. lab name, test date extracted from PDF
  raw_text TEXT                         -- full extracted text from document
);

-- Vector embeddings for RAG
CREATE TABLE document_chunks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chunk_text TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,         -- ordering within document
  embedding vector(768) NOT NULL,       -- Gemini text-embedding-004 outputs 768 dims
  source data_source NOT NULL,
  metadata JSONB DEFAULT '{}',          -- e.g. metric names mentioned, date context
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity search index
CREATE INDEX idx_chunks_embedding ON document_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Chat history
CREATE TABLE chat_messages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  sources JSONB DEFAULT '[]',           -- references to chunks/metrics used
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_user_time ON chat_messages(user_id, created_at DESC);
```

### Migration 2: Row Level Security

```sql
-- Enable RLS on all tables
ALTER TABLE health_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE nutrition_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplement_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

-- Policies: users can only access their own data
CREATE POLICY "Users can CRUD own health_metrics"
  ON health_metrics FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD own nutrition_entries"
  ON nutrition_entries FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD own supplement_log"
  ON supplement_log FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD own documents"
  ON documents FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD own document_chunks"
  ON document_chunks FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can CRUD own chat_messages"
  ON chat_messages FOR ALL
  USING (auth.uid() = user_id);
```

### Migration 3: Vector search function

```sql
-- Function for semantic similarity search
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding vector(768),
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 10,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS TABLE (
  id UUID,
  chunk_text TEXT,
  source data_source,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    dc.id,
    dc.chunk_text,
    dc.source,
    dc.metadata,
    1 - (dc.embedding <=> query_embedding) AS similarity
  FROM document_chunks dc
  WHERE dc.user_id = p_user_id
    AND 1 - (dc.embedding <=> query_embedding) > match_threshold
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

---

## Phase 1: Foundation — Blood Test PDF Ingestion

**Goal:** Upload a blood test PDF → LLM extracts biomarkers → stored in database → retrievable via API.

**Duration:** ~2 weeks

### Step 1.1: Backend Project Setup

1. Create the `backend/` directory with the project structure above
2. Create a Python virtual environment: `python -m venv venv`
3. Install dependencies:

```
# requirements.txt
fastapi==0.115.0
uvicorn==0.30.0
python-multipart==0.0.9
supabase==2.9.0
google-generativeai==0.8.0
python-dotenv==1.0.1
pydantic==2.9.0
pydantic-settings==2.5.0
httpx==0.27.0
PyPDF2==3.0.1
python-jose[cryptography]==3.3.0
```

4. Create `.env` file from `.env.example` with all required variables
5. Create `app/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    gemini_api_key: str
    gmail_client_id: str = ""       # Not needed until Phase 3
    gmail_client_secret: str = ""   # Not needed until Phase 3

    class Config:
        env_file = ".env"

settings = Settings()
```

6. Create `app/main.py` with FastAPI app, CORS middleware (allow Vercel frontend origin), and health check endpoint at `GET /health`
7. Create `app/db/supabase_client.py` that initializes the Supabase client using service role key (for backend operations that bypass RLS)
8. Verify the app starts: `uvicorn app.main:app --reload`

### Step 1.2: PDF Ingestion Pipeline

Build `app/services/pdf_parser.py`:

1. Accept a PDF file (bytes)
2. Extract raw text using PyPDF2
3. Send the raw text to Gemini with a structured extraction prompt. The prompt should instruct the model to return JSON in this exact shape:

```json
{
  "lab_name": "string",
  "test_date": "YYYY-MM-DD",
  "patient_name": "string",
  "biomarkers": [
    {
      "name": "string",
      "standardized_name": "string",
      "value": 0.0,
      "unit": "string",
      "reference_range_low": 0.0,
      "reference_range_high": 0.0,
      "flag": "normal | high | low | null"
    }
  ],
  "notes": "string — any doctor notes or comments"
}
```

4. The prompt must include a mapping of common biomarker aliases to standardized names. For example:
   - "LDL-C", "LDL Cholesterol", "Low-Density Lipoprotein" → `ldl_cholesterol`
   - "HDL-C", "HDL Cholesterol" → `hdl_cholesterol`
   - "HbA1c", "Hemoglobin A1c" → `hba1c`
   - "TSH", "Thyroid Stimulating Hormone" → `tsh`
   - "25-OH Vitamin D", "Vitamin D, 25-Hydroxy" → `vitamin_d`
   - (Include 30+ common biomarkers in the prompt)

5. Parse the Gemini response, validate with Pydantic models
6. Store each biomarker as a row in `health_metrics` with `category='biomarker'` and `source='blood_test'`
7. Store the full document record in `documents` with `processed=true`

**Step 1.2a: Generate text summaries from extracted biomarkers**

After structured extraction is complete, generate human-readable text summaries from the extracted JSON — **not** from the raw PDF text. This is what gets embedded for RAG, not the raw PDF content.

Add a `generate_blood_test_summary(extracted_data: dict) -> list[str]` function to `pdf_parser.py` that produces two types of summaries:

**1. Overall test summary** (one per blood test):
```
Blood test from LifeLabs on January 15, 2026. 12 biomarkers measured.
3 values flagged: Vitamin D was 28 nmol/L (low, reference range 75–250),
Iron was 8.2 umol/L (low, reference range 11–32), LDL was 3.8 mmol/L
(high, reference range 0–3.4). All other values within normal range.
```

**2. Per-biomarker summaries** (one per biomarker, grouped by category):
```
# Lipid panel — January 15, 2026
LDL cholesterol was 3.8 mmol/L, above the reference range of 0.0–3.4, flagged as high.
HDL cholesterol was 1.6 mmol/L, within the reference range of 1.0–1.9, normal.
Total cholesterol was 5.9 mmol/L, within the reference range of 0.0–5.2, flagged as high.
Triglycerides were 1.1 mmol/L, within the reference range of 0.0–1.7, normal.
```

Group biomarkers by panel/category (lipids, thyroid, CBC, vitamins, metabolic) so related values are embedded together. This improves retrieval accuracy for questions like "how are my cholesterol levels?" — the entire lipid panel is in one chunk rather than scattered.

The function should return a list of these summary strings — one overall + one per biomarker group. These strings are what get passed to the embedding pipeline, not the raw PDF text.

### Step 1.3: Embedding Pipeline

Build `app/services/embeddings.py`:

1. Create a `generate_embedding(text: str) -> list[float]` function that calls Gemini's embedding API (`text-embedding-004` model)
2. Create a `embed_and_store_chunks(document_id: UUID, text_chunks: list[str], user_id: UUID, source: str, metadata: dict)` function that:
   - Generates embeddings for each chunk
   - Stores chunks + embeddings in `document_chunks` table
   - Attaches the provided metadata to each chunk (e.g. `{"test_date": "2026-01-15", "lab_name": "LifeLabs", "biomarker_group": "lipids"}`)
3. Note: the generic `chunk_text()` splitter is **not used for blood tests**. Blood tests use the structured summary strings from Step 1.2a as their chunks. The `chunk_text()` splitter is only needed for free-form text sources like doctor notes.

### Step 1.4: Upload Endpoint

Build `app/routers/ingest.py`:

1. `POST /api/ingest/blood-test` — accepts a PDF file upload (multipart form)
2. Flow: receive file → extract raw text from PDF → send raw text to LLM for structured JSON extraction → store biomarkers in `health_metrics` → **generate human-readable summaries from the extracted JSON** → embed the summaries → store in `document_chunks` → return summary of what was extracted
3. Include error handling: if LLM extraction fails, store the document with `processed=false` and `processing_error` message
4. Add a `GET /api/ingest/documents` endpoint to list all uploaded documents

### Step 1.5: Basic Auth

Build `app/routers/auth.py`:

1. `POST /api/auth/signup` — create user via Supabase Auth
2. `POST /api/auth/login` — sign in, return JWT
3. Create a `get_current_user` dependency that validates the Supabase JWT from the Authorization header and extracts `user_id`
4. Apply this dependency to all protected routes

### Step 1.6: Frontend Setup

1. Create Next.js 14 project with App Router: `npx create-next-app@14 frontend --typescript --tailwind --app`
2. Create `.env.local` with `NEXT_PUBLIC_API_URL` pointing to backend
3. Build `src/lib/api.ts` — a thin wrapper around `fetch` that:
   - Prepends the API base URL
   - Attaches the auth token from localStorage
   - Handles errors consistently
4. Build a simple login page at `/` — email + password form, calls signup/login endpoints, stores token
5. Build an upload page at `/upload`:
   - File picker that accepts PDFs
   - Upload button that sends to `POST /api/ingest/blood-test`
   - Display the extracted biomarkers in a simple table after upload completes
   - Show upload history (list of processed documents)

### Phase 1 Verification

- [ ] Can sign up and log in
- [ ] Can upload a blood test PDF
- [ ] LLM extracts biomarkers correctly (spot-check against the original PDF)
- [ ] Biomarkers stored in `health_metrics` table with correct values, units, reference ranges
- [ ] Human-readable summaries generated from extracted biomarkers (check the `chunk_text` column in `document_chunks` — it should read as natural sentences, not raw lab report text)
- [ ] Summary chunks embedded and stored in `document_chunks` with correct metadata (test date, lab name, biomarker group)
- [ ] Upload history displays on the frontend

---

## Phase 2: Apple Health + Manual Tracking

**Goal:** Import Apple Health XML export. Build manual logging endpoints and UI for daily metrics.

**Duration:** ~2 weeks

### Step 2.1: Apple Health XML Parser

Build `app/services/apple_health.py`:

1. Accept the Apple Health export XML file (can be 100MB+, so stream-parse with `xml.etree.ElementTree.iterparse`, do NOT load into memory)
2. Extract these record types from `<Record>` elements:

| Apple Health Type String | Maps To `metric_name` | Category |
|-------------------------|----------------------|----------|
| `HKQuantityTypeIdentifierBodyMass` | `weight_kg` | `body_composition` |
| `HKQuantityTypeIdentifierHeartRate` | `heart_rate` | `cardiovascular` |
| `HKQuantityTypeIdentifierRestingHeartRate` | `resting_heart_rate` | `cardiovascular` |
| `HKQuantityTypeIdentifierHeartRateVariabilitySDNN` | `hrv` | `cardiovascular` |
| `HKQuantityTypeIdentifierStepCount` | `step_count` | `activity` |
| `HKQuantityTypeIdentifierActiveEnergyBurned` | `active_calories` | `activity` |
| `HKQuantityTypeIdentifierAppleExerciseTime` | `exercise_minutes` | `activity` |
| `HKQuantityTypeIdentifierDietaryEnergyConsumed` | `dietary_calories` | `nutrition` |

3. Extract sleep data from `<Record>` elements with type `HKCategoryTypeIdentifierSleepAnalysis`. Sleep records need special handling:
   - Values map to sleep stages: `HKCategoryValueSleepAnalysisAsleepCore`, `AsleepDeep`, `AsleepREM`, `Awake`, `InBed`
   - Aggregate per night: calculate total sleep duration, time in each stage
   - Store as `sleep_duration_hours`, `sleep_deep_minutes`, `sleep_rem_minutes`, `sleep_core_minutes` in `health_metrics`
   - A "night" is defined as records between 6 PM and 12 PM the next day

4. For high-frequency metrics (heart rate can have entries every few minutes), aggregate:
   - Heart rate: store daily resting HR (use Apple's resting HR record), daily average, daily min, daily max
   - Steps: sum per day
   - Active calories: sum per day

5. Batch insert into `health_metrics` with `source='apple_health'`
6. Handle deduplication: use the `UNIQUE(user_id, metric_name, recorded_at, source)` constraint with `ON CONFLICT DO NOTHING`

### Step 2.2: Apple Health Upload Endpoint

Add to `app/routers/ingest.py`:

1. `POST /api/ingest/apple-health` — accepts a ZIP file (Apple Health exports as `export.zip` containing `export.xml`)
2. Flow: receive ZIP → extract XML → stream-parse → batch insert metrics → return summary (date range covered, record counts per metric)
3. This will be a long-running operation for large exports. Options:
   - **Simple approach (do this first):** synchronous processing with a generous timeout (5 minutes). Return results when done.
   - **Better approach (Phase 6):** background job with status polling

### Step 2.3: Manual Logging Endpoints

Build `app/routers/metrics.py`:

1. `POST /api/metrics/log` — log a single metric:

```json
{
  "metric_name": "weight_kg",
  "metric_value": 82.5,
  "unit": "kg",
  "category": "body_composition",
  "recorded_at": "2025-01-15T08:00:00Z"
}
```

2. `POST /api/metrics/log/supplement` — log supplement intake:

```json
{
  "supplement_name": "Vitamin D3",
  "dosage": "5000 IU",
  "taken": true,
  "recorded_at": "2025-01-15",
  "notes": ""
}
```

3. `GET /api/metrics?category=cardiovascular&start_date=2025-01-01&end_date=2025-01-31` — retrieve metrics with filters
4. `GET /api/metrics/latest?metric_names=weight_kg,resting_heart_rate` — get most recent value for specified metrics

### Step 2.4: Daily Logging UI

Build `/log` page in the frontend:

1. **Quick Log form** with sections:
   - **Body weight:** single number input (kg), auto-fills today's date
   - **Energy/mood:** 1-5 scale selector (buttons or slider)
   - **Water intake:** number input (glasses or mL)
   - **Supplements:** checklist of configured supplements with toggle for each (taken/not taken). First-time setup: let user define their supplement list (stored in localStorage or a user_preferences table)

2. **Log history:** show today's entries with ability to edit
3. Submit all entries as a batch to the logging endpoints

### Phase 2 Verification

- [ ] Can upload Apple Health export ZIP
- [ ] Sleep, heart rate, HRV, steps, calories parsed correctly
- [ ] Deduplication works (re-uploading same export doesn't create duplicates)
- [ ] Can log weight, mood, water, supplements from the UI
- [ ] Can retrieve metrics by category and date range via API

---

## Phase 3: Nutrition Data from Lose It

**Goal:** Parse Lose It spreadsheet exports and set up automated Gmail-based ingestion.

**Duration:** ~1 week

### Step 3.1: Lose It Spreadsheet Parser

Build `app/services/nutrition_parser.py`:

1. **USER ACTION REQUIRED:** Export one sample spreadsheet from Lose It and examine the format. Document the column names and structure. Common Lose It export columns include: Date, Name, Type (Breakfast/Lunch/Dinner/Snack), Quantity, Calories, Fat (g), Protein (g), Carbohydrates (g), Fiber (g), Sugar (g), Sodium (mg).
2. Build a parser that:
   - Reads the spreadsheet (use `openpyxl` for .xlsx or `csv` module for .csv)
   - Maps each food entry row to a `nutrition_entries` record
   - Calculates daily summaries (total calories, total protein, etc.) and stores as `health_metrics` with `category='nutrition'`
3. Handle edge cases: empty rows, partial entries, date format variations

### Step 3.2: Manual Nutrition Upload Endpoint

Add to `app/routers/ingest.py`:

1. `POST /api/ingest/nutrition` — accepts spreadsheet file upload
2. Parse → store individual entries in `nutrition_entries` → store daily summaries in `health_metrics` → chunk food descriptions and embed for RAG

### Step 3.3: Gmail Auto-Ingestion

**USER ACTION REQUIRED:** Complete Google Cloud OAuth2 setup before this step.

Build `app/services/gmail_watcher.py`:

1. Set up Gmail API client with OAuth2 credentials
2. Create a function `check_for_nutrition_emails()` that:
   - Searches Gmail for emails from Lose It's sender address (user provides this) with attachments
   - Filters to unread/unprocessed emails
   - Downloads the spreadsheet attachment
   - Passes it through the nutrition parser from Step 3.1
   - Marks the email as processed (add a label or mark as read)
3. Add a `POST /api/ingest/nutrition/check-email` endpoint that triggers this check manually
4. Set up a scheduled job (use `apscheduler` or a simple cron) to run this check daily

Add to `requirements.txt`:

```
google-api-python-client==2.149.0
google-auth-oauthlib==1.2.1
google-auth-httplib2==0.2.0
openpyxl==3.1.5
APScheduler==3.10.4
```

### Step 3.4: Nutrition Embedding for RAG

After parsing nutrition data:

1. Create text summaries of daily nutrition: "On January 15, 2025, you ate: Oatmeal with banana for breakfast (350 cal), Chicken caesar salad for lunch (520 cal)..." etc.
2. Chunk and embed these summaries so the RAG system can answer questions like "when did I last eat sushi?" or "what do I typically eat for breakfast?"

### Phase 3 Verification

- [ ] Can upload Lose It export manually and see entries parsed
- [ ] Daily nutrition summaries appear in `health_metrics`
- [ ] Individual food entries appear in `nutrition_entries`
- [ ] Gmail watcher finds and processes Lose It emails
- [ ] Nutrition text chunks are embedded for RAG

---

## Phase 4: RAG Chat Interface

**Goal:** Ask questions about your health data and get accurate, grounded answers.

**Duration:** ~2 weeks

### Step 4.1: Query Router

Build `app/services/query_router.py`:

This is the brain of the RAG system. It determines how to answer a question.

1. Send the user's question to Gemini with a classification prompt:

```
Given this user question about their health data, classify the query type:

Question: "{user_question}"

Respond with JSON:
{
  "query_type": "structured" | "semantic" | "hybrid",
  "structured_query": {
    "metric_names": ["ldl_cholesterol"],  // if applicable
    "categories": ["biomarker"],           // if applicable
    "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},  // if applicable
    "aggregation": "latest" | "trend" | "average" | "min" | "max"  // if applicable
  },
  "semantic_search_query": "rephrased query for embedding search",  // if applicable
  "reasoning": "why this classification"
}

Rules:
- "structured" = questions about specific numbers, trends, comparisons (e.g. "what was my LDL?", "how has my weight changed?")
- "semantic" = questions about qualitative info, notes, food details, context (e.g. "what did my doctor flag?", "when did I eat sushi?")
- "hybrid" = questions that need both numbers AND context (e.g. "are my vitamin D levels improving and could my diet explain it?")
```

2. Based on classification, execute the appropriate retrieval:

**Structured path:**
- Build and execute SQL query against `health_metrics` using the extracted parameters
- Return results as formatted context

**Semantic path:**
- Embed the search query using Gemini embedding model
- Call the `match_document_chunks` Supabase function
- Return top matching chunks as context

**Hybrid path:**
- Do both, combine results

### Step 4.2: RAG Pipeline

Build `app/services/rag.py`:

1. `async def answer_question(user_id: UUID, question: str) -> dict`:
   - Call query router to classify and retrieve context
   - Build a prompt for Gemini:

```
You are a personal health assistant. Answer the user's question using ONLY the provided context from their health data. Be specific with numbers and dates. If the data doesn't contain enough information to answer, say so.

CONTEXT:
{retrieved_context}

QUESTION: {question}

Rules:
- Cite specific values and dates from the context
- If showing trends, mention the direction and magnitude of change
- Flag any values outside reference ranges
- Do not make medical diagnoses or treatment recommendations
- If asked about correlations, note that correlation ≠ causation
- Be concise but thorough
```

   - Call Gemini with this prompt
   - Return the answer along with source references (which chunks/metrics were used)

2. Store the question and answer in `chat_messages`

### Step 4.3: Chat API Endpoint

Build `app/routers/query.py`:

1. `POST /api/chat` — accepts `{"message": "string"}`, returns `{"response": "string", "sources": [...]}`
2. `GET /api/chat/history?limit=50` — returns recent chat messages
3. `DELETE /api/chat/history` — clear chat history

### Step 4.4: Chat UI

Build `/chat` page in the frontend:

1. **Chat window component** (`ChatWindow.tsx`):
   - Scrollable message list with user/assistant message bubbles
   - Input field at bottom with send button
   - Loading indicator while waiting for response
   - Auto-scroll to bottom on new messages

2. **Message bubble component** (`MessageBubble.tsx`):
   - Different styling for user vs assistant messages
   - For assistant messages: expandable "sources" section showing what data was used to generate the answer

3. **Suggested questions:** Show 3-4 starter questions when chat is empty:
   - "What were my latest blood test results?"
   - "How has my sleep been this week?"
   - "What's my average daily calorie intake?"
   - "Are any of my biomarkers outside the normal range?"

4. Load chat history on mount

### Phase 4 Verification

- [ ] Can ask a structured question ("what was my last LDL?") and get correct answer with actual values
- [ ] Can ask a semantic question ("what did the lab notes say?") and get relevant context
- [ ] Can ask a hybrid question ("is my vitamin D improving?") and get both numbers and context
- [ ] Chat history persists across sessions
- [ ] Sources are displayed for each answer
- [ ] Handles "I don't have enough data to answer" gracefully

---

## Phase 5: Visualizations & Dashboard

**Goal:** Time-series charts and trend visualizations for all health metrics.

**Duration:** ~1 week

### Step 5.1: Metrics Retrieval Endpoints

Add to `app/routers/metrics.py`:

1. `GET /api/metrics/timeseries?metric_name=weight_kg&start_date=...&end_date=...` — returns array of `{date, value}` for charting
2. `GET /api/metrics/summary` — returns latest values for key metrics (weight, resting HR, HRV, sleep, daily calories) for dashboard cards
3. `GET /api/metrics/biomarkers/latest` — returns all biomarkers from most recent blood test with reference ranges
4. `GET /api/metrics/correlate?metric_a=sleep_duration_hours&metric_b=energy_rating&start_date=...&end_date=...` — returns paired data points for correlation view

### Step 5.2: Dashboard UI

Build `/dashboard` page with these sections:

1. **Summary cards** (top row):
   - Current weight (with trend arrow vs last week)
   - Last night's sleep duration
   - Today's resting HR
   - Today's calories logged
   - Current HRV (with 7-day average)

2. **Biomarker table** (`BiomarkerTable.tsx`):
   - Table showing all biomarkers from latest blood test
   - Columns: Name, Value, Unit, Reference Range, Status (normal/high/low with color coding)
   - If multiple blood tests exist, show historical values in columns

3. **Trend charts** (`MetricChart.tsx` — reusable component):
   - Line chart for weight over time
   - Line chart for sleep duration over time
   - Line chart for resting HR and HRV over time (dual axis or separate charts)
   - Bar chart for daily calories with macro breakdown
   - Each chart should have date range selector (1 week, 1 month, 3 months, 6 months, 1 year)

4. **Correlation explorer:**
   - Two dropdowns to select any two metrics
   - Scatter plot showing the relationship
   - Display Pearson correlation coefficient

Use Recharts library for all charts:

```bash
cd frontend && npm install recharts
```

### Step 5.3: Navigation

Build `Navbar.tsx`:
- Links to: Dashboard, Chat, Upload, Daily Log
- Show currently logged-in user
- Logout button

### Phase 5 Verification

- [ ] Dashboard loads with summary cards showing latest values
- [ ] Biomarker table renders with correct reference range color coding
- [ ] Trend charts display correctly for all metric types
- [ ] Date range selectors work
- [ ] Correlation explorer shows scatter plot with any two metrics

---

## Phase 6: Polish & Auto-Sync

**Goal:** Automate data flow, improve UX, make production-ready.

**Duration:** ~2 weeks

### Step 6.1: Apple Health Auto-Sync

**USER ACTION REQUIRED:** Install "Health Auto Export" iOS app and configure it.

1. Add a `POST /api/ingest/apple-health/auto` endpoint that accepts JSON payloads from Health Auto Export app
2. The app can be configured to POST to a webhook URL on a schedule (hourly, daily)
3. Parse the incoming JSON format (different from the XML export — review Health Auto Export's documentation for their JSON schema)
4. Process and store as in Phase 2, with deduplication

### Step 6.2: Data Validation & Quality

1. Add input validation to all ingestion endpoints:
   - Reject values outside physically possible ranges (e.g., heart rate < 20 or > 250)
   - Validate dates aren't in the future
   - Check units match expected values for each metric

2. Add a `GET /api/metrics/data-quality` endpoint that returns:
   - Date range of available data per source
   - Gaps in daily data (e.g., "missing sleep data for Jan 5-7")
   - Record counts by source

### Step 6.3: Chat Improvements

1. **Conversation context:** Include last 5 messages as conversation history in the RAG prompt so follow-up questions work ("What about HDL?" after asking about LDL)
2. **Suggested follow-ups:** After each answer, have Gemini generate 2-3 relevant follow-up questions
3. **Streaming responses:** Use FastAPI's `StreamingResponse` with Gemini's streaming API for real-time text display in the chat UI

### Step 6.4: Mobile-Friendly UI

1. Make all pages responsive with Tailwind breakpoints
2. Daily logging form should be optimized for thumb-friendly inputs on mobile
3. Charts should be touch-scrollable

### Step 6.5: Deployment

**Frontend (Vercel):**
1. Connect frontend repo to Vercel
2. Set environment variable: `NEXT_PUBLIC_API_URL` = deployed backend URL
3. Deploy

**Backend (Railway):**
1. Create Railway project
2. Set all environment variables from the credentials table above
3. Deploy from Dockerfile
4. Note the deployed URL and update the frontend env var

**USER ACTION REQUIRED:** Update CORS allowed origins in `main.py` with the actual Vercel deployment URL.

### Phase 6 Verification

- [ ] Health Auto Export app sends data to the API successfully
- [ ] Deduplication prevents duplicate records from auto-sync
- [ ] Chat handles follow-up questions correctly
- [ ] UI works well on mobile
- [ ] Both frontend and backend deployed and accessible
- [ ] Data flows from all sources without manual intervention

---

## Future Enhancements (Post-MVP)

These are not part of the current implementation plan but are documented for later consideration:

1. **Periodic health summaries** — Scheduled LLM-generated weekly/monthly reports emailed to the user
2. **Alerting** — "Your resting HR has trended up 8% over the last 2 weeks"
3. **Doctor visit prep** — Generate a summary of changes since last checkup
4. **Additional integrations** — Oura Ring, Whoop, Garmin, MyFitnessPal
5. **Goal tracking** — Set targets (weight, sleep hours, daily steps) and track progress
6. **Export** — Generate PDF health reports to share with healthcare providers

---

## Key Implementation Notes for the Coding Agent

1. **Always use `async` for database operations and API calls.** FastAPI is async-first. Use `httpx` for HTTP calls, not `requests`.

2. **Environment variables are mandatory.** Never hardcode API keys or URLs. Always read from `Settings` via `config.py`.

3. **Error handling pattern:** Every endpoint should catch exceptions, log them, and return meaningful error responses. Never let a 500 error reach the user without context.

4. **Supabase client usage:** Use the `service_role_key` client for backend operations (bypasses RLS). Use the `anon_key` client when you need RLS enforcement.

5. **Embedding dimension:** Gemini `text-embedding-004` outputs 768-dimensional vectors. The `document_chunks.embedding` column is `vector(768)`. These must match.

6. **Chunking strategy:** Split by sentence boundaries, not character count. Aim for ~500 characters per chunk with ~50 character overlap. Each chunk should be self-contained enough to be useful on its own.

7. **Blood test PDF parsing is the hardest part.** Different labs format PDFs differently. The LLM extraction prompt needs to be robust. Test with multiple PDFs from different labs and iterate on the prompt.

8. **Apple Health XML files can be enormous.** Always use streaming/iterative XML parsing (`iterparse`). Never load the entire file into memory.

9. **Rate limiting:** Gemini API has rate limits. Add retry logic with exponential backoff for embedding generation (which may involve many sequential calls for large documents).

10. **Frontend state management:** For this app's complexity, React's built-in `useState` and `useContext` are sufficient. No need for Redux or Zustand.
