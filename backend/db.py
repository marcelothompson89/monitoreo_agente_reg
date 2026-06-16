import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "regulatory_mvp.db"


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS regulatory_alerts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                source_type TEXT,
                category TEXT,
                country TEXT,
                institution TEXT,
                source_url TEXT,
                presentation_date TEXT,
                full_text TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_source_url
                ON regulatory_alerts(source_url);
            CREATE INDEX IF NOT EXISTS idx_alerts_filters
                ON regulatory_alerts(country, institution, category, presentation_date);

            CREATE TABLE IF NOT EXISTS company_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                industry TEXT,
                countries TEXT,
                product_categories TEXT,
                keywords TEXT,
                excluded_topics TEXT,
                internal_areas TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                alert_id TEXT NOT NULL,
                is_relevant INTEGER NOT NULL,
                priority TEXT NOT NULL,
                impact_score INTEGER NOT NULL,
                impacted_areas TEXT,
                impact_summary TEXT,
                recommended_action TEXT,
                risk_if_ignored TEXT,
                confidence TEXT,
                requires_human_review INTEGER NOT NULL,
                agent_reasoning TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(company_id, alert_id),
                FOREIGN KEY(company_id) REFERENCES company_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY(alert_id) REFERENCES regulatory_alerts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_assessments_company
                ON alert_assessments(company_id, priority, requires_human_review);
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def decode_json_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) else []
    except json.JSONDecodeError:
        return [item.strip() for item in str(value).split(",") if item.strip()]


def hydrate_profile(row: sqlite3.Row | None) -> dict[str, Any] | None:
    profile = row_to_dict(row)
    if not profile:
        return None
    for key in ["countries", "product_categories", "keywords", "excluded_topics", "internal_areas"]:
        profile[key] = decode_json_list(profile.get(key))
    return profile


def list_to_json(value: Any) -> str:
    if isinstance(value, list):
        items = value
    else:
        items = [item.strip() for item in str(value or "").split(",")]
    return json.dumps([item for item in items if item], ensure_ascii=False)


def insert_alert(alert: dict[str, Any]) -> bool:
    alert_id = str(alert.get("id") or "").strip()
    source_url = str(alert.get("source_url") or "").strip()
    if not alert_id:
        raise ValueError("La alerta no tiene id")

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id FROM regulatory_alerts
            WHERE id = ? OR (? != '' AND source_url = ?)
            LIMIT 1
            """,
            (alert_id, source_url, source_url),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            """
            INSERT INTO regulatory_alerts (
                id, title, description, source_type, category, country, institution,
                source_url, presentation_date, full_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                alert.get("title") or "Sin título",
                alert.get("description") or "",
                alert.get("source_type") or "",
                alert.get("category") or "",
                alert.get("country") or "",
                alert.get("institution") or "",
                source_url,
                alert.get("presentation_date") or "",
                alert.get("full_text") or alert.get("description") or "",
                now_iso(),
            ),
        )
        return True


def get_active_company_profile() -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM company_profiles ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return hydrate_profile(row)


def save_company_profile(payload: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO company_profiles (
                company_name, industry, countries, product_categories, keywords,
                excluded_topics, internal_areas, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("company_name") or "Empresa sin nombre",
                payload.get("industry") or "",
                list_to_json(payload.get("countries")),
                list_to_json(payload.get("product_categories")),
                list_to_json(payload.get("keywords")),
                list_to_json(payload.get("excluded_topics")),
                list_to_json(payload.get("internal_areas")),
                payload.get("notes") or "",
                now_iso(),
            ),
        )
    profile = get_active_company_profile()
    assert profile is not None
    return profile


