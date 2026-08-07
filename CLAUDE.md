# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agente de Monitoreo Regulatorio Personalizado** — a personal MVP for regulatory alert monitoring targeting LATAM companies in healthcare, cosmetics, OTC medicines, and regulated consumer products. It ingests regulatory alerts from Supabase, evaluates their relevance against a company profile using an LLM with tool calling, and generates weekly reports — both markdown and a branded HTML email (fixed **Oversia** styling) with LLM-written narrative.

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLite
- **Frontend**: Vanilla HTML/CSS/JS (no build step)
- **Key dependencies**: OpenAI SDK, python-dotenv, Jinja2 (branded email), beautifulsoup4 + httpx (tool calling), supabase, resend

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

Additional optional env vars:
```env
OPENAI_ENABLE_TOOLS=true          # tool calling in evaluate_alert (default true); set false for single-shot
RESEND_API_KEY=your_key_here      # branded email delivery
RESEND_FROM_EMAIL=alertas@...     # sender address
SUPABASE_URL / SUPABASE_KEY       # weekly agent fetches alerts from Supabase
APP_API_KEY=your_key_here         # optional API auth; when set, all API routes require header X-API-Key
ALLOWED_ORIGINS=https://...       # optional CORS allow-list (comma-separated); defaults to localhost only
```

### Security

- **CORS**: restricted to `ALLOWED_ORIGINS` (comma-separated) or, by default, `http://127.0.0.1:8000` / `http://localhost:8000`. `allow_credentials=False` — never combine `*` origins with credentials. Configured in `main.py`.
- **API auth (optional)**: if `APP_API_KEY` is set, a global FastAPI dependency (`require_api_key`) requires the `X-API-Key` header on every API route; the `StaticFiles` mount at `/` is exempt so the SPA still loads. If `APP_API_KEY` is unset, auth is disabled (local-dev default). The frontend attaches the key from `localStorage["app_api_key"]` when present (`api()` in `app.js`, `apiFetch()` in `onboarding.js`).
- **SSRF / tool safety**: `fetch_source_text` only downloads the alert's own `source_url` (the URL the model passes is ignored); `_url_is_safe()` blocks loopback/private/link-local/reserved IPs (incl. cloud metadata `169.254.169.254`), redirects are validated per-hop (max 3), and downloads are capped at 2 MB. Alert/source text is passed to the LLM as untrusted data (system prompt tells the model to ignore instructions embedded in it).

Without `OPENAI_API_KEY`, the system falls back to mock evaluation (keyword/category/country scoring) and the report is generated without LLM narrative.

## Architecture

### Data Flow

1. **Alert ingestion** → the weekly agent fetches alerts from Supabase via `supabase_loader.py` → `regulatory_alerts` table
2. **Company Profile** → user configures countries, categories, keywords, excluded topics → `company_profiles` table
3. **Evaluation** → `ai_agent.py` evaluates each unevaluated alert via OpenAI (with tool calling) or mock → `alert_assessments` table
4. **Synthesis** → `report_synth.py` asks the LLM to write narrative prose (executive summary, cross-cutting points, per-country narrative)
5. **Report** → `report_generator.py` builds the markdown and `report_html.py` renders the branded HTML (fixed Oversia layout + LLM prose)
6. **Delivery** → `email_sender.py` sends the branded HTML via Resend; the whole run is orchestrated by `weekly_agent.py`

**Design principle:** the LLM writes *prose*; layout, branding, and per-country grouping are guaranteed by deterministic templates. The model never controls the branding or structure.

### Key Modules

**backend/db.py** — SQLite schema and helpers
- Three tables: `regulatory_alerts`, `company_profiles`, `alert_assessments`
- Lists stored as JSON strings; decoded by `decode_json_list()`, always returns lists
- Rows converted to dicts via `row_to_dict()` for API responses
- Active profile = latest `company_profiles` row by `id DESC` (no explicit active flag)

