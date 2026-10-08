"""Agente Aprobador: recibe propuestas ya revisadas y determina si pueden ejecutarse,
aplicando las reglas de autorización de policy.json. Las decisiones de riesgo del modelo solo
informan; quien decide es la política (y, para cambios en la planificación, el gestor humano)."""
import json
from datetime import datetime

from ..config import settings
from ..llm import LLMError, chat_json
from .common import dumps

ROLE = """Eres el Agente Aprobador de un sistema multiagente de seguimiento de proyectos de software.
Evalúas el riesgo de ejecutar una acción ya revisada sobre la planificación (Trello) o el repositorio.
Escribe en español."""

AUTO = "auto_ejecutar"
GESTOR = "requiere_gestor"
DENEGADA = "denegada"
RISK_ORDER = {"bajo": 0, "medio": 1, "alto": 2}


def load_policy() -> dict:
    return json.loads(settings.policy_path.read_text(encoding="utf-8"))


def _shift_days(p: dict, target: dict | None) -> int | None:
    if p["action_type"] != "reprogramar" or not target or not target.get("due"):
        return None
    try:
        new = datetime.fromisoformat(str(p["params"]["due"])[:10]).date()
        old = datetime.fromisoformat(target["due"][:10]).date()
    except (KeyError, ValueError):
        return None
    return (new - old).days


def decide(p: dict, review: dict, target: dict | None) -> dict:
    policy = load_policy()
    action = p["action_type"]

    if review.get("verdict") != "aprobada":
        return {"decision": DENEGADA, "risk": "alto", "notes": "La propuesta no fue aprobada por el Agente Revisor."}
    if action in policy["prohibidas"] or action not in policy["acciones_permitidas"]:
        return {"decision": DENEGADA, "risk": "alto",
                "notes": f"La acción '{action}' no está permitida por la política de autorización."}

    rule_notes = []
    risk = "bajo"
    shift = _shift_days(p, target)
    if shift is not None and abs(shift) > policy["escalar_si_reprogramacion_mayor_a_dias"]:
        risk = "alto"
        rule_notes.append(f"Reprogramación de {shift} días supera el umbral de "
                          f"{policy['escalar_si_reprogramacion_mayor_a_dias']} días: se escala al gestor.")

    try:
        r = chat_json(settings.model_approver, ROLE, f"""Acción revisada:
{dumps({k: p.get(k) for k in ("action_type", "target_name", "params", "justification", "impact")})}
Observaciones del Revisor: {review.get('notes')}
Actividad afectada: {dumps(target)}

Evalúa el riesgo de ejecutarla (bajo/medio/alto) considerando reversibilidad, impacto en el cronograma y en el equipo.
Devuelve JSON: {{"riesgo": "bajo|medio|alto", "justificacion": "..."}}""")
        llm_risk = r.get("riesgo") if r.get("riesgo") in RISK_ORDER else "medio"
        rule_notes.append(r.get("justificacion", ""))
    except LLMError as e:
        llm_risk = "medio"
        rule_notes.append(f"No se pudo evaluar el riesgo con el modelo ({e}); se asume riesgo medio.")
    if RISK_ORDER[llm_risk] > RISK_ORDER[risk]:
        risk = llm_risk

    if action in policy["auto_ejecutables"] and RISK_ORDER[risk] <= RISK_ORDER[policy["auto_ejecucion_riesgo_maximo"]]:
        decision = AUTO
        rule_notes.insert(0, "Acción de bajo impacto autorizada automáticamente según la política.")
    else:
        decision = GESTOR
        rule_notes.insert(0, "La acción modifica la planificación o el repositorio: requiere autorización del gestor.")
    return {"decision": decision, "risk": risk, "notes": "\n".join(n for n in rule_notes if n)}
