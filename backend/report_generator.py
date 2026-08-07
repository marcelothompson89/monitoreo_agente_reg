from collections import defaultdict
from datetime import datetime
from typing import Any

PRIORITY_LABEL = {
    "alta": "🔴 Prioridad Alta",
    "media": "🟡 Prioridad Media",
    "baja": "🟢 Informativa",
    "no_relevante": "⚪ No relevante",
}

PRIORITY_ORDER = ["alta", "media", "baja", "no_relevante"]


def _alert_block(item: dict[str, Any]) -> str:
    title = item.get("title") or "Sin título"
    date = item.get("presentation_date") or "Sin fecha"
    institution = item.get("institution") or "-"
    priority = PRIORITY_LABEL.get(item.get("priority") or "baja", "")
    impact = item.get("impact_summary") or "-"
    action = item.get("recommended_action") or "-"
    risk = item.get("risk_if_ignored") or ""
    areas = item.get("impacted_areas")
    if isinstance(areas, list):
        areas_text = ", ".join(areas) if areas else "-"
    else:
        areas_text = areas or "-"
    source = item.get("source_url") or ""
    review = item.get("requires_human_review", False)

    lines = [
        f"### {title}",
        f"**{institution}** &nbsp;|&nbsp; {date} &nbsp;|&nbsp; {priority}",
        "",
        f"**Impacto:** {impact}",
        "",
        f"**Áreas afectadas:** {areas_text}",
        "",
        f"**Acción recomendada:** {action}",
    ]
    if risk:
        lines += ["", f"**Riesgo si no se actúa:** {risk}"]
    if review:
        lines += ["", "> ⚠️ Requiere revisión humana"]
    if source:
        lines += ["", f"[Ver fuente]({source})"]
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def group_by_country(assessments: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Agrupa las alertas relevantes por país y las ordena.

    Helper compartido por el informe markdown y el HTML branded para no duplicar
    las reglas de orden. Devuelve una lista de (país, alertas) donde:
      - los países vienen ordenados: primero los que tienen prioridad alta, luego media, luego resto;
      - dentro de cada país las alertas van por prioridad y luego por impact_score desc.
    """
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in assessments:
        if not item.get("is_relevant"):
            continue
        country = (item.get("country") or "Sin país").strip().title()
        by_country[country].append(item)

    def country_sort_key(c: str) -> tuple:
        items = by_country[c]
        has_alta = any(a.get("priority") == "alta" for a in items)
        has_media = any(a.get("priority") == "media" for a in items)
        return (0 if has_alta else 1 if has_media else 2, c)

    def alert_sort_key(a: dict[str, Any]) -> tuple:
        return (
            PRIORITY_ORDER.index(a.get("priority") or "no_relevante"),
            -(a.get("impact_score") or 0),
        )

    result = []
    for country in sorted(by_country.keys(), key=country_sort_key):
        result.append((country, sorted(by_country[country], key=alert_sort_key)))
    return result


def _country_section(country: str, alerts: list[dict[str, Any]], narrative: str = "") -> str:
    lines = [f"## 🌎 {country}", ""]
    if narrative:
        lines += [f"*{narrative}*", ""]
    for item in alerts:
        lines.append(_alert_block(item))
    return "\n".join(lines)


def generate_weekly_report(
    company_profile: dict[str, Any] | None,
    summary: dict[str, int],
    assessments: list[dict[str, Any]],
    narrative: dict[str, Any] | None = None,
) -> str:
    company_name = (company_profile or {}).get("company_name") or "Empresa"
    now = datetime.now().strftime("%d de %B de %Y, %H:%M")
    narrative = narrative or {}
    country_narratives = narrative.get("country_narratives") or {}

    # Only include relevant alerts in country sections
    non_relevant = [a for a in assessments if not a.get("is_relevant")]

    # Group relevant alerts by country (helper compartido con el HTML branded)
    country_groups = group_by_country(assessments)
    sorted_countries = [c for c, _ in country_groups]

    # Build top actions list
    top_actions = [
        a for a in assessments
        if a.get("is_relevant") and a.get("recommended_action")
        and a.get("priority") in ("alta", "media")
    ][:10]

    # Build requires_review list
    review_items = [a for a in assessments if a.get("requires_human_review")][:10]

    lines = [
        f"# Monitoreo Regulatorio — {company_name}",
        f"*{now}*",
        "",
        "---",
        "",
        "## Resumen ejecutivo",
        "",
        f"| Indicador | Valor |",
        f"|-----------|-------|",
        f"| Alertas totales cargadas | {summary.get('total_alerts', 0)} |",
        f"| Alertas evaluadas | {summary.get('evaluated_alerts', 0)} |",
        f"| Alertas relevantes | {summary.get('relevant_alerts', 0)} |",
        f"| 🔴 Prioridad alta | {summary.get('priority_high', 0)} |",
        f"| 🟡 Prioridad media | {summary.get('priority_medium', 0)} |",
        f"| ⚠️ Requieren revisión humana | {summary.get('requires_human_review', 0)} |",
        f"| Países con alertas relevantes | {len(sorted_countries)} |",
        "",
    ]

    # Síntesis redactada por el LLM (si está disponible)
    if narrative.get("executive_summary"):
        lines += ["", narrative["executive_summary"], ""]
    if narrative.get("cross_cutting"):
        lines += ["**Puntos transversales:**", ""]
        for point in narrative["cross_cutting"]:
            lines.append(f"- {point}")
        lines.append("")

    lines += ["---", ""]

    # Top actions summary
    if top_actions:
        lines += [
            "## Acciones prioritarias esta semana",
            "",
        ]
        for i, item in enumerate(top_actions, 1):
            country = (item.get("country") or "").strip().title()
            action = item.get("recommended_action", "")
            title = item.get("title", "")
            priority = item.get("priority", "")
            emoji = "🔴" if priority == "alta" else "🟡"
            lines.append(f"{i}. {emoji} **{country}** — {action}  \n   *({title})*")
        lines += ["", "---", ""]

    # Country sections
    if country_groups:
        lines += ["## Novedades por país", ""]
        for country, alerts in country_groups:
            lines.append(_country_section(country, alerts, country_narratives.get(country, "")))
    else:
        lines += ["*No se encontraron alertas relevantes para el perfil configurado.*", ""]

    # Human review section
    if review_items:
        lines += [
            "---",
            "",
            "## ⚠️ Temas que requieren revisión humana",
            "",
        ]
        for item in review_items:
            country = (item.get("country") or "-").strip().title()
            title = item.get("title") or "Sin título"
            reasoning = item.get("agent_reasoning") or ""
            source = item.get("source_url") or ""
            link = f" [Ver]({source})" if source else ""
            lines.append(f"- **{country}** — {title}{link}")
            if reasoning:
                lines.append(f"  > {reasoning}")
        lines.append("")

    # Non-relevant summary (compact)
    if non_relevant:
        lines += [
            "---",
            "",
            f"## ⚪ Alertas descartadas ({len(non_relevant)})",
            "",
            "*Las siguientes alertas fueron evaluadas como no relevantes para el perfil actual:*",
            "",
        ]
        for item in non_relevant[:20]:
            country = (item.get("country") or "-").strip().title()
            title = item.get("title") or "Sin título"
            lines.append(f"- {country} — {title}")
        if len(non_relevant) > 20:
            lines.append(f"- … y {len(non_relevant) - 20} más.")
        lines.append("")

    lines += [
        "---",
        "",
        f"*Informe generado automáticamente por el Agente de Monitoreo Regulatorio · {now}*",
        "",
    ]

    return "\n".join(lines)