**backend/ai_agent.py** — Alert evaluation
- `evaluate_alert(alert, company_profile)` routes to OpenAI or `mock_evaluate_alert()`
- **OpenAI flow**: sends company profile + alert as JSON; expects strict JSON response with assessment fields
- **Tool calling**: when `OPENAI_ENABLE_TOOLS` is truthy (default), the model can call two tools (loop capped at `_MAX_TOOL_ITERS = 3`):
  - `fetch_source_text(url)` — downloads and strips the alert's own `source_url` only (httpx + BeautifulSoup); the model-supplied `url` is ignored. SSRF-guarded via `_url_is_safe()` (blocks private/loopback/link-local/metadata IPs), per-hop redirect validation (max 3), 2 MB cap. Returns an error string on failure so it never breaks evaluation
  - `search_company_history(query)` — reuses `db.get_assessments` to surface the company's prior assessments for consistency
  - The model is instructed to use tools only when the alert isn't enough to decide confidently
- **Tool observability**: `_dispatch_tool` prints each call/result to stdout (`[ai_agent] 🔧 tool call/result …`, visible in `uvicorn.log`). Each evaluation also persists a `tools_used` trace on the assessment: a list of `{tool, args, result_chars}`. Empty `[]` means no tool was called (or evaluation ran via mock). Only populated on future evaluations — pre-existing rows have it empty.
- **Mock flow**: scores by country match (+4), category/keyword match (+2–5), excluded topic penalty (−5); word-boundary regex prevents substring false positives
- Returns normalized dict: `is_relevant`, `priority` (alta/media/baja/no_relevante), `impact_score` (0–15), `impacted_areas`, `impact_summary`, `recommended_action`, `risk_if_ignored`, `confidence` (alta/media/baja), `requires_human_review`, `agent_reasoning`, `tools_used`
- Low confidence or borderline scores set `requires_human_review = True`
- Any exception (including tool-calling errors) falls back to `mock_evaluate_alert` with `requires_human_review = True`

**backend/report_synth.py** — LLM report narrative
- `synthesize_report(profile, summary, assessments)` returns `{executive_summary, cross_cutting, country_narratives}`
- Sends only compact fields of **relevant** assessments (no `full_text`) to limit tokens; `temperature≈0.3`
- Returns `{}` when `OPENAI_API_KEY` is missing or the call fails — the report still renders with deterministic sections

**backend/report_html.py** — Branded HTML render (fixed Oversia styling)
- `render_report_html(profile, summary, assessments, narrative)` renders a Jinja2 template (autoescaped) with a fixed Oversia look (navy + accent blue, `<style>` inline for email compatibility)
- Layout: header (Oversia wordmark + report code `OVS-{year}-W{week}` + week range), cover, KPI row, executive-summary box, per-country cards with a priority-colored left bar, human-review section, disclaimer footer
- Computes the ISO week/code/range and per-priority counts from `datetime.utcnow()` + the assessments; only `company_name` is read from the profile (branding is no longer per-client); country grouping reuses `report_generator.group_by_country`

**backend/email_sender.py** — Email delivery
- `send_report_email(to_emails, company_profile, summary, assessments, narrative)` builds the HTML via `report_html.render_report_html` and sends through Resend
- Returns `False` (no send) when `RESEND_API_KEY` or recipients are missing

**backend/weekly_agent.py** — Orchestrator
- `run_weekly_agent(company_id=None)` per company: fetch from Supabase → evaluate pending (capped by `agent_max_eval`) → `synthesize_report` → build markdown + send branded email → persist the run in `agent_runs`
- Manual date range → report over the whole window; relative `days_back` → delta report (only newly evaluated alerts)
- Re-running with no new alerts is normal: `inserted=0` (dedup por `source_url`/`id` en `insert_alert`) y `evaluated=0` (`get_unevaluated_alerts` excluye lo ya evaluado, para no pagar dos veces la misma alerta). En modo rango el informe igual sale completo; en modo relativo el delta queda vacío.
- La corrida persiste `report_alert_ids` (lo que el informe cubre) además de `alert_ids` (lo evaluado); el visualizador usa el primero.

**backend/supabase_loader.py** — Remote alert source
- `fetch_alerts_for_company()` queries `alertas_alerta` filtered by profile countries/keywords/sources; pre-filters with the mock (impact_score < 2 → stored as `no_relevante`, skips AI)
- `preview_agent_run()` is a dry-run estimate (no inserts, no OpenAI calls)

