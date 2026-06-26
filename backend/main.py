import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_agent import evaluate_alert
from .csv_loader import load_alerts_from_csv_bytes
from .db import (
    BASE_DIR,
    get_active_company_profile,
    get_agent_run,
    get_agent_runs,
    get_all_companies,
    get_alerts,
    get_assessments,
    get_dashboard_summary,
    get_filters,
    get_unevaluated_alerts,
    init_db,
    save_assessment,
    save_company_profile,
    update_last_agent_run,
)
from .report_generator import generate_weekly_report


load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Agente de Monitoreo Regulatorio Personalizado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompanyProfilePayload(BaseModel):
    id: int | None = None
    company_name: str
    industry: list[str] | str = []
    countries: list[str] | str = []
    product_categories: list[str] | str = []
    keywords: list[str] | str = []
    excluded_topics: list[str] | str = []
    internal_areas: list[str] | str = []
    notes: str = ""
    company_description: str = ""
    email_recipients: list[str] | str = []
    days_back: int = 7
    alert_sources: list[str] | str = []
    agent_date_from: str = ""
    agent_date_to: str = ""
    agent_max_eval: int = 100


class EvaluatePayload(BaseModel):
    country: str | None = None
    institution: str | None = None
    category: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 100


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Subí un archivo CSV.")
    content = await file.read()
    try:
        return load_alerts_from_csv_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/alerts")
def alerts(
    country: str | None = None,
    institution: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    items = get_alerts(
        {
            "country": country,
            "institution": institution,
            "category": category,
            "date_from": date_from,
            "date_to": date_to,
        },
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@app.get("/filters")
def filters() -> dict[str, list[str]]:
    return get_filters()


@app.get("/companies")
def companies() -> dict[str, Any]:
    items = get_all_companies()
    return {"items": items}


@app.post("/company-profile")
def company_profile(payload: CompanyProfilePayload) -> dict[str, Any]:
    return save_company_profile(payload.dict())


@app.get("/company-profile")
def active_company_profile(company_id: int | None = None) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    return profile or {}


@app.post("/evaluate-alerts")
def evaluate_alerts(
    payload: EvaluatePayload,
    company_id: int | None = Query(None),
) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Primero configurá un perfil de empresa.")

    pending_alerts = get_unevaluated_alerts(profile["id"], payload.dict(exclude={"limit"}))
    alerts_to_evaluate = pending_alerts[: payload.limit]

    processed = 0
    for alert in alerts_to_evaluate:
        assessment = evaluate_alert(alert, profile)
        save_assessment(profile["id"], alert["id"], assessment)
        processed += 1

    return {
        "processed": processed,
        "pending_matched": max(0, len(pending_alerts) - processed),
        "company_id": profile["id"],
    }


@app.get("/assessments")
def assessments(
    priority: str | None = None,
    country: str | None = None,
    institution: str | None = None,
    requires_human_review: str | None = None,
    company_id: int | None = Query(None),
) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    items = get_assessments(
        {
            "company_id": profile["id"] if profile else None,
            "priority": priority,
            "country": country,
            "institution": institution,
            "requires_human_review": requires_human_review,
        }
    )
    return {"items": items, "count": len(items)}


@app.get("/dashboard-summary")
def dashboard_summary(company_id: int | None = Query(None)) -> dict[str, int]:
    profile = get_active_company_profile(company_id)
    return get_dashboard_summary(profile["id"] if profile else None)


@app.get("/generate-report", response_class=PlainTextResponse)
def generate_report(company_id: int | None = Query(None)) -> str:
    profile = get_active_company_profile(company_id)
    assessments_list = get_assessments({"company_id": profile["id"] if profile else None})
    summary = get_dashboard_summary(profile["id"] if profile else None)
    return generate_weekly_report(profile, summary, assessments_list)


@app.get("/onboarding-status")
def onboarding_status(company_id: int | None = Query(None)) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    summary = get_dashboard_summary(profile["id"] if profile else None)
    return {
        "has_profile": profile is not None,
        "alert_count": summary.get("total_alerts", 0),
        "assessed_count": summary.get("evaluated_alerts", 0),
    }


@app.post("/load-demo-data")
def load_demo_data() -> dict[str, Any]:
    demo_path = Path(BASE_DIR) / "data" / "demo_alerts.csv"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de demo no encontrado.")
    content = demo_path.read_bytes()
    try:
        return load_alerts_from_csv_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/alert-sources")
def alert_sources(refresh: bool = Query(False)) -> dict[str, Any]:
    try:
        from .supabase_loader import get_available_sources
        sources = get_available_sources(refresh=refresh)
    except Exception:
        # Fallback: distinct source_type values already in local SQLite
        filters = get_filters()
        sources = []
    if not sources:
        sources = get_filters().get("institution", [])
    return {"sources": sources}


@app.post("/run-agent")
def run_agent(company_id: int | None = Query(None)) -> dict[str, Any]:
    from .weekly_agent import run_weekly_agent
    try:
        results = run_weekly_agent(company_id)
        return {"results": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/agent-runs")
def agent_runs(company_id: int | None = Query(None)) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    if not profile:
        return {"items": []}
    return {"items": get_agent_runs(profile["id"])}


@app.get("/agent-runs/{run_id}/report", response_class=PlainTextResponse)
def agent_run_report(run_id: int) -> str:
    run = get_agent_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Corrida no encontrada.")
    return run.get("report_markdown") or ""


@app.get("/agent-status")
def agent_status(company_id: int | None = Query(None)) -> dict[str, Any]:
    profile = get_active_company_profile(company_id)
    if not profile:
        return {"last_agent_run": None, "has_profile": False}
    return {
        "last_agent_run": profile.get("last_agent_run"),
        "has_profile": True,
        "email_recipients": profile.get("email_recipients", []),
        "days_back": profile.get("days_back", 7),
        "alert_sources": profile.get("alert_sources", []),
        "agent_date_from": profile.get("agent_date_from", ""),
        "agent_date_to": profile.get("agent_date_to", ""),
        "agent_max_eval": profile.get("agent_max_eval", 100),
    }


@app.post("/agent-preview")
def agent_preview(company_id: int | None = Query(None)) -> dict[str, Any]:
    """Dry-run: estima cuántas alertas evaluaría el agente (y cuántas llamadas a
    OpenAI haría) SIN insertar nada ni gastar créditos."""
    profile = get_active_company_profile(company_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Primero configurá un perfil de empresa.")

    days_back = int(profile.get("days_back") or 7)
    manual_from = (profile.get("agent_date_from") or "").strip()
    manual_to = (profile.get("agent_date_to") or "").strip()
    window = {"date_from": manual_from, "date_to": manual_to} if manual_from else {}

    try:
        from .supabase_loader import preview_agent_run
        preview = preview_agent_run(
            profile,
            days_back=days_back,
            date_from=manual_from or None,
            date_to=manual_to or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo previsualizar contra Supabase: {exc}") from exc

    pending_local = len(get_unevaluated_alerts(profile["id"], window))
    cap = int(profile.get("agent_max_eval") or 100)
    candidates = pending_local + preview["would_evaluate_new"]

    preview["pending_local"] = pending_local
    preview["candidates_total"] = candidates
    preview["cap"] = cap
    preview["estimated_ai_calls"] = min(candidates, cap)
    preview["ai_enabled"] = bool(os.getenv("OPENAI_API_KEY"))
    return preview


app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
