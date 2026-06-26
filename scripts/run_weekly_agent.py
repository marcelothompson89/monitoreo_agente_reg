"""
Entry point para ejecutar el agente semanal desde la línea de comandos o un scheduler.

Uso:
    python scripts/run_weekly_agent.py
    python scripts/run_weekly_agent.py --company-id 1

Scheduling en Windows Task Scheduler:
    Programa: python
    Argumentos: C:\ruta\al\proyecto\scripts\run_weekly_agent.py
    Frecuencia: Semanal, viernes 18:00
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend.db import init_db
from backend.weekly_agent import run_weekly_agent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecutar agente de monitoreo regulatorio")
    parser.add_argument("--company-id", type=int, default=None, help="ID de empresa (omitir para todas)")
    args = parser.parse_args()

    print("Iniciando agente de monitoreo regulatorio...")
    init_db()

    results = run_weekly_agent(args.company_id)

    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    errors = [r for r in results if r.get("error")]
    sys.exit(1 if errors else 0)
