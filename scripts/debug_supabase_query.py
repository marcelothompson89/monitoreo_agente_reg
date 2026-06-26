"""
Diagnóstico del filtro de fuentes contra Supabase.

Replica la consulta de backend/supabase_loader.fetch_alerts_for_company pero
mostrando el conteo en CADA etapa del filtro, para ver en qué paso se cae a cero.

Uso:
    venv\\Scripts\\python.exe scripts\\debug_supabase_query.py            # usa ILAR
    venv\\Scripts\\python.exe scripts\\debug_supabase_query.py --company "ILAR"
    venv\\Scripts\\python.exe scripts\\debug_supabase_query.py --company-id 5
    venv\\Scripts\\python.exe scripts\\debug_supabase_query.py --use-last-run   # emula el comportamiento viejo (piso = last_agent_run)

Requiere SUPABASE_URL y SUPABASE_KEY en .env (igual que el server).
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# Permitir importar el paquete backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.db import BASE_DIR, DB_PATH, decode_json_list
from backend.supabase_loader import _build_date_floor, _get_client

load_dotenv(BASE_DIR / ".env")

TABLE = "alertas_alerta"


def get_profile(company: str | None, company_id: int | None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if company_id is not None:
        row = conn.execute("SELECT * FROM company_profiles WHERE id = ?", (company_id,)).fetchone()
    elif company:
        row = conn.execute(
            "SELECT * FROM company_profiles WHERE company_name LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{company}%",),
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM company_profiles ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        sys.exit("No se encontró el perfil de empresa.")
    return dict(row)


def count(query) -> int:
    return len(query.execute().data or [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default="ILAR")
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--use-last-run", action="store_true",
                        help="Emula el comportamiento viejo: usa last_agent_run como piso de fecha")
    parser.add_argument("--days-back", type=int, default=None)
    args = parser.parse_args()

    profile = get_profile(args.company, args.company_id)
    countries = decode_json_list(profile.get("countries"))
    keywords = decode_json_list(profile.get("keywords"))
    alert_sources = decode_json_list(profile.get("alert_sources"))
    days_back = args.days_back if args.days_back is not None else int(profile.get("days_back") or 7)
    # Por defecto el agente ya NO usa last_agent_run como piso (la ventana es days_back).
    last_run = profile.get("last_agent_run") if args.use_last_run else None
    date_floor = _build_date_floor(days_back, last_run)

    print(f"Empresa        : {profile.get('company_name')} (id {profile.get('id')})")
    print(f"countries      : {countries}")
    print(f"keywords       : {keywords}")
    print(f"alert_sources  : {alert_sources}")
    print(f"last_agent_run : {profile.get('last_agent_run')}  (usado: {last_run})")
    print(f"date_floor     : {date_floor}  (presentation_date >= esto)")
    print("-" * 60)

    client = _get_client()

    def base():
        return client.table(TABLE).select("*").gte("presentation_date", date_floor).limit(1000)

    # Etapa 0: solo fecha
    print(f"[0] solo fecha (>= {date_floor})                : {count(base())}")

    # Etapa 1: + país
    q = base()
    if countries:
        q = q.in_("country", countries)
    print(f"[1] + país {countries}      : {count(q)}")

    # Etapa 2: + institución (fuente seleccionada)
    q2 = base()
    if countries:
        q2 = q2.in_("country", countries)
    if alert_sources:
        q2 = q2.in_("institution", alert_sources)
    print(f"[2] + institución {alert_sources} : {count(q2)}")

    # Etapa 3: + keywords (consulta REAL que usa el agente)
    q3 = base()
    if countries:
        q3 = q3.in_("country", countries)
    if alert_sources:
        q3 = q3.in_("institution", alert_sources)
    if keywords:
        or_parts = []
        for kw in keywords:
            kw = kw.strip()
            if kw:
                or_parts.append(f"title.ilike.%{kw}%")
                or_parts.append(f"description.ilike.%{kw}%")
        if or_parts:
            q3 = q3.or_(",".join(or_parts))
    print(f"[3] + keywords {keywords}  : {count(q3)}   <-- lo que trae el agente")
    print("-" * 60)

    # Diagnóstico extra: la institución ignorando fecha y keywords
    for src in (alert_sources or []):
        total = count(client.table(TABLE).select("*").eq("institution", src).limit(1000))
        print(f"[A] '{src}': total histórico (sin fecha ni keywords) = {total}")
        recientes = (
            client.table(TABLE)
            .select("presentation_date,country,title")
            .eq("institution", src)
            .order("presentation_date", desc=True)
            .limit(5)
            .execute()
        ).data or []
        for r in recientes:
            print(f"      {r.get('presentation_date')} | {r.get('country')} | {(r.get('title') or '')[:70]}")
        # ¿cuántas coinciden con alguna keyword?
        if keywords:
            qk = client.table(TABLE).select("*").eq("institution", src)
            or_parts = []
            for kw in keywords:
                kw = kw.strip()
                if kw:
                    or_parts.append(f"title.ilike.%{kw}%")
                    or_parts.append(f"description.ilike.%{kw}%")
            qk = qk.or_(",".join(or_parts)).limit(1000)
            print(f"      coinciden con keywords (sin filtro de fecha): {count(qk)}")


if __name__ == "__main__":
    main()
