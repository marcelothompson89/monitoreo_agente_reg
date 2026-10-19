"""Capa de síntesis del informe con LLM.

El modelo redacta *prosa* (resumen ejecutivo, análisis transversal y una narrativa
por país); la maquetación, el logo y la agrupación las garantiza la plantilla
determinista de `report_html.py` / `report_generator.py`. El modelo nunca controla
el layout.

Si no hay `OPENAI_API_KEY` o falla la llamada, se devuelve `{}` y el informe se arma
igual con las secciones deterministas (mismo patrón que `ai_agent.evaluate_alert`).
"""

import json
import os
import re
from typing import Any


SYNTH_PROMPT = """Actuás como analista regulatorio senior para empresas de salud, autocuidado, medicamentos OTC, cosmética y productos de consumo regulado en LATAM.

Vas a redactar la parte narrativa de un informe semanal para la empresa "{company_name}".

No inventes obligaciones legales ni normas que no aparezcan en los datos. Sé concreto y accionable. Escribí en español rioplatense, tono profesional.

Resumen cuantitativo de la semana:
{summary}

Alertas relevantes (ya evaluadas por el agente):
{alerts}

Devolvé únicamente JSON válido con esta estructura:
{{
  "executive_summary": "2 a 4 oraciones que sinteticen lo más importante de la semana para la empresa.",
  "cross_cutting": ["hallazgos que atraviesan varias alertas o países, como patrones o acciones que conviene coordinar"],
  "country_narratives": {{"NombrePaís": "1 a 3 oraciones sobre lo relevante en ese país"}}
}}

Si no hay alertas relevantes, devolvé executive_summary explicándolo, cross_cutting vacío y country_narratives vacío."""


# Campos de cada assessment que se mandan al modelo. Se excluye full_text para
# acotar tokens; la síntesis trabaja sobre lo ya evaluado, no sobre el texto crudo.
_ALERT_FIELDS = ("title", "country", "priority", "impact_summary", "recommended_action")


def _compact_alerts(assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for a in assessments:
        if not a.get("is_relevant"):
            continue
        compact.append({k: a.get(k) for k in _ALERT_FIELDS if a.get(k)})
    return compact


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return json.loads(content)


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    cross = data.get("cross_cutting")
    if not isinstance(cross, list):
        cross = []
    narratives = data.get("country_narratives")
    if not isinstance(narratives, dict):
        narratives = {}
    return {
        "executive_summary": str(data.get("executive_summary") or "").strip(),
        "cross_cutting": [str(item).strip() for item in cross if str(item).strip()],
        "country_narratives": {
            str(k).strip(): str(v).strip()
            for k, v in narratives.items()
            if str(k).strip() and str(v).strip()
        },
    }


def synthesize_report(
    company_profile: dict[str, Any] | None,
    summary: dict[str, int],
    assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Devuelve la narrativa del informe. `{}` si la IA no está disponible o falla."""
    if not os.getenv("OPENAI_API_KEY"):
        return {}

    company_name = (company_profile or {}).get("company_name") or "la empresa"
    alerts = _compact_alerts(assessments)

    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = SYNTH_PROMPT.format(
            company_name=company_name,
            summary=json.dumps(summary, ensure_ascii=False, indent=2),
            alerts=json.dumps(alerts, ensure_ascii=False, indent=2),
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
            messages=[
                {"role": "system", "content": "Respondé solo con JSON válido, sin Markdown."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return _normalize(_extract_json(content))
    except Exception as exc:
        print(f"[report_synth] Síntesis omitida por error: {exc}")
        return {}
