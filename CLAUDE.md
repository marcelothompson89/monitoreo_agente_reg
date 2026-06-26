# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agente de Monitoreo Regulatorio Personalizado** — a personal MVP for regulatory alert monitoring targeting LATAM companies in healthcare, cosmetics, OTC medicines, and regulated consumer products. It ingests regulatory alerts via CSV, evaluates their relevance against a company profile, and generates weekly markdown reports.

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLite
- **Frontend**: Vanilla HTML/CSS/JS (no build step)
- **Key dependencies**: pandas, OpenAI SDK, python-dotenv

## Commands

### Setup
```powershell
pip install -r requirements.txt
```

### Run Development Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
# Or:
.\scripts\run_server.ps1
```

App runs at `http://127.0.0.1:8000`. Static files from `frontend/` are mounted at root.

### Environment
`.env` controls OpenAI integration:
```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
```

Without `OPENAI_API_KEY`, the system falls back to mock evaluation (keyword/category/country scoring).

## Architecture

### Data Flow

1. **CSV Upload** → `csv_loader.py` normalizes and deduplicates alerts → `regulatory_alerts` table
2. **Company Profile** → user configures countries, categories, keywords, excluded topics → `company_profiles` table
3. **Evaluation** → `ai_agent.py` evaluates each unevaluated alert via OpenAI or mock → `alert_assessments` table
4. **Report** → `report_generator.py` aggregates assessments into a prioritized weekly markdown

### Key Modules

**backend/db.py** — SQLite schema and helpers
- Three tables: `regulatory_alerts`, `company_profiles`, `alert_assessments`
- Lists stored as JSON strings; decoded by `decode_json_list()`, always returns lists
- Rows converted to dicts via `row_to_dict()` for API responses
- Active profile = latest `company_profiles` row by `id DESC` (no explicit active flag)

**backend/ai_agent.py** — Alert evaluation
- `evaluate_alert(alert, company_profile)` routes to OpenAI or `mock_evaluate_alert()`
- **OpenAI flow**: sends company profile + alert as JSON; expects strict JSON response with assessment fields
- **Mock flow**: scores by country match (+4), category/keyword match (+2–5), excluded topic penalty (−5); word-boundary regex prevents substring false positives
- Returns normalized dict: `is_relevant`, `priority` (alta/media/baja/no_relevante), `impact_score` (0–15), `impacted_areas`, `impact_summary`, `recommended_action`, `risk_if_ignored`, `confidence` (alta/media/baja), `requires_human_review`, `agent_reasoning`
- Low confidence or borderline scores set `requires_human_review = True`

**backend/csv_loader.py** — CSV ingestion
- Requires at minimum `title` + (`id` or `source_url`)
- Generates stable 24-char hash from `(source_url, title, presentation_date)` when `id` is absent
- Deduplicates by `id` first, then `source_url`; skipped rows counted in upload summary
- Falls back to `description` when `full_text` column is missing

**backend/report_generator.py** — Markdown report
- Groups assessments by priority; outputs executive summary, per-priority sections, top-12 actions, top-12 human-review topics

### Database Schema

```
regulatory_alerts        — title, description, source_type, category, country, institution,
                           source_url, presentation_date, full_text, created_at
                           Index: source_url; (country, institution, category, presentation_date)

company_profiles         — company_name, industry, countries (JSON), product_categories (JSON),
                           keywords, excluded_topics, internal_areas (JSON), notes, created_at

alert_assessments        — company_id FK, alert_id FK (UNIQUE pair),
                           is_relevant, priority, impact_score, impacted_areas (JSON),
                           impact_summary, recommended_action, risk_if_ignored,
                           confidence, requires_human_review, agent_reasoning, created_at
                           Index: (company_id, priority, requires_human_review)
```

DB auto-created at `data/regulatory_mvp.db` on first run.

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload-csv` | Ingest CSV file |
| `GET` | `/alerts` | List alerts (filters: country, institution, category, date range) |
| `GET` | `/filters` | Distinct values for filter dropdowns |
| `POST` | `/company-profile` | Save/update company profile |
| `GET` | `/company-profile` | Fetch active profile |
| `POST` | `/evaluate-alerts` | Evaluate pending alerts (optional filters + limit) |
| `GET` | `/assessments` | List assessments (filters: priority, country, requires_human_review) |
| `GET` | `/dashboard-summary` | Counts: total/evaluated/relevant/priority breakdown/review needed |
| `GET` | `/generate-report` | Weekly markdown report (plain text response) |

CORS enabled for all origins.

### Frontend

Single-page vanilla JS (`frontend/app.js`). Key patterns:
- `api()` helper handles JSON/text responses and extracts `.detail` from error payloads
- Functions: `loadFilters()`, `loadProfile()`, `loadSummary()`, `loadAssessments()`, `loadReport()`
- Report textarea includes a markdown download button

## Key Conventions

- **Priority values**: always `"alta"`, `"media"`, `"baja"`, or `"no_relevante"`
- **Confidence values**: always `"alta"`, `"media"`, or `"baja"`
- **Impact score**: integer 0–15, clamped during normalization in `ai_agent.py`
- **Timestamps**: ISO 8601 UTC via `now_iso()`
- **JSON lists in SQLite**: always encode on write, always decode with `decode_json_list()` on read
