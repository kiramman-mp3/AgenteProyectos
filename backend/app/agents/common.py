"""Contexto y definiciones compartidas por los tres agentes."""
import json
from datetime import datetime

from ..config import settings

ACTION_SPEC = """Tipos de acción disponibles (action_type -> params):
- "reprogramar": {"due": "YYYY-MM-DD", "start": "YYYY-MM-DD" (opcional)}  -> cambia fechas de la tarjeta
- "cambiar_prioridad": {"priority": una de %(priorities)s}
- "reasignar": {"add_members": [nombres], "remove_members": [nombres]}  -> usa nombres exactos de la lista de miembros
- "cambiar_estado": {"list_name": nombre exacto de una lista del tablero}
- "comentar": {"text": "comentario para el equipo en la tarjeta"}
- "crear_issue": {"title": "...", "body": "..."}  -> crea un issue en GitHub (nunca se modifica código directamente)
""" % {"priorities": settings.priority_labels}


def today_local() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m-%d (%A)")


def compact_activity(a: dict) -> dict:
    return {k: a[k] for k in ("id", "name", "list", "status", "priority", "responsables", "start", "due",
                              "days_left", "progress", "risk_reasons", "depends_on", "blocks", "description")}


def board_context(activities: list[dict], board_meta: dict) -> str:
    ctx = {
        "fecha_actual": today_local(),
        "tablero": board_meta.get("name"),
        "listas": [lst["name"] for lst in board_meta.get("lists", [])],
        "miembros": [m.get("fullName") or m.get("username") for m in board_meta.get("members", [])],
        "prioridades": settings.priority_labels,
        "actividades": [compact_activity(a) for a in activities],
    }
    return json.dumps(ctx, ensure_ascii=False, indent=1)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
