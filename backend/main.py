import os
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_agent import evaluate_alert
from .db import (
    BASE_DIR,
    get_active_company_profile,
    get_agent_run,
    get_agent_runs,
    soft_delete_agent_run,
    get_all_companies,
    get_alerts,
    get_alerts_by_ids,
    get_assessments,
    get_assessments_by_alert_ids,
    get_dashboard_summary,
    get_filters,
    get_unevaluated_alerts,
    init_db,
    save_assessment,
    save_company_profile,
    summarize_assessments,
    update_last_agent_run,
)
from .report_generator import generate_weekly_report
from .report_html import render_report_html
from .report_synth import synthesize_report


load_dotenv(BASE_DIR / ".env")

# Auth mínima opcional: si APP_API_KEY está seteada en el entorno, todos los
# endpoints de la API exigen el header X-API-Key con ese valor. Si NO está seteada,
# la auth queda deshabilitada (modo desarrollo local, sin fricción).
_APP_API_KEY = os.getenv("APP_API_KEY", "").strip()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not _APP_API_KEY:
        return  # auth deshabilitada
    if x_api_key != _APP_API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida o ausente.")


# CORS: por defecto solo el propio origen local. Configurable con ALLOWED_ORIGINS
# (lista separada por comas) para producción. Sin credenciales: no usamos cookies,
# y "*" + credentials es justamente la combinación insegura que evitamos.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

# La dependencia global aplica a todas las rutas de la API, pero NO al StaticFiles
# montado en "/" (las sub-apps montadas no heredan dependencies), así que el frontend
# se sigue sirviendo sin key.
app = FastAPI(
    title="Agente de Monitoreo Regulatorio Personalizado",
    dependencies=[Depends(require_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
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
    report_logo_url: str = ""
    report_primary_color: str = "#176b62"
    report_header: str = ""
    report_footer: str = ""


class EvaluatePayload(BaseModel):
    country: str | None = None
    institution: str | None = None
    category: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 100
    alert_ids: list[str] | None = None  # si viene, re-evalúa esas alertas puntuales (pisa la evaluación previa)


@app.on_event("startup")
def startup() -> None:
    init_db()


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
    # exclude_unset: al actualizar un perfil existente, solo se persisten los campos
    # que el cliente envió, así una pantalla que omite (p. ej.) alert_sources no los
    # borra. En un alta (sin id) igual se aplican los defaults en save_company_profile.
    data = payload.dict(exclude_unset=True)
    if not payload.id:
        # Alta: garantizar que el INSERT reciba todos los campos con sus defaults.
        data = {**payload.dict(), **data}
    return save_company_profile(data)


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

    if payload.alert_ids:
        # Re-evaluación puntual: pisa la evaluación existente de esas alertas (para
        # comparar cambios de prompt/modelo sin esperar a que haya alertas nuevas).
        alerts_to_evaluate = get_alerts_by_ids(payload.alert_ids)[: payload.limit]
        force = True
        pending_total = len(alerts_to_evaluate)
    else:
        pending_alerts = get_unevaluated_alerts(profile["id"], payload.dict(exclude={"limit", "alert_ids"}))
        alerts_to_evaluate = pending_alerts[: payload.limit]
        force = False
        pending_total = len(pending_alerts)

    processed = 0
    for alert in alerts_to_evaluate:
        assessment = evaluate_alert(alert, profile)
        save_assessment(profile["id"], alert["id"], assessment, force=force)
        processed += 1

    return {
        "processed": processed,
        "pending_matched": max(0, pending_total - processed),
        "company_id": profile["id"],
    }


@app.get("/assessments")
def assessments(
    priority: str | None = None,
    country: str | None = None,
    institution: str | None = None,
    requires_human_review: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
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
            "date_from": date_from,
            "date_to": date_to,
        }
    )
    return {"items": items, "count": len(items)}


@app.get("/dashboard-summary")
def dashboard_summary(
    company_id: int | None = Query(None),
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, int]:
    profile = get_active_company_profile(company_id)
    return get_dashboard_summary(profile["id"] if profile else None, date_from, date_to)


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


@app.get("/report-preview.html", response_class=HTMLResponse)
def report_preview(
    company_id: int | None = Query(None),
    synth: bool = Query(False),
) -> str:
    """Previsualiza el informe branded HTML de la empresa activa.

    Por defecto NO llama al LLM (synth=false) para no gastar créditos; con
    synth=true genera la narrativa real con síntesis."""
    profile = get_active_company_profile(company_id)
    assessments_list = get_assessments({"company_id": profile["id"] if profile else None})
    summary = get_dashboard_summary(profile["id"] if profile else None)
    narrative = synthesize_report(profile, summary, assessments_list) if synth else {}
    return render_report_html(profile, summary, assessments_list, narrative)


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


@app.delete("/agent-runs/{run_id}")
def delete_agent_run(run_id: int) -> dict[str, Any]:
    """Baja lógica: oculta la corrida del historial sin borrar el informe."""
    if not soft_delete_agent_run(run_id):
        raise HTTPException(status_code=404, detail="Corrida no encontrada.")
    return {"ok": True, "id": run_id}


@app.get("/agent-runs/{run_id}/report", response_class=PlainTextResponse)
def agent_run_report(run_id: int) -> str:
    run = get_agent_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Corrida no encontrada.")
    return run.get("report_markdown") or ""


@app.get("/agent-runs/{run_id}/report.html", response_class=HTMLResponse)
def agent_run_report_html(run_id: int) -> str:
    """HTML branded del informe de esa corrida.

    Se re-renderiza siempre con la plantilla actual (formato Oversia) a partir de
    las alertas evaluadas en la corrida y la narrativa LLM guardada, de modo que el
    historial completo se ve con el formato vigente. El `report_html` congelado que
    se envió por email queda como registro de esa entrega, pero no se usa acá."""
    run = get_agent_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Corrida no encontrada.")

    profile = get_active_company_profile(run.get("company_id"))
    assessments_list = get_assessments_by_alert_ids(run["company_id"], run.get("report_alert_ids") or [])
    summary = summarize_assessments(assessments_list)
    return render_report_html(profile, summary, assessments_list, run.get("narrative") or {})


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
    if manual_from:
        window = {"date_from": manual_from, "date_to": manual_to}
    else:
        # Misma ventana relativa que aplica run_weekly_agent, para que el conteo de
        # pendientes locales de la preview coincida con lo que realmente se evaluaría.
        relative_floor = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        window = {"date_from": relative_floor}

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
