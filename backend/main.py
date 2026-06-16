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
    get_alerts,
    get_assessments,
    get_dashboard_summary,
    get_filters,
    get_unevaluated_alerts,
    init_db,
    save_assessment,
    save_company_profile,
)
from .report_generator import generate_weekly_report


load_dotenv()

app = FastAPI(title="Agente de Monitoreo Regulatorio Personalizado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompanyProfilePayload(BaseModel):
    company_name: str
    industry: str = ""
    countries: list[str] | str = []
    product_categories: list[str] | str = []
    keywords: list[str] | str = []
    excluded_topics: list[str] | str = []
    internal_areas: list[str] | str = []
    notes: str = ""


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


@app.post("/company-profile")
def company_profile(payload: CompanyProfilePayload) -> dict[str, Any]:
    return save_company_profile(payload.dict())


@app.get("/company-profile")
def active_company_profile() -> dict[str, Any]:
    profile = get_active_company_profile()
    return profile or {}


@app.post("/evaluate-alerts")
def evaluate_alerts(payload: EvaluatePayload) -> dict[str, Any]:
    profile = get_active_company_profile()
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
) -> dict[str, Any]:
    profile = get_active_company_profile()
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
def dashboard_summary() -> dict[str, int]:
    profile = get_active_company_profile()
    return get_dashboard_summary(profile["id"] if profile else None)


@app.get("/generate-report", response_class=PlainTextResponse)
def generate_report() -> str:
    profile = get_active_company_profile()
    assessments_list = get_assessments({"company_id": profile["id"] if profile else None})
    summary = get_dashboard_summary(profile["id"] if profile else None)
    return generate_weekly_report(profile, summary, assessments_list)


app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
