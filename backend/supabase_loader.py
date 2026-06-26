import os
from datetime import datetime, timedelta
from typing import Any

from .ai_agent import mock_evaluate_alert
from .db import decode_json_list, existing_alert_keys, insert_alert, now_iso, save_assessment


def _get_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL y SUPABASE_KEY son requeridos en .env")
    return create_client(url, key)


def _build_date_floor(days_back: int, last_run: str | None) -> str:
    if last_run:
        try:
            dt = datetime.fromisoformat(last_run)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")


def _map_row(row: dict[str, Any]) -> dict[str, Any]:
    description = row.get("description") or ""
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "Sin título",
        "description": description,
        "full_text": description,
        "source_type": row.get("source_type") or "",
        "category": row.get("category") or "",
        "country": row.get("country") or "",
        "institution": row.get("institution") or "",
        "source_url": row.get("source_url") or "",
        "presentation_date": row.get("presentation_date") or "",
    }


def _query_alert_rows(
    profile: dict[str, Any],
    days_back: int,
    date_from: str | None,
    date_to: str | None,
    max_alerts: int,
) -> tuple[list[dict[str, Any]], str]:
    """Trae las filas de Supabase según la ventana y los filtros del perfil.

    Dos modos de ventana de búsqueda:
      - Rango manual: si se pasa `date_from`, ese es el piso (y `date_to`, si viene,
        el techo). El informe se hace exactamente sobre ese período.
      - Relativo ("días hacia atrás"): piso = hoy − days_back, sin techo.
    Devuelve (filas, date_floor). Es la misma query que usan el fetch real y la
    previsualización, para que los números coincidan.
    """
    client = _get_client()

    countries = decode_json_list(profile.get("countries"))
    keywords = decode_json_list(profile.get("keywords"))
    alert_sources = decode_json_list(profile.get("alert_sources"))

    date_floor = date_from if date_from else _build_date_floor(days_back, None)

    query = (
        client.table("alertas_alerta")
        .select("*")
        .gte("presentation_date", date_floor)
        .order("presentation_date", desc=True)
        .limit(max_alerts)
    )

    if date_to:
        query = query.lte("presentation_date", date_to)

    if countries:
        query = query.in_("country", countries)

    if alert_sources:
        query = query.in_("institution", alert_sources)

    if keywords:
        # Build OR filter for keywords across title and description
        or_parts = []
        for kw in keywords:
            kw_clean = kw.strip()
            if kw_clean:
                or_parts.append(f"title.ilike.%{kw_clean}%")
                or_parts.append(f"description.ilike.%{kw_clean}%")
        if or_parts:
            query = query.or_(",".join(or_parts))

    response = query.execute()
    return response.data or [], date_floor


def preview_agent_run(
    profile: dict[str, Any],
    days_back: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    max_alerts: int = 200,
) -> dict[str, Any]:
    """Dry-run: cuenta qué haría una corrida SIN insertar ni llamar a OpenAI.

    Replica el fetch + pre-filtro local (gratis) para estimar cuántas alertas nuevas
    llegarían a la evaluación con IA. No persiste nada."""
    rows, date_floor = _query_alert_rows(profile, days_back, date_from, date_to, max_alerts)

    existing = existing_alert_keys(
        [str(r.get("id") or "") for r in rows],
        [str(r.get("source_url") or "") for r in rows],
    )

    already_present = would_prefilter = would_evaluate_new = 0
    for row in rows:
        alert = _map_row(row)
        if alert["id"] in existing or (alert["source_url"] and alert["source_url"] in existing):
            already_present += 1
            continue
        pre_score = mock_evaluate_alert(alert, profile)
        if pre_score["impact_score"] < 2:
            would_prefilter += 1
        else:
            would_evaluate_new += 1

    return {
        "fetched": len(rows),
        "already_present": already_present,
        "would_prefilter": would_prefilter,
        "would_evaluate_new": would_evaluate_new,
        "hit_fetch_ceiling": len(rows) >= max_alerts,
        "date_from": date_floor,
        "date_to": date_to or None,
    }


def fetch_alerts_for_company(
    profile: dict[str, Any],
    days_back: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    max_alerts: int = 200,
) -> dict[str, int]:
    rows, date_floor = _query_alert_rows(profile, days_back, date_from, date_to, max_alerts)

    fetched = len(rows)
    inserted = 0
    pre_filtered = 0

    for row in rows:
        alert = _map_row(row)

        pre_score = mock_evaluate_alert(alert, profile)

        if pre_score["impact_score"] < 2:
            # Save to local DB but mark as no_relevante to skip AI evaluation
            insert_alert(alert)
            pre_filtered_assessment = {**pre_score, "priority": "no_relevante", "is_relevant": False}
            save_assessment(profile["id"], alert["id"], pre_filtered_assessment)
            pre_filtered += 1
        else:
            if insert_alert(alert):
                inserted += 1

    return {
        "fetched": fetched,
        "inserted": inserted,
        "pre_filtered_as_irrelevant": pre_filtered,
        "date_from": date_floor,
        "date_to": date_to or None,
    }


_sources_cache: list[str] | None = None


def get_available_sources(refresh: bool = False) -> list[str]:
    """Return distinct institution values from Supabase for UI checkboxes.

    PostgREST corta cada respuesta en ~1000 filas (db-max-rows), así que un único
    select se queda con las primeras 1000 filas y pierde instituciones que recién
    aparecen más adelante (la tabla tiene decenas de miles). Por eso paginamos con
    .range() hasta recorrer todo. El resultado se cachea en memoria porque las
    fuentes cambian rara vez; pasar refresh=True fuerza una recarga.
    """
    global _sources_cache
    if _sources_cache is not None and not refresh:
        return _sources_cache

    try:
        client = _get_client()
        seen: set[str] = set()
        start, page = 0, 1000
        max_pages = 500  # tope de seguridad (~500k filas)
        for _ in range(max_pages):
            response = (
                client.table("alertas_alerta")
                .select("institution")
                .not_.is_("institution", "null")
                .range(start, start + page - 1)
                .execute()
            )
            rows = response.data or []
            for row in rows:
                val = (row.get("institution") or "").strip()
                if val:
                    seen.add(val)
            if len(rows) < page:
                break
            start += page
        _sources_cache = sorted(seen)
        return _sources_cache
    except Exception:
        return []
