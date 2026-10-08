"""Ejecución de acciones AUTORIZADAS. Es el único módulo que escribe en Trello o GitHub, y solo
acepta propuestas en estado 'aprobada' (por el gestor) o con decisión automática del Aprobador.
Nunca modifica el código fuente: para el repositorio solo crea issues."""
from datetime import datetime

from .config import settings
from .integrations.github import GitHubClient
from .integrations.trello import PRIORITY_COLORS, TrelloClient

EXECUTABLE_STATUSES = {"aprobada", "auto_aprobada"}


class ExecutionError(RuntimeError):
    pass


def _norm(s) -> str:
    return (s or "").strip().lower()


def _to_trello_date(value: str) -> str:
    d = datetime.fromisoformat(str(value)[:10])
    # Fin de jornada local para la fecha límite.
    return d.replace(hour=18, tzinfo=settings.tz).isoformat()


def execute(p: dict, board_meta: dict, current_card: dict | None) -> str:
    if p["status"] not in EXECUTABLE_STATUSES:
        raise ExecutionError(f"La propuesta #{p['id']} no está autorizada (estado: {p['status']})")
    action, params, card_id = p["action_type"], p["params"], p.get("target_id")

    if action == "crear_issue":
        issue = GitHubClient().create_issue(params["title"], params.get("body", ""), params.get("labels"))
        return f"Issue creado: {issue.get('html_url')}"

    trello = TrelloClient()
    if action == "reprogramar":
        fields = {"due": _to_trello_date(params["due"])}
        if params.get("start"):
            fields["start"] = _to_trello_date(params["start"])
        trello.update_card(card_id, **fields)
        return f"Fecha límite actualizada a {params['due']}"

    if action == "cambiar_prioridad":
        prio_norm = {_norm(x) for x in settings.priority_labels}
        current_ids = (current_card or {}).get("label_ids", [])
        labels_by_id = {lb["id"]: lb for lb in board_meta.get("labels", [])}
        keep = [i for i in current_ids if _norm(labels_by_id.get(i, {}).get("name")) not in prio_norm]
        idx = [_norm(x) for x in settings.priority_labels].index(_norm(params["priority"]))
        new_id = trello.ensure_label(settings.priority_labels[idx], PRIORITY_COLORS.get(idx))
        trello.update_card(card_id, idLabels=",".join(keep + [new_id]))
        return f"Prioridad cambiada a {settings.priority_labels[idx]}"

    if action == "reasignar":
        ids_by_name = {}
        for m in board_meta.get("members", []):
            ids_by_name[_norm(m.get("fullName"))] = m["id"]
            ids_by_name[_norm(m.get("username"))] = m["id"]
        members = set((current_card or {}).get("member_ids", []))
        members |= {ids_by_name[_norm(n)] for n in params.get("add_members", [])}
        members -= {ids_by_name[_norm(n)] for n in params.get("remove_members", [])}
        trello.update_card(card_id, idMembers=",".join(sorted(members)))
        return f"Responsables actualizados (+{params.get('add_members', [])} -{params.get('remove_members', [])})"

    if action == "cambiar_estado":
        target = next(lst for lst in board_meta["lists"] if _norm(lst["name"]) == _norm(params["list_name"]))
        trello.update_card(card_id, idList=target["id"])
        return f"Tarjeta movida a la lista '{target['name']}'"

    if action == "comentar":
        trello.add_comment(card_id, f"🤖 Agente de seguimiento: {params['text']}")
        return "Comentario agregado en la tarjeta"

    raise ExecutionError(f"Acción no soportada: {action}")
