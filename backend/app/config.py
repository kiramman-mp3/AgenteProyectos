"""Configuración central leída desde variables de entorno (.env)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


class Settings:
    master_key: str = os.getenv("MASTER_KEY", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "12"))
    db_path: Path = BASE_DIR / os.getenv("DB_PATH", "data/agente.db")

    llm_provider: str = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
    model_executor: str = os.getenv("MODEL_EXECUTOR", "anthropic/claude-sonnet-4.5")
    model_reviewer: str = os.getenv("MODEL_REVIEWER", "openai/gpt-4.1-mini")
    model_approver: str = os.getenv("MODEL_APPROVER", "openai/gpt-4.1-mini")

    trello_board_id: str = os.getenv("TRELLO_BOARD_ID", "")
    lists_pending: list[str] = _list("LISTS_PENDING", "Pendiente,Por hacer,To Do,Backlog")
    lists_in_progress: list[str] = _list("LISTS_IN_PROGRESS", "En progreso,En ejecución,Doing,In Progress")
    lists_done: list[str] = _list("LISTS_DONE", "Hecho,Completado,Terminado,Done")
    lists_blocked: list[str] = _list("LISTS_BLOCKED", "Bloqueado,Blocked")
    blocked_label: str = os.getenv("BLOCKED_LABEL", "Bloqueado")
    priority_labels: list[str] = _list("PRIORITY_LABELS", "Alta,Media,Baja")

    github_repo: str = os.getenv("GITHUB_REPO", "")
    github_branch: str = os.getenv("GITHUB_BRANCH", "main")

    risk_days: int = int(os.getenv("RISK_DAYS", "3"))
    tz: ZoneInfo = ZoneInfo(os.getenv("TIMEZONE", "America/Guayaquil"))

    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    analysis_interval_minutes: int = int(os.getenv("ANALYSIS_INTERVAL_MINUTES", "60"))
    code_review_interval_hours: int = int(os.getenv("CODE_REVIEW_INTERVAL_HOURS", "24"))
    report_day: str = os.getenv("REPORT_DAY", "mon")
    report_hour: int = int(os.getenv("REPORT_HOUR", "8"))

    policy_path: Path = BASE_DIR / "policy.json"
    standards_path: Path = BASE_DIR / "standards.md"


settings = Settings()
