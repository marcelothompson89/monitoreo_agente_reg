import os
from datetime import datetime
from typing import Any

from .report_html import render_report_html


def send_report_email(
    to_emails: list[str],
    company_profile: dict[str, Any],
    summary: dict[str, Any],
    assessments: list[dict[str, Any]],
    narrative: dict[str, Any] | None = None,
) -> bool:
    """Envía el informe branded por email.

    El HTML se arma con `render_report_html` (plantilla determinista + branding del
    perfil + narrativa del LLM). El markdown ya no se usa para el email.
    """
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

    company_name = (company_profile or {}).get("company_name") or "tu empresa"
    fecha = datetime.utcnow().strftime("%d/%m/%Y")
    html_body = render_report_html(company_profile, summary, assessments, narrative)

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
