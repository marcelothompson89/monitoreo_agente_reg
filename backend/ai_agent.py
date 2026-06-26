import json
import os
import re
from typing import Any


PROMPT_TEMPLATE = """Actuás como analista regulatorio senior para empresas de salud, autocuidado, medicamentos OTC, cosmética y productos de consumo regulado en LATAM.

Tu tarea es evaluar si una alerta regulatoria impacta a una empresa específica.

No inventes obligaciones legales. Si la información no es suficiente, indicá que requiere revisión humana.

Perfil de empresa:
{company_profile}

Alerta regulatoria:
{alert}

Devolvé únicamente JSON válido con esta estructura:
{{
  "is_relevant": true,
  "priority": "alta | media | baja | no_relevante",
  "impact_score": 0,
  "impacted_areas": [],
  "impact_summary": "",
  "recommended_action": "",
  "risk_if_ignored": "",
  "confidence": "alta | media | baja",
  "requires_human_review": false,
  "agent_reasoning": ""
}}"""


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        decoded = json.loads(value)
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    except (TypeError, json.JSONDecodeError):
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _text_blob(alert: dict[str, Any]) -> str:
    fields = [
        alert.get("title"),
        alert.get("description"),
        alert.get("category"),
        alert.get("institution"),
        alert.get("full_text"),
    ]
    return " ".join(str(field or "") for field in fields).lower()


def _contains_any(text: str, terms: list[str]) -> list[str]:
    matches = []
    for term in terms:
        clean = term.strip().lower()
        if clean and re.search(rf"\b{re.escape(clean)}\b", text):
            matches.append(term)
    return matches


def mock_evaluate_alert(alert: dict[str, Any], company_profile: dict[str, Any]) -> dict[str, Any]:
    text = _text_blob(alert)
    countries = _as_list(company_profile.get("countries"))
    categories = _as_list(company_profile.get("product_categories"))
    keywords = _as_list(company_profile.get("keywords"))
    excluded_topics = _as_list(company_profile.get("excluded_topics"))
    internal_areas = _as_list(company_profile.get("internal_areas")) or ["Regulatorio"]

    country_match = bool(alert.get("country")) and any(
        alert.get("country", "").lower() == country.lower() for country in countries
    )
    category_matches = _contains_any(text, categories)
    keyword_matches = _contains_any(text, keywords)
    excluded_matches = _contains_any(text, excluded_topics)

    score = 0
    reasons = []
    if country_match:
        score += 4
        reasons.append("coincide país operativo")
    if category_matches:
        score += min(5, 2 + len(category_matches))
        reasons.append(f"coinciden categorías: {', '.join(category_matches[:4])}")
    if keyword_matches:
        score += min(6, 2 + len(keyword_matches))
        reasons.append(f"coinciden keywords: {', '.join(keyword_matches[:6])}")
    if excluded_matches:
        score = max(0, score - 5)
        reasons.append(f"incluye temas excluidos: {', '.join(excluded_matches[:4])}")

    score = max(0, min(15, score))
    is_relevant = score >= 4 and not (excluded_matches and score < 6)

    if not is_relevant:
        priority = "no_relevante"
    elif score >= 11:
        priority = "alta"
    elif score >= 7:
        priority = "media"
    else:
        priority = "baja"

    confidence = "alta" if score >= 8 or not is_relevant else "media"
    if not alert.get("description") and not alert.get("full_text"):
        confidence = "baja"

    requires_review = confidence == "baja" or (is_relevant and score in [4, 5, 6])
    impacted_areas = internal_areas if is_relevant else []

    return {
        "is_relevant": is_relevant,
        "priority": priority,
        "impact_score": score,
        "impacted_areas": impacted_areas,
        "impact_summary": (
            f"La alerta podría impactar a {company_profile.get('company_name')} por "
            f"{', '.join(reasons)}."
            if is_relevant
            else "No se detectaron coincidencias suficientes con el perfil configurado."
        ),
        "recommended_action": (
            "Revisar el texto fuente, confirmar alcance regulatorio y asignar responsable interno."
            if is_relevant
            else "Mantener como informativa salvo que aparezcan nuevas coincidencias."
        ),
        "risk_if_ignored": (
            "Podrían omitirse cambios regulatorios aplicables, plazos o ajustes operativos."
            if is_relevant
            else "Riesgo bajo según las coincidencias configuradas."
        ),
        "confidence": confidence,
        "requires_human_review": requires_review,
        "agent_reasoning": "Evaluación mock basada en país, categorías, keywords y temas excluidos.",
    }


# Campos que se envían a OpenAI. Se excluyen id, created_at, email_recipients (PII),
# days_back, alert_sources y last_agent_run: no aportan al análisis y gastan tokens.
_PROFILE_FIELDS_FOR_AI = (
    "company_name",
    "industry",
    "countries",
    "product_categories",
    "keywords",
    "excluded_topics",
    "internal_areas",
    "company_description",
    "notes",
)
_ALERT_FIELDS_FOR_AI = (
    "title",
    "description",
    "source_type",
    "category",
    "country",
    "institution",
    "presentation_date",
    "full_text",
)


def _pick(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Devuelve solo los campos indicados que tengan algún valor."""
    return {key: data[key] for key in fields if data.get(key) not in (None, "", [], {})}


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return json.loads(content)


def _normalize_assessment(data: dict[str, Any]) -> dict[str, Any]:
    priority = data.get("priority")
    if priority not in {"alta", "media", "baja", "no_relevante"}:
        priority = "no_relevante"
    confidence = data.get("confidence")
    if confidence not in {"alta", "media", "baja"}:
        confidence = "baja"
    return {
        "is_relevant": bool(data.get("is_relevant")),
        "priority": priority,
        "impact_score": max(0, min(15, int(data.get("impact_score") or 0))),
        "impacted_areas": _as_list(data.get("impacted_areas")),
        "impact_summary": str(data.get("impact_summary") or ""),
        "recommended_action": str(data.get("recommended_action") or ""),
        "risk_if_ignored": str(data.get("risk_if_ignored") or ""),
        "confidence": confidence,
        "requires_human_review": bool(data.get("requires_human_review")),
        "agent_reasoning": str(data.get("agent_reasoning") or ""),
    }


def evaluate_alert(alert: dict[str, Any], company_profile: dict[str, Any]) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return mock_evaluate_alert(alert, company_profile)

    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = PROMPT_TEMPLATE.format(
            company_profile=json.dumps(_pick(company_profile, _PROFILE_FIELDS_FOR_AI), ensure_ascii=False, indent=2),
            alert=json.dumps(_pick(alert, _ALERT_FIELDS_FOR_AI), ensure_ascii=False, indent=2),
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Respondé solo con JSON válido, sin Markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return _normalize_assessment(_extract_json(content))
    except Exception as exc:
        fallback = mock_evaluate_alert(alert, company_profile)
        fallback["confidence"] = "baja"
        fallback["requires_human_review"] = True
        fallback["agent_reasoning"] = f"Fallback mock por error al llamar OpenAI: {exc}"
        return fallback
