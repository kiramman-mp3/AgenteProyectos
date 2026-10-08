"""Tareas periódicas: análisis de retrasos, revisión de código y reporte semanal."""
import logging
import os

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from . import audit, orchestrator
from .config import settings

log = logging.getLogger("agente.scheduler")
_scheduler: BackgroundScheduler | None = None


def _safe(name: str, fn):
    def job():
        try:
            result = fn()
            log.info("%s: %s", name, result)
        except orchestrator.BusyError:
            log.info("%s omitido: ya está en ejecución", name)
        except Exception as e:  # noqa: BLE001
            log.exception("%s falló", name)
            audit.log(audit.SYSTEM, f"tarea_fallida_{name}", details={"error": str(e)})
    return job


def start() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler:
        return
    _scheduler = BackgroundScheduler(timezone=settings.tz)
    _scheduler.add_job(_safe("analisis_retrasos", orchestrator.run_delay_analysis), "interval",
                       minutes=settings.analysis_interval_minutes, id="analysis")
    _scheduler.add_job(_safe("revision_codigo", orchestrator.run_code_review), "interval",
                       hours=settings.code_review_interval_hours, id="code")
    _scheduler.add_job(_safe("reporte_semanal", orchestrator.generate_weekly_report), "cron",
                       day_of_week=settings.report_day, hour=settings.report_hour, id="report")
    # En Render (plan gratuito) el servicio se duerme tras 15 min sin tráfico entrante: se hace ping a sí mismo
    # por su URL pública para que las tareas programadas sigan corriendo.
    public_url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if public_url:
        _scheduler.add_job(_keepalive, "interval", minutes=10, id="keepalive", args=[public_url.rstrip("/")])
    _scheduler.start()


def _keepalive(url: str) -> None:
    try:
        httpx.get(f"{url}/health", timeout=20)
    except httpx.HTTPError as e:
        log.warning("keepalive falló: %s", e)


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def jobs() -> list[dict]:
    if not _scheduler:
        return []
    return [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in _scheduler.get_jobs() if j.id != "keepalive"]
