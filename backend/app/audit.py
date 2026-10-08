"""REQ-10: bitácora de auditoría y notificaciones al gestor."""
import json

from . import db

EXECUTOR = "Agente Ejecutor"
REVIEWER = "Agente Revisor"
APPROVER = "Agente Aprobador"
SYSTEM = "Sistema"


def log(actor: str, action: str, entity: str | None = None, entity_id=None,
        details: dict | None = None, actor_type: str | None = None) -> None:
    if actor_type is None:
        actor_type = "agente" if actor.startswith("Agente") else ("sistema" if actor == SYSTEM else "humano")
    db.insert("audit_log", {
        "ts": db.now_iso(),
        "actor": actor,
        "actor_type": actor_type,
        "action": action,
        "entity": entity,
        "entity_id": None if entity_id is None else str(entity_id),
        "details_json": json.dumps(details or {}, ensure_ascii=False, default=str),
    })


def notify(level: str, title: str, body: str = "", entity: str | None = None, entity_id=None) -> None:
    db.insert("notifications", {
        "created_at": db.now_iso(),
        "level": level,
        "title": title,
        "body": body,
        "entity": entity,
        "entity_id": None if entity_id is None else str(entity_id),
    })
