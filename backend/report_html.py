"""Render del informe a HTML branded (estilo Oversia) para la UI y el email.

Principio: el LLM redacta la prosa (via `report_synth`), pero la maquetación, la
marca y la agrupación por país las garantiza esta plantilla determinista. La marca
es fija (Oversia): azul marino + acento azul, con barra de color por prioridad. El
modelo nunca controla el layout.

Este mismo HTML alimenta el visualizador (iframe), la descarga `.html` y el email,
por eso los estilos van inline en un `<style>` simple, sin fuentes ni assets externos.
"""

from datetime import datetime, timedelta
from typing import Any

from jinja2 import Environment, select_autoescape

from .report_generator import group_by_country

_env = Environment(autoescape=select_autoescape(["html", "xml"]))

# Paleta fija de marca (Oversia).
NAVY = "#0B1830"
ACCENT = "#2563EB"
MUTED = "#566179"
BORDER = "#E4E9F2"
BGALT = "#F5F7FB"

# Colores e etiquetas cortas por prioridad.
PRIORITY_COLOR = {
    "alta": "#C0392B",
    "media": "#B7791F",
    "baja": "#157347",
    "no_relevante": "#8A93A6",
}
PRIORITY_SHORT = {
    "alta": "Alta",
    "media": "Media",
    "baja": "Baja",
    "no_relevante": "No relevante",
}

# Meses en español abreviados (evita depender del locale del sistema en Windows).
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

DISCLAIMER = (
    "Oversia ayuda a detectar, filtrar y priorizar información; cada alerta enlaza a la "
    "fuente oficial. La interpretación final corresponde a su equipo regulatorio y las "
    "acciones sugeridas son orientativas. No reemplaza asesoramiento jurídico, técnico "
    "ni regulatorio."
)


_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.5;
    color: {{ navy }}; background: #ffffff; max-width: 760px; margin: 0 auto; padding: 28px 24px; }
  a { color: {{ accent }}; }

  /* Header */
  .rp-header { display: flex; justify-content: space-between; align-items: flex-start;
    border-bottom: 1px solid {{ border }}; padding-bottom: 14px; margin-bottom: 22px; }
  .rp-wordmark { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; color: {{ navy }}; }
  .rp-wordmark span { color: {{ accent }}; }
  .rp-header-meta { text-align: right; font-size: 12px; }
  .rp-code { font-weight: 700; color: {{ navy }}; }
  .rp-range { color: {{ muted }}; margin-top: 2px; }

  /* Portada */
  .rp-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {{ accent }};
    text-transform: uppercase; margin-bottom: 6px; }
  .rp-title { font-size: 26px; font-weight: 800; color: {{ navy }}; margin: 0 0 6px; }
  .rp-subtitle { color: {{ muted }}; font-size: 14px; margin: 0 0 20px; }

  /* KPIs */
  .rp-kpis { width: 100%; border-collapse: separate; border-spacing: 8px 0; margin: 4px 0 22px; }
  .rp-kpi { background: {{ bgalt }}; border: 1px solid {{ border }}; border-radius: 8px;
    text-align: center; padding: 14px 8px; }
  .rp-kpi-value { font-size: 26px; font-weight: 800; color: {{ accent }}; line-height: 1; }
  .rp-kpi-label { font-size: 10px; font-weight: 700; letter-spacing: 0.5px; color: {{ muted }};
    text-transform: uppercase; margin-top: 6px; }

  /* Resumen ejecutivo */
  .rp-exec { background: {{ bgalt }}; border-left: 4px solid {{ accent }}; border-radius: 0 8px 8px 0;
    padding: 14px 18px; margin: 0 0 12px; }
  .rp-exec-title { font-size: 11px; font-weight: 700; letter-spacing: 0.5px; color: {{ navy }};
    text-transform: uppercase; margin-bottom: 6px; }
  .rp-exec p { margin: 0 0 8px; color: {{ muted }}; }
  .rp-exec ul { margin: 6px 0 0; padding-left: 18px; color: {{ muted }}; }
  .rp-exec li { margin: 3px 0; }
  .rp-priobar { font-size: 13px; font-weight: 700; color: {{ muted }}; margin: 0 0 24px; }

  /* Secciones */
  .rp-section { font-size: 18px; font-weight: 800; color: {{ navy }}; margin: 26px 0 4px;
    padding-bottom: 6px; border-bottom: 2px solid {{ navy }}; }
  .rp-country { font-size: 15px; font-weight: 800; color: {{ accent }}; margin: 20px 0 10px; }
  .rp-country-note { color: {{ muted }}; font-style: italic; font-size: 13px; margin: -4px 0 12px; }

  /* Tarjeta de alerta */
  .rp-card { border: 1px solid {{ border }}; border-left-width: 4px; border-radius: 6px;
    padding: 12px 16px; margin: 0 0 12px; }
  .rp-card-title { font-size: 15px; font-weight: 700; color: {{ navy }}; margin: 0 0 4px; }
  .rp-card-meta { font-size: 12px; color: {{ muted }}; margin: 0 0 8px; }
  .rp-prio { font-weight: 700; }
  .rp-label { font-weight: 700; color: {{ navy }}; }
  .rp-card p { margin: 4px 0; color: {{ muted }}; font-size: 13.5px; }
  .rp-source { font-size: 13px; font-weight: 700; }

  /* Revisión humana */
  .rp-review { background: #FFF7ED; border-left: 4px solid {{ media }}; border-radius: 0 6px 6px 0;
    padding: 10px 16px; margin: 0 0 10px; }
  .rp-review-country { font-weight: 700; color: {{ navy }}; }
  .rp-review p { margin: 4px 0 0; color: {{ muted }}; font-size: 13px; }

  /* Footer */
  .rp-footer { margin-top: 30px; padding-top: 14px; border-top: 1px solid {{ border }};
    font-size: 11px; color: {{ muted }}; }
  .rp-footer .rp-gen { margin-top: 8px; }
