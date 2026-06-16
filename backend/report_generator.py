from collections import defaultdict
from datetime import datetime
from typing import Any


def _section(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"## {title}", ""]
    if not rows:
        lines.append("Sin alertas en esta sección.")
        lines.append("")
        return "\n".join(lines)

    for item in rows:
        date = item.get("presentation_date") or "Sin fecha"
        source = item.get("source_url") or ""
        source_text = f" [Fuente]({source})" if source else ""
        lines.extend(
            [
                f"### {item.get('title') or 'Sin título'}",
                f"- Fecha: {date}",
                f"- País / institución: {item.get('country') or '-'} / {item.get('institution') or '-'}",
                f"- Prioridad / score: {item.get('priority')} / {item.get('impact_score')}",
                f"- Impacto: {item.get('impact_summary') or '-'}",
                f"- Acción recomendada: {item.get('recommended_action') or '-'}{source_text}",
                "",
            ]
        )
    return "\n".join(lines)


def generate_weekly_report(
    company_profile: dict[str, Any] | None,
    summary: dict[str, int],
    assessments: list[dict[str, Any]],
) -> str:
    company_name = (company_profile or {}).get("company_name") or "Empresa"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in assessments:
        grouped[item.get("priority") or "no_relevante"].append(item)

    actions = [
        item for item in assessments
        if item.get("is_relevant") and item.get("recommended_action")
    ][:12]
    review_topics = [
        item for item in assessments
        if item.get("requires_human_review")
    ][:12]

    lines = [
        f"# Informe semanal de monitoreo regulatorio - {company_name}",
        "",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Resumen ejecutivo",
        "",
        f"- Alertas cargadas: {summary.get('total_alerts', 0)}",
        f"- Alertas evaluadas: {summary.get('evaluated_alerts', 0)}",
        f"- Alertas relevantes: {summary.get('relevant_alerts', 0)}",
        f"- Prioridad alta: {summary.get('priority_high', 0)}",
        f"- Prioridad media: {summary.get('priority_medium', 0)}",
        f"- Requieren revisión humana: {summary.get('requires_human_review', 0)}",
        "",
        _section("Alertas de prioridad alta", grouped["alta"]),
        _section("Alertas de prioridad media", grouped["media"]),
        _section("Alertas informativas", grouped["baja"] + grouped["no_relevante"]),
        "## Acciones recomendadas",
        "",
    ]

    if actions:
        for item in actions:
            lines.append(f"- {item.get('recommended_action')} ({item.get('title')})")
    else:
        lines.append("Sin acciones recomendadas pendientes.")

    lines.extend(["", "## Temas para seguimiento", ""])
    if review_topics:
        for item in review_topics:
            lines.append(f"- Revisar manualmente: {item.get('title')} ({item.get('country')})")
    else:
        lines.append("No hay temas marcados para revisión humana.")

    lines.append("")
    return "\n".join(lines)