**backend/report_generator.py** — Markdown report
- `generate_weekly_report(profile, summary, assessments, narrative=None)` — when `narrative` is provided, injects the LLM executive summary, cross-cutting points, and per-country narrative into the markdown
- `group_by_country(assessments)` — shared helper (used by markdown and HTML) that returns countries ordered by highest priority, alerts sorted by priority then impact_score
- Markdown is the artifact stored in `agent_runs.report_markdown` and shown/downloaded in the UI

### Database Schema

```
regulatory_alerts        — title, description, source_type, category, country, institution,
                           source_url, presentation_date, full_text, created_at
                           Index: source_url; (country, institution, category, presentation_date)

company_profiles         — company_name, industry, countries (JSON), product_categories (JSON),
                           keywords, excluded_topics, internal_areas (JSON), notes,
                           company_description, email_recipients (JSON), days_back,
                           alert_sources (JSON), last_agent_run, agent_date_from/to, agent_max_eval,
                           report_logo_url, report_primary_color, report_header, report_footer,
                           created_at

alert_assessments        — company_id FK, alert_id FK (UNIQUE pair),
                           is_relevant, priority, impact_score, impacted_areas (JSON),
                           impact_summary, recommended_action, risk_if_ignored,
                           confidence, requires_human_review, agent_reasoning,
                           tools_used (JSON list of {tool, args, result_chars}), created_at
                           Index: (company_id, priority, requires_human_review)

agent_runs               — company_id FK, started_at, date_from, fetched, inserted,
                           evaluated, alert_ids (JSON), report_alert_ids (JSON),
                           email_sent, report_markdown,
                           deleted_at (NULL = visible; baja lógica del historial)
                           Index: (company_id, started_at)

  alert_ids        = alertas evaluadas EN esa corrida (0 si no había nada nuevo).
  report_alert_ids = alertas que el informe CUBRE. En modo relativo coincide con
                     alert_ids; en modo rango incluye las ya evaluadas antes dentro
                     de la ventana. El visualizador re-renderiza a partir de esta
                     lista — usar alert_ids hacía que un informe de rango sin alertas
                     nuevas se viera vacío. Filas previas caen a alert_ids.
```

New columns are added via idempotent `ALTER TABLE` migrations in `init_db()`. Branding columns (`report_*`) are plain strings, not JSON lists.

DB auto-created at `data/regulatory_mvp.db` on first run.

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/alerts` | List alerts (filters: country, institution, category, date range) |
| `GET` | `/filters` | Distinct values for filter dropdowns |
| `POST` | `/company-profile` | Save/update company profile |
| `GET` | `/company-profile` | Fetch active profile |
| `POST` | `/evaluate-alerts` | Evaluate pending alerts (optional filters + limit) |
| `GET` | `/assessments` | List assessments (filters: priority, country, requires_human_review) |
| `GET` | `/dashboard-summary` | Counts: total/evaluated/relevant/priority breakdown/review needed |
| `GET` | `/generate-report` | Weekly markdown report (plain text response) |
| `GET` | `/report-preview.html` | Branded HTML preview of the report (`?synth=true` runs the LLM narrative; default skips it to save credits) |
| `POST` | `/run-agent` | Run the full weekly agent (fetch → evaluate → synth → email → persist) |
| `POST` | `/agent-preview` | Dry-run estimate of alerts/AI calls without inserting or spending credits |
| `GET` | `/agent-runs`, `/agent-runs/{id}/report`, `/agent-status` | Run history, stored markdown, and last-run status |
| `DELETE` | `/agent-runs/{id}` | Baja lógica de una corrida: setea `deleted_at`, la oculta del historial y hace que los endpoints de informe devuelvan 404. La fila y el informe se conservan |

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
- **Report branding vs. content**: branding/layout is deterministic and fixed (Oversia styling in `report_html.py`'s Jinja2 template); only the *prose* comes from the LLM (`report_synth.py`). Never let the model emit layout or logos. The `report_*` columns still exist in `company_profiles` but no longer affect the rendered report.
