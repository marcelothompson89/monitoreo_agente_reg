from datetime import datetime, timedelta
from typing import Any

from .ai_agent import evaluate_alert
from .db import (
    decode_json_list,
    get_active_company_profile,
    get_all_companies,
    get_assessments,
    get_assessments_by_alert_ids,
    get_unevaluated_alerts,
    now_iso,
    save_agent_run,
    save_assessment,
    summarize_assessments,
    update_last_agent_run,
)
from .email_sender import send_report_email
from .report_generator import generate_weekly_report
from .report_html import render_report_html
from .report_synth import synthesize_report
from .supabase_loader import fetch_alerts_for_company


def run_weekly_agent(
    company_id: int | None = None,
    max_eval_per_run: int = 100,
) -> list[dict[str, Any]]:
    if company_id is not None:
        companies = [{"id": company_id}]
    else:
        companies = get_all_companies()

    results = []

    for company_stub in companies:
        cid = company_stub["id"]
        result: dict[str, Any] = {"company_id": cid, "error": None}

        try:
            profile = get_active_company_profile(cid)
            if not profile:
                result["error"] = "Perfil no encontrado"
                results.append(result)
                continue

            result["company_name"] = profile.get("company_name", "")
            started_at = now_iso()

            # Ventana de búsqueda: rango manual (agent_date_from/_to) o relativo (days_back).
            days_back = int(profile.get("days_back") or 7)
            manual_from = (profile.get("agent_date_from") or "").strip()
            manual_to = (profile.get("agent_date_to") or "").strip()
            use_range = bool(manual_from)
            if use_range:
                date_window = {"date_from": manual_from, "date_to": manual_to}
            else:
                # Modo relativo: acotar la evaluación a los últimos `days_back` días para
                # no evaluar (ni pagar) alertas viejas pendientes fuera de la ventana.
                relative_floor = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                date_window = {"date_from": relative_floor}

            # Step 1: fetch from Supabase
            date_from = None
            try:
                fetch_result = fetch_alerts_for_company(
                    profile,
                    days_back=days_back,
                    date_from=manual_from or None,
                    date_to=manual_to or None,
                )
                result["fetched"] = fetch_result["fetched"]
                result["inserted"] = fetch_result["inserted"]
                date_from = fetch_result.get("date_from")
            except Exception as exc:
                result["fetched"] = 0
                result["inserted"] = 0
                result["supabase_error"] = str(exc)

            # Step 2: evaluate pending alerts (Capa 3 — AI), restringidas a la ventana.
            # El tope por corrida sale del perfil (agent_max_eval) para controlar el
            # gasto de créditos; si no está configurado, cae al default del parámetro.
            max_eval = int(profile.get("agent_max_eval") or max_eval_per_run)
            pending = get_unevaluated_alerts(cid, date_window)
            to_eval = pending[:max_eval]
            evaluated_ids = []
            for alert in to_eval:
                assessment = evaluate_alert(alert, profile)
                save_assessment(cid, alert["id"], assessment)
                evaluated_ids.append(alert["id"])
            result["evaluated"] = len(evaluated_ids)

            # Step 3: generar informe.
            #  - Rango manual: informe sobre TODO el período (todas las alertas del rango,
            #    nuevas y ya evaluadas en corridas previas).
            #  - Relativo: informe DELTA (solo las alertas nuevas de esta corrida).
            if use_range:
                report_assessments = get_assessments({"company_id": cid, **date_window})
            else:
                report_assessments = get_assessments_by_alert_ids(cid, evaluated_ids)
            delta_summary = summarize_assessments(report_assessments)
            # Síntesis narrativa con LLM (devuelve {} si la IA no está disponible).
            narrative = synthesize_report(profile, delta_summary, report_assessments)
            report_md = generate_weekly_report(profile, delta_summary, report_assessments, narrative)
            # HTML branded idéntico al que se envía por email; se congela para el visualizador.
            report_html = render_report_html(profile, delta_summary, report_assessments, narrative)

            # Step 4: send email (informe delta)
            recipients = decode_json_list(profile.get("email_recipients"))
            email_sent = False
            if not recipients:
                result["email_error"] = "sin destinatarios configurados"
            else:
                email_sent = send_report_email(recipients, profile, delta_summary, report_assessments, narrative)
                if not email_sent:
                    result["email_error"] = "falló el envío (revisá RESEND_API_KEY y los logs)"
            result["email_sent"] = email_sent

            # Step 5: persistir la corrida en el historial + timestamp
            run_id = save_agent_run({
                "company_id": cid,
                "started_at": started_at,
                "date_from": date_from,
                "fetched": result.get("fetched", 0),
                "inserted": result.get("inserted", 0),
                "evaluated": result["evaluated"],
                "alert_ids": evaluated_ids,
                # Lo que el informe cubre != lo evaluado en esta corrida: en modo rango
                # incluye alertas ya evaluadas antes. El visualizador re-renderiza a
                # partir de esta lista, así que sin ella el informe sale vacío.
                "report_alert_ids": [a["alert_id"] for a in report_assessments],
                "email_sent": email_sent,
                "report_markdown": report_md,
                "report_html": report_html,
                "narrative": narrative,
            })
            result["run_id"] = run_id
            update_last_agent_run(cid, now_iso())

        except Exception as exc:
            result["error"] = str(exc)

        results.append(result)

    return results
