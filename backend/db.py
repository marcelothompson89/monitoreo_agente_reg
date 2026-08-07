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
                company_description TEXT DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                date_from TEXT,
                fetched INTEGER DEFAULT 0,
                inserted INTEGER DEFAULT 0,
                evaluated INTEGER DEFAULT 0,
                alert_ids TEXT,
                report_alert_ids TEXT,
                email_sent INTEGER DEFAULT 0,
                report_markdown TEXT,
                report_html TEXT,
                deleted_at TEXT DEFAULT NULL,
                FOREIGN KEY(company_id) REFERENCES company_profiles(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_agent_runs_company
                ON agent_runs(company_id, started_at);
            """
        )
        # Migrations for existing DBs
        migrations = [
            "ALTER TABLE company_profiles ADD COLUMN company_description TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN email_recipients TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN days_back INTEGER DEFAULT 7",
            "ALTER TABLE company_profiles ADD COLUMN alert_sources TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN last_agent_run TEXT DEFAULT NULL",
            "ALTER TABLE company_profiles ADD COLUMN agent_date_from TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN agent_date_to TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN agent_max_eval INTEGER DEFAULT 100",
            "ALTER TABLE company_profiles ADD COLUMN report_logo_url TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN report_primary_color TEXT DEFAULT '#176b62'",
            "ALTER TABLE company_profiles ADD COLUMN report_header TEXT DEFAULT ''",
            "ALTER TABLE company_profiles ADD COLUMN report_footer TEXT DEFAULT ''",
            "ALTER TABLE alert_assessments ADD COLUMN tools_used TEXT DEFAULT ''",
            "ALTER TABLE agent_runs ADD COLUMN report_html TEXT DEFAULT ''",
            "ALTER TABLE agent_runs ADD COLUMN narrative TEXT DEFAULT ''",
            "ALTER TABLE agent_runs ADD COLUMN deleted_at TEXT DEFAULT NULL",
            "ALTER TABLE agent_runs ADD COLUMN report_alert_ids TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


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
    for key in ["industry", "countries", "product_categories", "keywords", "excluded_topics", "internal_areas", "email_recipients", "alert_sources"]:
        profile[key] = decode_json_list(profile.get(key))
    return profile


def list_to_json(value: Any) -> str:
    if isinstance(value, list):
        items = value
    else:
        items = [item.strip() for item in str(value or "").split(",")]
    return json.dumps([item for item in items if item], ensure_ascii=False)


def insert_alert(alert: dict[str, Any]) -> tuple[str, bool]:
    """Inserta la alerta si no existe (deduplicando por id o source_url).

    Devuelve (id_canónico, fue_insertada): el id_canónico es el id REAL con el que
    la alerta quedó en la tabla — si ya existía deduplicada por source_url con otro
    id, devuelve ese id existente (no el entrante). Así el caller puede guardar el
    assessment contra un id que sí existe y no violar la foreign key."""
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
            return existing["id"], False

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
        return alert_id, True


def existing_alert_keys(ids: list[str], source_urls: list[str]) -> set[str]:
    """Devuelve el subconjunto de ids/source_urls que YA existen localmente.

    Sirve para previsualizar cuántas alertas son nuevas (sin insertarlas), usando
    la misma lógica de deduplicación que insert_alert (id o source_url)."""
    ids = [i for i in ids if i]
    urls = [u for u in source_urls if u]
    if not ids and not urls:
        return set()
    clauses: list[str] = []
    params: list[Any] = []
    if ids:
        clauses.append(f"id IN ({','.join('?' for _ in ids)})")
        params.extend(ids)
    if urls:
        clauses.append(f"source_url IN ({','.join('?' for _ in urls)})")
        params.extend(urls)
    sql = f"SELECT id, source_url FROM regulatory_alerts WHERE {' OR '.join(clauses)}"
    keys: set[str] = set()
    with get_connection() as conn:
        for row in conn.execute(sql, params).fetchall():
            keys.add(row["id"])
            if row["source_url"]:
                keys.add(row["source_url"])
    return keys


def get_active_company_profile(company_id: int | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        if company_id:
            row = conn.execute(
                "SELECT * FROM company_profiles WHERE id = ?", (company_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM company_profiles ORDER BY id DESC LIMIT 1"
            ).fetchone()
    return hydrate_profile(row)


def get_all_companies() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, company_name, industry, created_at FROM company_profiles ORDER BY id DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["industry"] = decode_json_list(item.get("industry"))
        result.append(item)
    return result


# Columnas actualizables del perfil → cómo serializar cada valor al escribir.
# Se usa para el UPDATE parcial: solo se tocan las columnas cuya clave viene en el
# payload, de modo que guardar desde un formulario que no incluye (p. ej.)
# `alert_sources` no las pise con vacío. Ver save_company_profile.
_PROFILE_COLUMN_ENCODERS: dict[str, Any] = {
    "company_name": lambda v: v or "Empresa sin nombre",
    "industry": list_to_json,
    "countries": list_to_json,
    "product_categories": list_to_json,
    "keywords": list_to_json,
    "excluded_topics": list_to_json,
    "internal_areas": list_to_json,
    "notes": lambda v: v or "",
    "company_description": lambda v: v or "",
    "email_recipients": list_to_json,
    "days_back": lambda v: int(v or 7),
    "alert_sources": list_to_json,
    "agent_date_from": lambda v: v or "",
    "agent_date_to": lambda v: v or "",
    "agent_max_eval": lambda v: int(v or 100),
    "report_logo_url": lambda v: v or "",
    "report_primary_color": lambda v: v or "#176b62",
    "report_header": lambda v: v or "",
    "report_footer": lambda v: v or "",
}


def save_company_profile(payload: dict[str, Any]) -> dict[str, Any]:
    company_id = payload.get("id")
    new_id: int | None = None
    with get_connection() as conn:
        if company_id:
            # UPDATE parcial: solo las columnas presentes en el payload. Así una
            # pantalla que no envía cierto campo no lo borra (el llamador debe pasar
            # únicamente lo que quiere cambiar, p. ej. via dict(exclude_unset=True)).
            updates = [
                (col, encode(payload[col]))
                for col, encode in _PROFILE_COLUMN_ENCODERS.items()
                if col in payload
            ]
            if updates:
                set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
                params = [value for _, value in updates]
                params.append(company_id)
                conn.execute(
                    f"UPDATE company_profiles SET {set_clause} WHERE id = ?",
                    params,
                )
            new_id = int(company_id)
        else:
            cursor = conn.execute(
                """
                INSERT INTO company_profiles (
                    company_name, industry, countries, product_categories, keywords,
                    excluded_topics, internal_areas, notes, company_description,
                    email_recipients, days_back, alert_sources, agent_date_from,
                    agent_date_to, agent_max_eval, report_logo_url, report_primary_color,
                    report_header, report_footer, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("company_name") or "Empresa sin nombre",
                    list_to_json(payload.get("industry")),
                    list_to_json(payload.get("countries")),
                    list_to_json(payload.get("product_categories")),
                    list_to_json(payload.get("keywords")),
                    list_to_json(payload.get("excluded_topics")),
                    list_to_json(payload.get("internal_areas")),
                    payload.get("notes") or "",
                    payload.get("company_description") or "",
                    list_to_json(payload.get("email_recipients")),
                    int(payload.get("days_back") or 7),
                    list_to_json(payload.get("alert_sources")),
                    payload.get("agent_date_from") or "",
                    payload.get("agent_date_to") or "",
                    int(payload.get("agent_max_eval") or 100),
                    payload.get("report_logo_url") or "",
                    payload.get("report_primary_color") or "#176b62",
                    payload.get("report_header") or "",
                    payload.get("report_footer") or "",
                    now_iso(),
                ),
            )
            new_id = cursor.lastrowid  # capture ID before commit
    # Read AFTER the with-block so the commit is visible to the new connection
    profile = get_active_company_profile(new_id)
    assert profile is not None
    return profile