def build_alert_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for field in ["country", "institution", "category"]:
        value = filters.get(field)
        if value:
            clauses.append(f"a.{field} = ?")
            params.append(value)
    if filters.get("date_from"):
        clauses.append("a.presentation_date >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("a.presentation_date <= ?")
        params.append(filters["date_to"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def get_alerts(filters: dict[str, Any] | None = None, limit: int = 500) -> list[dict[str, Any]]:
    where, params = build_alert_where(filters or {})
    sql = f"""
        SELECT a.* FROM regulatory_alerts a
        {where}
        ORDER BY COALESCE(a.presentation_date, '') DESC, a.created_at DESC
        LIMIT ?
    """
    with get_connection() as conn:
        rows = conn.execute(sql, [*params, limit]).fetchall()
    return [dict(row) for row in rows]


def get_unevaluated_alerts(company_id: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
    where, params = build_alert_where(filters)
    extra = "AND" if where else "WHERE"
    sql = f"""
        SELECT a.* FROM regulatory_alerts a
        {where}
        {extra} NOT EXISTS (
            SELECT 1 FROM alert_assessments aa
            WHERE aa.company_id = ? AND aa.alert_id = a.id
        )
        ORDER BY COALESCE(a.presentation_date, '') DESC, a.created_at DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, [*params, company_id]).fetchall()
    return [dict(row) for row in rows]


def save_assessment(company_id: int, alert_id: str, assessment: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO alert_assessments (
                company_id, alert_id, is_relevant, priority, impact_score,
                impacted_areas, impact_summary, recommended_action, risk_if_ignored,
                confidence, requires_human_review, agent_reasoning, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                alert_id,
                1 if assessment.get("is_relevant") else 0,
                assessment.get("priority") or "no_relevante",
                int(assessment.get("impact_score") or 0),
                json.dumps(assessment.get("impacted_areas") or [], ensure_ascii=False),
                assessment.get("impact_summary") or "",
                assessment.get("recommended_action") or "",
                assessment.get("risk_if_ignored") or "",
                assessment.get("confidence") or "baja",
                1 if assessment.get("requires_human_review") else 0,
                assessment.get("agent_reasoning") or "",
                now_iso(),
            ),
        )


def get_filters() -> dict[str, list[str]]:
    with get_connection() as conn:
        result = {}
        for field in ["country", "institution", "category"]:
            rows = conn.execute(
                f"""
                SELECT DISTINCT {field} AS value FROM regulatory_alerts
                WHERE {field} IS NOT NULL AND TRIM({field}) != ''
                ORDER BY {field}
                """
            ).fetchall()
            result[field] = [row["value"] for row in rows]
    return result


def get_assessments(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses = []
    params: list[Any] = []

    if filters.get("company_id"):
        clauses.append("aa.company_id = ?")
        params.append(filters["company_id"])
    if filters.get("priority"):
        clauses.append("aa.priority = ?")
        params.append(filters["priority"])
    if filters.get("country"):
        clauses.append("a.country = ?")
        params.append(filters["country"])
    if filters.get("institution"):
        clauses.append("a.institution = ?")
        params.append(filters["institution"])
    if filters.get("requires_human_review") in ("true", "false", True, False):
        value = filters["requires_human_review"]
        clauses.append("aa.requires_human_review = ?")
        params.append(1 if value in ("true", True) else 0)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                aa.*,
                a.title,
                a.category,
                a.country,
                a.institution,
                a.presentation_date,
                a.source_url
            FROM alert_assessments aa
            JOIN regulatory_alerts a ON a.id = aa.alert_id
            {where}
            ORDER BY COALESCE(a.presentation_date, '') DESC, aa.created_at DESC
            LIMIT 500
            """,
            params,
        ).fetchall()

    assessments = []
    for row in rows:
        item = dict(row)
        item["is_relevant"] = bool(item["is_relevant"])
        item["requires_human_review"] = bool(item["requires_human_review"])
        item["impacted_areas"] = decode_json_list(item.get("impacted_areas"))
        assessments.append(item)
    return assessments


def get_dashboard_summary(company_id: int | None = None) -> dict[str, int]:
    params: list[Any] = []
    company_clause = ""
    if company_id:
        company_clause = "WHERE company_id = ?"
        params.append(company_id)

    with get_connection() as conn:
        total_alerts = conn.execute("SELECT COUNT(*) AS total FROM regulatory_alerts").fetchone()["total"]
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS evaluated,
                SUM(CASE WHEN is_relevant = 1 THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN priority = 'alta' THEN 1 ELSE 0 END) AS high,
                SUM(CASE WHEN priority = 'media' THEN 1 ELSE 0 END) AS medium,
                SUM(CASE WHEN priority = 'baja' THEN 1 ELSE 0 END) AS low,
                SUM(CASE WHEN requires_human_review = 1 THEN 1 ELSE 0 END) AS human_review
            FROM alert_assessments
            {company_clause}
            """,
            params,
        ).fetchone()

    return {
        "total_alerts": total_alerts,
        "evaluated_alerts": row["evaluated"] or 0,
        "relevant_alerts": row["relevant"] or 0,
        "priority_high": row["high"] or 0,
        "priority_medium": row["medium"] or 0,
        "priority_low": row["low"] or 0,
        "requires_human_review": row["human_review"] or 0,
    }