</style>
</head>
<body>

<div class="rp-header">
  <div class="rp-wordmark">Over<span>sia</span></div>
  <div class="rp-header-meta">
    <div class="rp-code">{{ report_code }}</div>
    <div class="rp-range">{{ week_range }} · Semana {{ week }}</div>
  </div>
</div>

<div class="rp-eyebrow">Monitoreo regulatorio y sanitario · LATAM</div>
<h1 class="rp-title">Informe regulatorio semanal</h1>
<p class="rp-subtitle">Preparado para {{ company_name }} · Semana {{ week }} · {{ year }}</p>

<table class="rp-kpis"><tr>
  <td class="rp-kpi" width="25%"><div class="rp-kpi-value">{{ summary.get("evaluated_alerts", 0) }}</div><div class="rp-kpi-label">Analizadas</div></td>
  <td class="rp-kpi" width="25%"><div class="rp-kpi-value">{{ summary.get("relevant_alerts", 0) }}</div><div class="rp-kpi-label">Relevantes</div></td>
  <td class="rp-kpi" width="25%"><div class="rp-kpi-value">{{ summary.get("priority_high", 0) }}</div><div class="rp-kpi-label">Prioridad alta</div></td>
  <td class="rp-kpi" width="25%"><div class="rp-kpi-value">{{ summary.get("requires_human_review", 0) }}</div><div class="rp-kpi-label">Revisión humana</div></td>
</tr></table>

<div class="rp-exec">
  <div class="rp-exec-title">Resumen ejecutivo</div>
  {% if executive_summary %}<p>{{ executive_summary }}</p>{% else %}<p>Se evaluaron {{ summary.get("evaluated_alerts", 0) }} alertas regulatorias y sanitarias; {{ summary.get("relevant_alerts", 0) }} resultaron relevantes para {{ company_name }}.</p>{% endif %}
  {% if cross_cutting %}<ul>{% for point in cross_cutting %}<li>{{ point }}</li>{% endfor %}</ul>{% endif %}
</div>
<p class="rp-priobar">Relevantes por prioridad: Alta {{ prio_counts.alta }} · Media {{ prio_counts.media }} · Baja {{ prio_counts.baja }}</p>

{% if country_groups %}
<div class="rp-section">Novedades por país</div>
{% for country, alerts in country_groups %}
  <div class="rp-country">{{ country }}</div>
  {% if country_narratives.get(country) %}<p class="rp-country-note">{{ country_narratives.get(country) }}</p>{% endif %}
  {% for a in alerts %}
  {% set prio = a.get("priority") or "baja" %}
  <div class="rp-card" style="border-left-color: {{ prio_color.get(prio, muted) }}">
    <div class="rp-card-title">{{ a.get("title") or "Sin título" }}</div>
    <div class="rp-card-meta">
      {{ a.get("institution") or "-" }} &nbsp;·&nbsp; {{ a.get("presentation_date") or "Sin fecha" }} &nbsp;·&nbsp;
      <span class="rp-prio" style="color: {{ prio_color.get(prio, muted) }}">Prioridad {{ prio_short.get(prio, "-") }}</span>
    </div>
    {% if a.get("impact_summary") %}<p><span class="rp-label">Impacto:</span> {{ a.get("impact_summary") }}</p>{% endif %}
    {% if a.get("recommended_action") %}<p><span class="rp-label">Acción recomendada:</span> {{ a.get("recommended_action") }}</p>{% endif %}
    {% if a.get("source_url") %}<p><a class="rp-source" href="{{ a.get('source_url') }}">Ver fuente oficial →</a></p>{% endif %}
  </div>
  {% endfor %}
{% endfor %}
{% else %}
<p><em>No se encontraron alertas relevantes para el perfil configurado.</em></p>
{% endif %}