def update_last_agent_run(company_id: int, ts: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE company_profiles SET last_agent_run = ? WHERE id = ?",
            (ts, company_id),
        )


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


def get_alerts_by_ids(alert_ids: list[str]) -> list[dict[str, Any]]:
    if not alert_ids:
        return []
    placeholders = ",".join("?" for _ in alert_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM regulatory_alerts WHERE id IN ({placeholders})",
            alert_ids,
        ).fetchall()
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


def save_assessment(company_id: int, alert_id: str, assessment: dict[str, Any], force: bool = False) -> None:
    """Guarda una evaluación. Por defecto no pisa una existente (INSERT OR IGNORE);
    con force=True la re-evalúa y reemplaza los campos (usado para re-evaluación manual)."""
    values = (
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
        json.dumps(assessment.get("tools_used") or [], ensure_ascii=False),
        now_iso(),
    )
    conflict_action = (
        """
        DO UPDATE SET
            is_relevant = excluded.is_relevant,
            priority = excluded.priority,
            impact_score = excluded.impact_score,
            impacted_areas = excluded.impacted_areas,
            impact_summary = excluded.impact_summary,
            recommended_action = excluded.recommended_action,
            risk_if_ignored = excluded.risk_if_ignored,
            confidence = excluded.confidence,
            requires_human_review = excluded.requires_human_review,
            agent_reasoning = excluded.agent_reasoning,
            tools_used = excluded.tools_used,
            created_at = excluded.created_at
        """
        if force
        else "DO NOTHING"
    )
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO alert_assessments (
                company_id, alert_id, is_relevant, priority, impact_score,
                impacted_areas, impact_summary, recommended_action, risk_if_ignored,
                confidence, requires_human_review, agent_reasoning, tools_used, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, alert_id) {conflict_action}
            """,
            values,
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
    if filters.get("date_from"):
        clauses.append("a.presentation_date >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("a.presentation_date <= ?")
        params.append(filters["date_to"])

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
        item["tools_used"] = decode_json_list(item.get("tools_used"))
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


def get_assessments_by_alert_ids(company_id: int, alert_ids: list[str]) -> list[dict[str, Any]]:
    """Assessments de una empresa restringidos a una lista de alert_ids (para el informe delta)."""
    if not alert_ids:
        return []
    placeholders = ",".join("?" for _ in alert_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT aa.*, a.title, a.category, a.country, a.institution,
                   a.presentation_date, a.source_url
            FROM alert_assessments aa
            JOIN regulatory_alerts a ON a.id = aa.alert_id
            WHERE aa.company_id = ? AND aa.alert_id IN ({placeholders})
            ORDER BY COALESCE(a.presentation_date, '') DESC, aa.created_at DESC
            """,
            [company_id, *alert_ids],
        ).fetchall()

    assessments = []
    for row in rows:
        item = dict(row)
        item["is_relevant"] = bool(item["is_relevant"])
        item["requires_human_review"] = bool(item["requires_human_review"])
        item["impacted_areas"] = decode_json_list(item.get("impacted_areas"))
        item["tools_used"] = decode_json_list(item.get("tools_used"))
        assessments.append(item)
    return assessments


