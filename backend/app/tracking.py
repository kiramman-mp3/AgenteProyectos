"""REQ-01, REQ-02, REQ-03, REQ-04: modelo de actividades, estados, avance, riesgos y cambios en la planificación.

Las funciones de este módulo son deterministas (no usan IA) para que los cálculos sean verificables.
"""
import re
from datetime import datetime, timezone

from .config import settings

PENDIENTE = "pendiente"
EN_EJECUCION = "en_ejecucion"
COMPLETADA = "completada"
RETRASADA = "retrasada"
BLOQUEADA = "bloqueada"
STATUSES = (PENDIENTE, EN_EJECUCION, COMPLETADA, RETRASADA, BLOQUEADA)

_DEP_RE = re.compile(r"depende(?:\s+de)?\s*:\s*(.+)", re.I)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _in(name: str, options: list[str]) -> bool:
    return _norm(name) in {_norm(o) for o in options}


def _is_status_list(name: str) -> bool:
    return _in(name, settings.lists_pending + settings.lists_in_progress + settings.lists_done + settings.lists_blocked)


def _priority(card: dict) -> str | None:
    names = {_norm(lb.get("name")): lb.get("name") for lb in card.get("labels", [])}
    for p in settings.priority_labels:
        for candidate in (p, f"prioridad {p}", f"prioridad: {p}"):
            if _norm(candidate) in names:
                return p
    return None


def _checklist_progress(card: dict) -> float | None:
    items = [i for cl in card.get("checklists", []) for i in cl.get("checkItems", [])]
    if not items:
        return None
    return sum(1 for i in items if i.get("state") == "complete") / len(items)


def _dependencies(desc: str) -> list[str]:
    deps = []
    for line in (desc or "").splitlines():
        m = _DEP_RE.search(line)
        if m:
            deps += [d.strip().lstrip("#") for d in m.group(1).split(",") if d.strip()]
    return deps


def build_activities(board: dict, now: datetime | None = None) -> list[dict]:
    """Convierte las tarjetas de Trello en actividades con estado, progreso y riesgo."""
    now = now or datetime.now(timezone.utc)
    lists = {lst["id"]: lst["name"] for lst in board["lists"]}
    members = {m["id"]: m.get("fullName") or m.get("username") for m in board["members"]}
    by_short = {c["shortLink"]: c for c in board["cards"]}
    by_name = {_norm(c["name"]): c for c in board["cards"]}

    activities = []
    for card in board["cards"]:
        list_name = lists.get(card["idList"], "?")
        labels = [lb.get("name") or lb.get("color") for lb in card.get("labels", [])]
        due = _parse_dt(card.get("due"))
        start = _parse_dt(card.get("start"))
        checklist = _checklist_progress(card)
        done = bool(card.get("dueComplete")) or _in(list_name, settings.lists_done)
        blocked = _in(list_name, settings.lists_blocked) or any(_norm(lb) == _norm(settings.blocked_label) for lb in labels)
        # En tableros organizados por fases (listas que no indican estado) la ejecución se infiere de la fecha de inicio.
        if _is_status_list(list_name):
            in_progress = _in(list_name, settings.lists_in_progress)
        else:
            in_progress = bool(start and start <= now)

        if done:
            status = COMPLETADA
        elif blocked:
            status = BLOQUEADA
        elif due and due < now:
            status = RETRASADA
        elif in_progress:
            status = EN_EJECUCION
        else:
            status = PENDIENTE

        if status == COMPLETADA:
            progress = 1.0
        elif checklist is not None:
            progress = checklist
        else:
            progress = 0.5 if in_progress else 0.0

        # Riesgo de retraso: vence pronto o el avance va por detrás del tiempo transcurrido.
        risk_reasons = []
        days_left = None
        if due and status != COMPLETADA:
            days_left = round((due - now).total_seconds() / 86400, 1)
            if 0 <= days_left <= settings.risk_days:
                risk_reasons.append(f"vence en {days_left} días")
                if status == PENDIENTE:
                    risk_reasons.append("aún no ha iniciado")
            if start and due > start and start < now < due:
                elapsed = (now - start) / (due - start)
                if elapsed - progress > 0.3:
                    risk_reasons.append(f"tiempo transcurrido {elapsed:.0%} vs avance {progress:.0%}")
        if status == BLOQUEADA:
            risk_reasons.append("actividad bloqueada")

        deps = []
        for ref in _dependencies(card.get("desc", "")):
            dep = by_short.get(ref) or by_name.get(_norm(ref))
            if dep:
                deps.append(dep["id"])

        activities.append({
            "id": card["id"],
            "short_link": card["shortLink"],
            "url": card.get("url"),
            "name": card["name"],
            "list": list_name,
            "list_id": card["idList"],
            "responsables": [members.get(m, m) for m in card.get("idMembers", [])],
            "member_ids": card.get("idMembers", []),
            "labels": labels,
            "label_ids": card.get("idLabels", []),
            "priority": _priority(card),
            "start": start.isoformat() if start else None,
            "due": due.isoformat() if due else None,
            "days_left": days_left,
            "status": status,
            "progress": round(progress, 2),
            "at_risk": bool(risk_reasons) and status != COMPLETADA,
            "risk_reasons": risk_reasons,
            "depends_on": deps,
            "last_activity": card.get("dateLastActivity"),
            "description": (card.get("desc") or "")[:500],
        })

    # Impacto: actividades que dependen (directa o indirectamente) de cada una.
    dependents: dict[str, list[str]] = {a["id"]: [] for a in activities}
    for a in activities:
        for d in a["depends_on"]:
            dependents.setdefault(d, []).append(a["id"])
    for a in activities:
        seen, stack = set(), list(dependents.get(a["id"], []))
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack += dependents.get(x, [])
        a["blocks"] = sorted(seen)
    return activities


