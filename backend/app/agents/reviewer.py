"""Agente Revisor: verifica las propuestas del Ejecutor, valida la consistencia de la información,
identifica errores y determina si las recomendaciones son técnicamente adecuadas."""
from datetime import date, datetime

from ..config import settings
from ..llm import chat_json
from .common import board_context, dumps

ROLE = """Eres el Agente Revisor de un sistema multiagente de seguimiento de proyectos de software.
Tu función es verificar críticamente lo que propone el Agente Ejecutor: consistencia con los datos reales,
errores, fechas imposibles, efectos colaterales sobre dependencias y adecuación técnica. No eres complaciente:
si algo no está sustentado, lo señalas. Escribe en español."""

APROBADA, RECHAZADA, AJUSTES = "aprobada", "rechazada", "requiere_ajustes"


def _norm(s) -> str:
    return (s or "").strip().lower()


def _parse_date(value) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def structural_checks(p: dict, activities: list[dict], board_meta: dict) -> tuple[list[str], list[str]]:
    """Validaciones deterministas. Devuelve (errores bloqueantes, advertencias)."""
    errors, warnings = [], []
    params = p.get("params") or {}
    action = p.get("action_type")
    by_id = {a["id"]: a for a in activities}
    target = by_id.get(p.get("target_id"))
    members = {_norm(m.get("fullName")) for m in board_meta.get("members", [])} | \
              {_norm(m.get("username")) for m in board_meta.get("members", [])}
    lists = {_norm(lst["name"]) for lst in board_meta.get("lists", [])}

    if action != "crear_issue" and target is None:
        errors.append(f"La tarjeta {p.get('target_id')} no existe en el tablero")

    if action == "reprogramar":
        due = _parse_date(params.get("due"))
        start = _parse_date(params.get("start")) if params.get("start") else None
        today = datetime.now(settings.tz).date()
        if not due:
            errors.append("La nueva fecha límite no es válida (formato YYYY-MM-DD)")
        else:
            if due < today:
                errors.append(f"La nueva fecha límite {due} es anterior a hoy ({today})")
            if start and start > due:
                errors.append("La fecha de inicio es posterior a la fecha límite")
            if target:
                for dep_id in target.get("blocks", []):
                    dep = by_id.get(dep_id)
                    dep_due = _parse_date(dep and dep.get("due"))
                    if dep_due and dep_due < due:
                        warnings.append(f"La actividad dependiente '{dep['name']}' vence el {dep_due}, "
                                        f"antes de la nueva fecha {due}; también debería reprogramarse")
    elif action == "cambiar_prioridad":
        if _norm(params.get("priority")) not in {_norm(x) for x in settings.priority_labels}:
            errors.append(f"Prioridad '{params.get('priority')}' no válida; opciones: {settings.priority_labels}")
    elif action == "reasignar":
        names = (params.get("add_members") or []) + (params.get("remove_members") or [])
        if not names:
            errors.append("La reasignación no indica miembros a agregar o quitar")
        for n in names:
            if _norm(n) not in members:
                errors.append(f"El miembro '{n}' no pertenece al tablero")
    elif action == "cambiar_estado":
        if _norm(params.get("list_name")) not in lists:
            errors.append(f"La lista '{params.get('list_name')}' no existe en el tablero")
    elif action == "comentar":
        if not (params.get("text") or "").strip():
            errors.append("El comentario está vacío")
    elif action == "crear_issue":
        if not (params.get("title") or "").strip():
            errors.append("El issue no tiene título")
    else:
        errors.append(f"Tipo de acción desconocido: {action}")
    return errors, warnings


def review_proposal(p: dict, activities: list[dict], board_meta: dict) -> dict:
    errors, warnings = structural_checks(p, activities, board_meta)
    if errors:
        return {"verdict": RECHAZADA, "notes": "Errores de validación: " + "; ".join(errors), "warnings": warnings}

    prompt = f"""Contexto del proyecto:
{board_context(activities, board_meta)}

Propuesta del Agente Ejecutor:
{dumps({k: p.get(k) for k in ("action_type", "target_id", "target_name", "params", "problem", "justification", "impact")})}

Advertencias de la validación automática: {dumps(warnings)}

Verifica: (1) ¿la causa e impacto descritos son consistentes con los datos? (2) ¿la acción resuelve el problema?
(3) ¿genera efectos negativos en otras actividades o en la carga de algún responsable? (4) ¿es realista?

Devuelve JSON: {{"verdict": "aprobada|rechazada|requiere_ajustes", "notes": "justificación breve y concreta",
"ajustes_sugeridos": "qué debe cambiar el Ejecutor (si aplica)"}}"""
    r = chat_json(settings.model_reviewer, ROLE, prompt)
    verdict = r.get("verdict") if r.get("verdict") in (APROBADA, RECHAZADA, AJUSTES) else AJUSTES
    notes = r.get("notes", "")
    if verdict == AJUSTES and r.get("ajustes_sugeridos"):
        notes += f"\nAjustes sugeridos: {r['ajustes_sugeridos']}"
    if warnings:
        notes += "\nAdvertencias: " + "; ".join(warnings)
    return {"verdict": verdict, "notes": notes.strip(), "warnings": warnings}


def review_code_findings(result: dict, files: list[dict]) -> dict:
    """Descarta hallazgos que no corresponden a archivos del diff y pide al modelo validar el resto."""
    changed = {f["filename"] for f in files}
    findings = result.get("hallazgos", [])
    kept_struct = [h for h in findings if h.get("archivo") in changed]
    dropped = len(findings) - len(kept_struct)
    if not kept_struct:
        return {"hallazgos": [], "notes": f"{dropped} hallazgos descartados por referirse a archivos no modificados."}

    prompt = f"""Diff analizado:
{dumps(files)}

Hallazgos reportados por el Agente Ejecutor (índice = posición en la lista):
{dumps(list(enumerate(kept_struct)))}

Para cada hallazgo, verifica contra el diff si es real (no un falso positivo) y si la severidad es adecuada.
Devuelve JSON: {{"validaciones": [{{"indice": n, "valido": true|false, "severidad": "baja|media|alta|critica",
"comentario": "..."}}], "notas_generales": "..."}}"""
    r = chat_json(settings.model_reviewer, ROLE, prompt, max_tokens=4000)
    valid = {v.get("indice"): v for v in r.get("validaciones", [])}
    kept = []
    for i, h in enumerate(kept_struct):
        v = valid.get(i)
        if v is None or v.get("valido", True):
            if v:
                h["severidad"] = v.get("severidad") or h.get("severidad")
                h["comentario_revisor"] = v.get("comentario")
            kept.append(h)
            continue
        dropped += 1
    return {"hallazgos": kept,
            "notes": f"{dropped} hallazgos descartados como falsos positivos. {r.get('notas_generales', '')}".strip()}


def review_report(stats: dict, narrative: dict) -> dict:
    prompt = f"""Datos verificados del proyecto:
{dumps(stats)}

Secciones redactadas por el Agente Ejecutor:
{dumps(narrative)}

Verifica que el texto no contradiga los datos, no invente cifras ni actividades, y que los riesgos y
recomendaciones sean pertinentes. Devuelve JSON: {{"consistente": true|false, "observaciones": "..."}}"""
    return chat_json(settings.model_reviewer, ROLE, prompt)