{% if review_items %}
<div class="rp-section">Temas que requieren revisión humana</div>
{% for a in review_items %}
<div class="rp-review">
  <span class="rp-review-country">{{ (a.get("country") or "-") }}</span> — {{ a.get("title") or "Sin título" }}
  {% if a.get("source_url") %} · <a href="{{ a.get('source_url') }}">Ver fuente</a>{% endif %}
  {% if a.get("agent_reasoning") %}<p>{{ a.get("agent_reasoning") }}</p>{% endif %}
</div>
{% endfor %}
{% endif %}

<div class="rp-footer">
  {{ disclaimer }}
  <div class="rp-gen">Informe generado automáticamente para {{ company_name }} por Oversia · Agente de Monitoreo Regulatorio.</div>
</div>
</body>
</html>"""
)


def _date_span(start: datetime, end: datetime) -> str:
    """Devuelve 'dd mmm – dd mmm yyyy' para el período entre `start` y `end`."""
    ini = f"{start.day:02d} {_MESES[start.month - 1]}"
    fin = f"{end.day:02d} {_MESES[end.month - 1]} {end.year}"
    return f"{ini} – {fin}"


def _covered_dates(assessments: list[dict[str, Any]]) -> list[datetime]:
    """Fechas de presentación de las alertas del informe, ordenadas y sin basura."""
    dates = []
    for a in assessments:
        raw = str(a.get("presentation_date") or "")[:10]
        try:
            dates.append(datetime.strptime(raw, "%Y-%m-%d"))
        except ValueError:
            continue  # sin fecha o formato inesperado: no ancla el período
    return sorted(dates)


def _report_period(assessments: list[dict[str, Any]]) -> tuple[int, int, str]:
    """Semana ISO, año y rango a mostrar en la cabecera.

    Se ancla en las alertas que el informe cubre, no en "hoy": un informe de la
    semana 28 consultado en la semana 29 debe seguir diciendo 28. Si el informe no
    tiene alertas fechadas, cae a la fecha actual. Cuando las alertas se salen de la
    semana del ancla (rango manual largo), se muestra el rango real en vez de la
    semana calendario, que sería engañoso.
    """
    dates = _covered_dates(assessments)
    anchor = dates[-1] if dates else datetime.utcnow()
    year, week, _ = anchor.isocalendar()
    monday = anchor - timedelta(days=anchor.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    if dates and (dates[0] < monday or dates[-1] > sunday):
        return year, week, _date_span(dates[0], dates[-1])
    return year, week, _date_span(monday, sunday)


def _priority_counts(assessments: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"alta": 0, "media": 0, "baja": 0}
    for a in assessments:
        if not a.get("is_relevant"):
            continue
        prio = a.get("priority")
        if prio in counts:
            counts[prio] += 1
    return counts


def render_report_html(
    company_profile: dict[str, Any] | None,
    summary: dict[str, int],
    assessments: list[dict[str, Any]],
    narrative: dict[str, Any] | None = None,
) -> str:
    profile = company_profile or {}
    narrative = narrative or {}

    year, week, week_range = _report_period(assessments)

    return _TEMPLATE.render(
        # Paleta / marca fija
        navy=NAVY,
        accent=ACCENT,
        muted=MUTED,
        border=BORDER,
        bgalt=BGALT,
        media=PRIORITY_COLOR["media"],
        prio_color=PRIORITY_COLOR,
        prio_short=PRIORITY_SHORT,
        disclaimer=DISCLAIMER,
        # Cabecera / portada
        company_name=profile.get("company_name") or "tu empresa",
        report_code=f"OVS-{year}-W{week:02d}",
        week_range=week_range,
        week=week,
        year=year,
        # Datos
        summary=summary or {},
        prio_counts=_priority_counts(assessments),
        country_groups=group_by_country(assessments),
        review_items=[a for a in assessments if a.get("requires_human_review")][:10],
        # Narrativa LLM
        executive_summary=narrative.get("executive_summary") or "",
        cross_cutting=narrative.get("cross_cutting") or [],
        country_narratives=narrative.get("country_narratives") or {},
    )
