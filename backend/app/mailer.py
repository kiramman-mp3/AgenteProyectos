"""REQ-09: envío de correos al gestor ante retrasos y eventos críticos.

Transportes (MAIL_TRANSPORT):
  smtp         Gmail u otro servidor SMTP con contraseña de aplicación (credencial cifrada 'smtp_password').
  apps_script  Webhook HTTPS de Google Apps Script que envía desde la cuenta de Gmail del gestor
               (credencial 'mail_webhook_secret'). Necesario en Render gratuito, que bloquea los puertos SMTP.
"""
import html
import logging
import smtplib
import threading
from email.message import EmailMessage

import httpx

from . import db
from .config import settings
from .security import get_secret

log = logging.getLogger("agente.mailer")
LEVEL_TITLE = {"critico": "🔴 Crítico", "advertencia": "🟠 Advertencia", "info": "ℹ️ Información"}


def enabled() -> bool:
    return settings.mail_transport in ("smtp", "apps_script")


def manager_emails() -> list[str]:
    rows = db.query("SELECT email FROM users WHERE active = 1 AND role IN ('gestor', 'admin') "
                    "AND email IS NOT NULL AND email != ''")
    return sorted({r["email"].strip() for r in rows})


def _render(level: str, title: str, body: str) -> tuple[str, str]:
    link = f"\n\nAbre la app para revisar el detalle: {settings.app_url}" if settings.app_url else ""
    text = f"{LEVEL_TITLE.get(level, level)}\n\n{title}\n\n{body}{link}\n\n— Agente de seguimiento de proyectos"
    html_body = (
        "<div style='font-family:Arial,sans-serif;max-width:560px'>"
        f"<p style='font-size:13px;color:#5E6C84'>{html.escape(LEVEL_TITLE.get(level, level))}</p>"
        f"<h2 style='color:#172B4D;margin:4px 0 12px'>{html.escape(title)}</h2>"
        f"<p style='color:#172B4D;white-space:pre-line'>{html.escape(body)}</p>"
        "<hr style='border:none;border-top:1px solid #DFE1E6'>"
        "<p style='font-size:12px;color:#5E6C84'>Agente de seguimiento de proyectos · "
        "notificación automática</p></div>"
    )
    return text, html_body


def send(to: list[str], subject: str, text: str, html_body: str | None = None) -> None:
    if settings.mail_transport == "smtp":
        msg = EmailMessage()
        msg["From"] = settings.smtp_user
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(text)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.login(settings.smtp_user, get_secret("smtp_password"))
            s.send_message(msg)
    elif settings.mail_transport == "apps_script":
        r = httpx.post(settings.mail_webhook_url, timeout=60, follow_redirects=True, json={
            "secret": get_secret("mail_webhook_secret"), "to": ", ".join(to),
            "subject": subject, "body": text, "htmlBody": html_body or ""})
        if r.status_code != 200 or '"ok":true' not in r.text.replace(" ", ""):
            raise RuntimeError(f"Apps Script respondió {r.status_code}: {r.text[:200]}")
    else:
        raise RuntimeError("Correo desactivado (MAIL_TRANSPORT vacío)")


def notify_managers_async(level: str, title: str, body: str) -> None:
    """Envía el aviso en segundo plano para no bloquear el análisis; el resultado queda en la bitácora."""
    if not enabled():
        return

    def run():
        from . import audit
        to = manager_emails()
        if not to:
            return
        text, html_body = _render(level, title, body)
        try:
            send(to, f"[Agente de proyectos] {title}", text, html_body)
            audit.log(audit.SYSTEM, "correo_enviado", "correo", None, {"para": to, "asunto": title})
        except Exception as e:  # noqa: BLE001 — un fallo de correo no debe interrumpir el agente
            log.warning("No se pudo enviar el correo: %s", e)
            audit.log(audit.SYSTEM, "correo_fallido", "correo", None, {"para": to, "error": str(e)[:300]})

    threading.Thread(target=run, daemon=True).start()
