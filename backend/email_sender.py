import html as html_lib
import os
import re
from datetime import datetime
from typing import Any


def _md_to_html(md: str) -> str:
    # Escapar primero el contenido dinámico (puede traer < > & " de las alertas).
    # No rompe el markdown: escapeHtml no toca #, *, - usados por el formato.
    html = html_lib.escape(md, quote=False)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", html, flags=re.DOTALL)
    html = re.sub(r"(?m)^(?!<[hul]).+$", lambda m: f"<p>{m.group(0)}</p>" if m.group(0).strip() else "", html)
    return html


def _build_html(company_name: str, report_html: str, summary: dict[str, Any], fecha: str) -> str:
    safe_name = html_lib.escape(company_name or "tu empresa")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color: #1f2933; max-width: 720px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 22px; color: #176b62; }}
  h2 {{ font-size: 17px; border-bottom: 1px solid #d9e0e6; padding-bottom: 4px; margin-top: 24px; }}
  h3 {{ font-size: 14px; margin-top: 16px; }}
  .metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
  .metric {{ background: #eef3f1; border-radius: 8px; padding: 12px 16px; text-align: center; min-width: 100px; }}
  .metric-value {{ display: block; font-size: 28px; font-weight: 800; color: #176b62; }}
  .metric-label {{ font-size: 11px; color: #65717d; font-weight: 700; }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
  p {{ margin: 6px 0; }}
  .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #d9e0e6; font-size: 12px; color: #65717d; }}
</style>
</head>
<body>
<h1>Informe regulatorio semanal — {safe_name}</h1>
<p style="color:#65717d">{fecha}</p>

<div class="metrics">
  <div class="metric"><span class="metric-value">{summary.get("total_alerts", 0)}</span><span class="metric-label">Alertas analizadas</span></div>
  <div class="metric"><span class="metric-value">{summary.get("relevant_alerts", 0)}</span><span class="metric-label">Relevantes</span></div>
  <div class="metric"><span class="metric-value">{summary.get("priority_high", 0)}</span><span class="metric-label">Prioridad alta</span></div>
  <div class="metric"><span class="metric-value">{summary.get("requires_human_review", 0)}</span><span class="metric-label">Revisión humana</span></div>
</div>

{report_html}

<div class="footer">
  Informe generado automáticamente para {safe_name} por el Agente de Monitoreo Regulatorio.
</div>
</body>
</html>"""


def send_report_email(
    to_emails: list[str],
    company_name: str,
    report_markdown: str,
    summary: dict[str, Any],
) -> bool:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("[email_sender] RESEND_API_KEY no configurada — email omitido.")
        return False

    if not to_emails:
        print("[email_sender] Sin destinatarios configurados — email omitido.")
        return False

    try:
        import resend
        resend.api_key = api_key
    except ImportError:
        print("[email_sender] Librería 'resend' no instalada — ejecutá pip install resend")
        return False

    fecha = datetime.utcnow().strftime("%d/%m/%Y")
    report_html = _md_to_html(report_markdown)
    html_body = _build_html(company_name, report_html, summary, fecha)

    try:
        resend.Emails.send({
            "from": os.getenv("RESEND_FROM_EMAIL", "alertas@agenteregulatorio.com"),
            "to": to_emails,
            "subject": f"Informe regulatorio semanal — {company_name} — {fecha}",
            "html": html_body,
        })
        print(f"[email_sender] Email enviado a {to_emails}")
        return True
    except Exception as exc:
        print(f"[email_sender] Error al enviar email: {exc}")
        return False