def summarize_assessments(assessments: list[dict[str, Any]]) -> dict[str, int]:
    """Conteos sobre una lista de assessments, con las mismas claves que get_dashboard_summary."""
    return {
        "total_alerts": len(assessments),
        "evaluated_alerts": len(assessments),
        "relevant_alerts": sum(1 for a in assessments if a.get("is_relevant")),
        "priority_high": sum(1 for a in assessments if a.get("priority") == "alta"),
        "priority_medium": sum(1 for a in assessments if a.get("priority") == "media"),
        "priority_low": sum(1 for a in assessments if a.get("priority") == "baja"),
        "requires_human_review": sum(1 for a in assessments if a.get("requires_human_review")),
    }


def save_agent_run(run: dict[str, Any]) -> int:
    """Guarda una corrida del agente y devuelve su id."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_runs
                (company_id, started_at, date_from, fetched, inserted, evaluated,
                 alert_ids, report_alert_ids, email_sent, report_markdown, report_html, narrative)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["company_id"],
                run.get("started_at") or now_iso(),
                run.get("date_from"),
                int(run.get("fetched") or 0),
                int(run.get("inserted") or 0),
                int(run.get("evaluated") or 0),
                list_to_json(run.get("alert_ids") or []),
                list_to_json(run.get("report_alert_ids") or []),
                1 if run.get("email_sent") else 0,
                run.get("report_markdown") or "",
                run.get("report_html") or "",
                json.dumps(run.get("narrative") or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_agent_runs(company_id: int) -> list[dict[str, Any]]:
    """Metadata de las corridas visibles (sin el markdown, para listar el historial)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, company_id, started_at, date_from, fetched, inserted,
                   evaluated, email_sent
            FROM agent_runs
            WHERE company_id = ? AND deleted_at IS NULL
            ORDER BY started_at DESC, id DESC
            """,
            (company_id,),
        ).fetchall()
    runs = []
    for row in rows:
        item = dict(row)
        item["email_sent"] = bool(item["email_sent"])
        runs.append(item)
    return runs


def get_agent_run(run_id: int) -> dict[str, Any] | None:
    """Una corrida completa, incluyendo el markdown del informe guardado.

    Las corridas eliminadas lógicamente se tratan como inexistentes."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE id = ? AND deleted_at IS NULL", (run_id,)
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["email_sent"] = bool(item["email_sent"])
    item["alert_ids"] = decode_json_list(item.get("alert_ids"))
    # Alertas que el informe cubre. En modo relativo coincide con las evaluadas en la
    # corrida; en modo rango incluye además las ya evaluadas antes dentro de la ventana.
    # Las corridas previas a esta columna caen a alert_ids, que era el criterio de render.
    item["report_alert_ids"] = decode_json_list(item.get("report_alert_ids")) or item["alert_ids"]
    try:
        narrative = json.loads(item.get("narrative") or "{}")
    except (json.JSONDecodeError, TypeError):
        narrative = {}
    item["narrative"] = narrative if isinstance(narrative, dict) else {}
    return item


def soft_delete_agent_run(run_id: int) -> bool:
    """Marca una corrida como eliminada para que no aparezca en el historial.

    La fila se conserva (informe, narrativa y alertas evaluadas quedan intactos).
    Devuelve False si la corrida no existe o ya estaba eliminada."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE agent_runs SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (now_iso(), run_id),
        )
        conn.commit()
        return cursor.rowcount > 0