def summarize(activities: list[dict]) -> dict:
    """Avance general y conteos por estado."""
    total = len(activities)
    counts = {s: sum(1 for a in activities if a["status"] == s) for s in STATUSES}
    return {
        "total": total,
        "counts": counts,
        "progress_weighted": round(100 * sum(a["progress"] for a in activities) / total, 1) if total else 0.0,
        "progress_completed": round(100 * counts[COMPLETADA] / total, 1) if total else 0.0,
        "at_risk": sum(1 for a in activities if a["at_risk"] and a["status"] != RETRASADA),
    }


def problem_activities(activities: list[dict]) -> list[dict]:
    """Actividades retrasadas, bloqueadas o en riesgo (insumo para el Agente Ejecutor)."""
    return [a for a in activities if a["status"] in (RETRASADA, BLOQUEADA) or a["at_risk"]]


# ---------- Detección de cambios en la planificación ----------

def snapshot(board: dict) -> dict:
    lists = {lst["id"]: lst["name"] for lst in board["lists"]}
    members = {m["id"]: m.get("fullName") or m.get("username") for m in board["members"]}
    return {
        c["id"]: {
            "name": c["name"],
            "lista": lists.get(c["idList"], "?"),
            "fecha_limite": c.get("due"),
            "fecha_inicio": c.get("start"),
            "completada": bool(c.get("dueComplete")),
            "responsables": sorted(members.get(m, m) for m in c.get("idMembers", [])),
            "etiquetas": sorted((lb.get("name") or lb.get("color") or "") for lb in c.get("labels", [])),
        }
        for c in board["cards"]
    }


def diff_snapshots(old: dict, new: dict) -> list[dict]:
    changes = []
    for cid, card in new.items():
        if cid not in old:
            changes.append({"card_id": cid, "card_name": card["name"], "field": "tarjeta",
                            "old_value": None, "new_value": "creada"})
            continue
        for field, value in card.items():
            if old[cid].get(field) != value:
                changes.append({"card_id": cid, "card_name": card["name"], "field": field,
                                "old_value": _fmt(old[cid].get(field)), "new_value": _fmt(value)})
    for cid, card in old.items():
        if cid not in new:
            changes.append({"card_id": cid, "card_name": card["name"], "field": "tarjeta",
                            "old_value": "existente", "new_value": "archivada/eliminada"})
    return changes


def _fmt(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(v)
    return str(v)
