"""REQ-06: cálculo de cifras del reporte semanal (sin IA) y renderizado a Markdown."""
import json
from datetime import datetime, timedelta, timezone

from . import db
from .tracking import STATUSES, summarize

STATUS_TITLES = {
    "completada": "Completadas", "en_ejecucion": "En ejecución", "pendiente": "Pendientes",
    "retrasada": "Retrasadas", "bloqueada": "Bloqueadas",
}
PROPOSAL_GROUPS = {
    "propuestas": None,
    "aprobadas": ("aprobada", "auto_aprobada", "ejecutada", "fallida"),
    "rechazadas": ("rechazada_gestor", "rechazada_revisor", "denegada_aprobador"),
    "ejecutadas": ("ejecutada",),
    "pendientes_de_decision": ("pendiente_gestor",),
}


def build_stats(activities: list[dict], board_meta: dict, days: int = 7) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    since = start.isoformat(timespec="seconds")

    by_status = {
        s: [{"nombre": a["name"], "responsables": a["responsables"], "fecha_limite": a["due"],
             "avance": a["progress"], "motivos_riesgo": a["risk_reasons"]}
            for a in activities if a["status"] == s]
        for s in STATUSES
    }
    changes = db.query("SELECT card_name, field, old_value, new_value, detected_at FROM plan_changes "
                       "WHERE detected_at >= ? ORDER BY id", (since,))
    proposals = db.query("SELECT id, action_type, target_name, status, justification, manager_comment "
                         "FROM proposals WHERE created_at >= ? OR decided_at >= ? OR executed_at >= ?",
                         (since, since, since))
    acciones = {}
    for key, statuses in PROPOSAL_GROUPS.items():
        acciones[key] = [p for p in proposals if statuses is None or p["status"] in statuses]
    review = db.query_one("SELECT summary, score, findings_json FROM code_reviews WHERE created_at >= ? "
                          "ORDER BY id DESC LIMIT 1", (since,))
    code = None
    if review:
        findings = json.loads(review["findings_json"])
        code = {"resumen": review["summary"], "puntaje": review["score"], "hallazgos": len(findings),
                "hallazgos_graves": sum(1 for h in findings if h.get("severidad") in ("alta", "critica"))}

    return {
        "tablero": board_meta.get("name"),
        "periodo": {"inicio": start.date().isoformat(), "fin": end.date().isoformat()},
        "resumen": summarize(activities),
        "actividades_por_estado": by_status,
        "en_riesgo": [{"nombre": a["name"], "motivos": a["risk_reasons"], "fecha_limite": a["due"]}
                      for a in activities if a["at_risk"]],
        "cambios_planificacion": {"total": len(changes), "detalle": changes[:30]},
        "acciones_correctivas": {k: [{"id": p["id"], "accion": p["action_type"], "actividad": p["target_name"],
                                      "estado": p["status"]} for p in v] for k, v in acciones.items()},
        "revision_codigo": code,
    }


def render_markdown(stats: dict, narrative: dict, review_notes: str) -> str:
    r = stats["resumen"]
    lines = [
        f"# Reporte semanal — {stats['tablero']}",
        f"**Periodo:** {stats['periodo']['inicio']} al {stats['periodo']['fin']}",
        "",
        "## Resumen ejecutivo",
        narrative.get("resumen_ejecutivo", ""),
        "",
        "## Avance del proyecto",
        f"- **Avance ponderado:** {r['progress_weighted']}%",
        f"- **Actividades completadas:** {r['progress_completed']}% ({r['counts']['completada']} de {r['total']})",
        "",
        "| Estado | Cantidad |",
        "|---|---|",
    ]
    lines += [f"| {STATUS_TITLES[s]} | {r['counts'][s]} |" for s in STATUSES]
    for s in ("retrasada", "bloqueada", "en_ejecucion", "pendiente", "completada"):
        items = stats["actividades_por_estado"][s]
        if items:
            lines += ["", f"### {STATUS_TITLES[s]}"]
            lines += [f"- {a['nombre']} — {', '.join(a['responsables']) or 'sin responsable'}"
                      f"{' — vence ' + a['fecha_limite'][:10] if a['fecha_limite'] else ''}" for a in items]

    lines += ["", "## Riesgos identificados"]
    for rk in narrative.get("riesgos", []) or []:
        lines.append(f"- **{rk.get('riesgo')}** (probabilidad {rk.get('probabilidad')}): {rk.get('impacto')}. "
                     f"*Mitigación:* {rk.get('mitigacion')}")
    lines += ["", "## Desviaciones respecto de la planificación"]
    lines += [f"- {d}" for d in narrative.get("desviaciones", []) or []]
    ch = stats["cambios_planificacion"]
    lines.append(f"- Cambios detectados en la planificación esta semana: **{ch['total']}**")

    lines += ["", "## Acciones correctivas", "| Categoría | Cantidad |", "|---|---|"]
    ac = stats["acciones_correctivas"]
    lines += [f"| {k.replace('_', ' ').capitalize()} | {len(v)} |" for k, v in ac.items()]
    for p in ac["propuestas"]:
        lines.append(f"- #{p['id']} {p['accion']} — {p['actividad'] or 'repositorio'} → *{p['estado']}*")

    if stats["revision_codigo"]:
        rc = stats["revision_codigo"]
        lines += ["", "## Calidad del código",
                  f"- Puntaje de calidad: **{rc['puntaje']}/100**",
                  f"- Hallazgos: {rc['hallazgos']} ({rc['hallazgos_graves']} de severidad alta o crítica)",
                  f"- {rc['resumen']}"]

    lines += ["", "## Recomendaciones para la siguiente semana"]
    lines += [f"{i}. {rec}" for i, rec in enumerate(narrative.get("recomendaciones_siguiente_semana", []) or [], 1)]
    lines += ["", "---", f"*Validación del Agente Revisor:* {review_notes}"]
    return "\n".join(lines)
