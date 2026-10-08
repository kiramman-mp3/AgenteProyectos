"""REQ-08: orquestación del flujo multiagente  Ejecutor -> Revisor -> Aprobador -> Ejecución autorizada.
También coordina la sincronización con Trello, la revisión de código y el reporte semanal."""
import json
import threading
from datetime import datetime

from . import actions, audit, code_analysis, db, reports, tracking
from .agents import approver, executor, reviewer
from .audit import APPROVER, EXECUTOR, REVIEWER, SYSTEM
from .config import settings
from .integrations.github import GitHubClient
from .integrations.trello import TrelloClient

OPEN_STATUSES = ("en_revision", "pendiente_gestor", "modificacion_solicitada")
_locks = {name: threading.Lock() for name in ("analysis", "code", "report")}


class BusyError(RuntimeError):
    pass


def _exclusive(name: str):
    def wrap(fn):
        def inner(*args, **kwargs):
            if not _locks[name].acquire(blocking=False):
                raise BusyError(f"Ya hay un proceso de '{name}' en ejecución")
            try:
                return fn(*args, **kwargs)
            finally:
                _locks[name].release()
        inner.__name__ = fn.__name__
        return inner
    return wrap


# ---------------------------------------------------------------- Trello / seguimiento

def sync_board(actor: str = SYSTEM) -> dict:
    """REQ-01/02/03: consulta Trello, calcula estados/avance y detecta cambios en la planificación."""
    board = TrelloClient().fetch_board()
    activities = tracking.build_activities(board)
    summary = tracking.summarize(activities)
    snap = tracking.snapshot(board)

    prev = db.query_one("SELECT data_json FROM board_snapshots ORDER BY id DESC LIMIT 1")
    changes = tracking.diff_snapshots(json.loads(prev["data_json"]), snap) if prev else []
    if not prev or changes:
        db.insert("board_snapshots", {"taken_at": db.now_iso(), "data_json": json.dumps(snap, ensure_ascii=False)})
    for ch in changes:
        db.insert("plan_changes", {"detected_at": db.now_iso(), **ch})
    if changes:
        audit.log(EXECUTOR, "cambios_planificacion_detectados", "tablero", settings.trello_board_id,
                  {"total": len(changes), "cambios": changes[:20]})
        audit.notify("info", f"{len(changes)} cambios en la planificación",
                     "; ".join(f"{c['card_name']}: {c['field']}" for c in changes[:5]), "cambios")

    # Notificar actividades que acaban de pasar a retrasada o bloqueada.
    prev_status = db.kv_get("activity_status", {})
    for a in activities:
        if a["status"] in (tracking.RETRASADA, tracking.BLOQUEADA) and prev_status.get(a["id"]) != a["status"]:
            audit.notify("critico", f"Actividad {a['status']}: {a['name']}",
                         f"Fase/lista: {a['list']}\n"
                         f"Responsables: {', '.join(a['responsables']) or 'sin asignar'}\n"
                         f"Fecha límite: {(a['due'] or 'sin fecha')[:10]}\n"
                         f"Motivos: {'; '.join(a['risk_reasons']) or a['status']}\n"
                         f"Impacta a {len(a['blocks'])} actividad(es) dependiente(s)\n"
                         f"Tarjeta: {a.get('url') or ''}", "actividad", a["id"])
    db.kv_set("activity_status", {a["id"]: a["status"] for a in activities})

    meta = {k: board[k] for k in ("lists", "members", "labels")}
    meta.update(name=board["board"]["name"], url=board["board"].get("url"))
    db.kv_set("board_meta", meta)
    db.kv_set("activities", activities)
    db.kv_set("summary", summary)
    db.kv_set("last_sync", db.now_iso())
    audit.log(actor, "sincronizar_tablero", "tablero", settings.trello_board_id,
              {"actividades": summary["total"], "cambios": len(changes)})
    return {"summary": summary, "changes": len(changes)}


def state() -> tuple[list[dict], dict]:
    activities, meta = db.kv_get("activities"), db.kv_get("board_meta")
    if activities is None or meta is None:
        sync_board()
        activities, meta = db.kv_get("activities"), db.kv_get("board_meta")
    return activities, meta


# ---------------------------------------------------------------- Propuestas

def get_proposal(pid: int) -> dict | None:
    p = db.query_one("SELECT * FROM proposals WHERE id = ?", (pid,))
    if p:
        p["params"] = json.loads(p.pop("params_json"))
    return p


def _create_proposal(source: str, group_key: str, target: dict | None, alt: dict, problem: str = "",
                     impact: str = "", revision_of: int | None = None) -> int:
    pid = db.insert("proposals", {
        "created_at": db.now_iso(), "updated_at": db.now_iso(), "source": source, "group_key": group_key,
        "action_type": alt.get("action_type"), "target_id": target["id"] if target else None,
        "target_name": target["name"] if target else alt.get("target_name"),
        "params_json": json.dumps(alt.get("params") or {}, ensure_ascii=False),
        "problem": problem, "justification": alt.get("justificacion"),
        "impact": alt.get("impacto_esperado") or impact, "status": "en_revision", "revision_of": revision_of,
    })
    audit.log(EXECUTOR, "proponer_accion", "propuesta", pid,
              {"accion": alt.get("action_type"), "actividad": target and target["name"], "params": alt.get("params")})
    return pid


def _set(pid: int, **fields) -> None:
    db.update("proposals", pid, {**fields, "updated_at": db.now_iso()})


def process_proposal(pid: int, activities: list[dict], meta: dict, allow_revision: bool = True) -> str:
    """Lleva una propuesta por Revisor y Aprobador. Devuelve el estado final."""
    p = get_proposal(pid)
    review = reviewer.review_proposal(p, activities, meta)
    audit.log(REVIEWER, f"revision_{review['verdict']}", "propuesta", pid, {"notas": review["notes"]})

    if review["verdict"] == reviewer.AJUSTES and allow_revision:
        revised = executor.revise_proposal(p, review["notes"], activities, meta)
        _set(pid, action_type=revised.get("action_type", p["action_type"]),
             params_json=json.dumps(revised.get("params", p["params"]), ensure_ascii=False),
             justification=revised.get("justificacion", p["justification"]),
             impact=revised.get("impacto_esperado", p["impact"]))
        audit.log(EXECUTOR, "corregir_propuesta", "propuesta", pid, {"cambios": revised.get("cambios_realizados")})
        p = get_proposal(pid)
        review = reviewer.review_proposal(p, activities, meta)
        audit.log(REVIEWER, f"revision_{review['verdict']}", "propuesta", pid, {"notas": review["notes"]})

    _set(pid, reviewer_verdict=review["verdict"], reviewer_notes=review["notes"])
    if review["verdict"] != reviewer.APROBADA:
        _set(pid, status="rechazada_revisor")
        return "rechazada_revisor"

    target = next((a for a in activities if a["id"] == p["target_id"]), None)
    decision = approver.decide(p, review, target)
    audit.log(APPROVER, f"decision_{decision['decision']}", "propuesta", pid,
              {"riesgo": decision["risk"], "notas": decision["notes"]})
    _set(pid, approver_decision=decision["decision"], approver_risk=decision["risk"], approver_notes=decision["notes"])

    if decision["decision"] == approver.DENEGADA:
        _set(pid, status="denegada_aprobador")
        return "denegada_aprobador"
    if decision["decision"] == approver.AUTO:
        _set(pid, status="auto_aprobada", decided_at=db.now_iso(), manager=APPROVER)
        return execute_proposal(pid, APPROVER)

    _set(pid, status="pendiente_gestor")
    audit.notify("advertencia", f"Propuesta #{pid} requiere tu autorización",
                 f"{p['action_type']} — {p['target_name'] or 'repositorio'}", "propuesta", pid)
    return "pendiente_gestor"


def execute_proposal(pid: int, actor: str) -> str:
    p = get_proposal(pid)
    activities, meta = state()
    target = next((a for a in activities if a["id"] == p["target_id"]), None)
    try:
        result = actions.execute(p, meta, target)
    except Exception as e:  # noqa: BLE001 — cualquier fallo se registra y se informa
        _set(pid, status="fallida", execution_result=str(e), executed_at=db.now_iso())
        audit.log(actor, "ejecucion_fallida", "propuesta", pid, {"error": str(e)})
        audit.notify("critico", f"Falló la ejecución de la propuesta #{pid}", str(e)[:200], "propuesta", pid)
        return "fallida"

    _set(pid, status="ejecutada", execution_result=result, executed_at=db.now_iso())
    audit.log(actor, "accion_ejecutada", "propuesta", pid, {"resultado": result, "accion": p["action_type"]})
    # Las acciones autoejecutables (p. ej. comentarios) son complementarias: no descartan alternativas.
    if p["group_key"] and p["action_type"] not in approver.load_policy()["auto_ejecutables"]:
        for other in db.query("SELECT id FROM proposals WHERE group_key = ? AND id != ? AND status = 'pendiente_gestor'",
                              (p["group_key"], pid)):
            _set(other["id"], status="descartada", execution_result=f"Se ejecutó la alternativa #{pid}")
            audit.log(SYSTEM, "alternativa_descartada", "propuesta", other["id"], {"por": pid})
    audit.notify("info", f"Propuesta #{pid} ejecutada", result, "propuesta", pid)
    try:
        sync_board(actor)
    except Exception:  # noqa: BLE001 — la sincronización posterior es opcional
        pass
    return "ejecutada"


@_exclusive("analysis")
def run_delay_analysis(actor: str = SYSTEM) -> dict:
    """REQ-04/05: detecta retrasos y riesgos, y genera alternativas correctivas que pasan por el flujo multiagente."""
    sync_board(actor)
    activities, meta = state()
    policy = approver.load_policy()
    open_targets = {r["target_id"] for r in db.query(
        f"SELECT target_id FROM proposals WHERE status IN ({','.join('?' * len(OPEN_STATUSES))})", OPEN_STATUSES)}
    problems = [a for a in tracking.problem_activities(activities) if a["id"] not in open_targets]
    problems = problems[:policy["max_propuestas_por_analisis"]]
    audit.log(EXECUTOR, "detectar_retrasos", "tablero", settings.trello_board_id,
              {"problemas": [a["name"] for a in problems]})
    if not problems:
        return {"problemas": 0, "propuestas": 0}

    analyses = executor.propose_corrective_actions(problems, activities, meta)
    by_id = {a["id"]: a for a in activities}
    results = []
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    for an in analyses:
        target = by_id.get(an.get("card_id"))
        if not target:
            audit.log(REVIEWER, "analisis_descartado", "tarjeta", an.get("card_id"), {"motivo": "tarjeta inexistente"})
            continue
        for alt in an.get("alternativas", [])[:3]:
            pid = _create_proposal("retraso", f"{target['id']}:{stamp}", target, alt,
                                   an.get("causa_probable", ""), an.get("impacto", ""))
            results.append({"id": pid, "estado": process_proposal(pid, activities, meta)})
    return {"problemas": len(problems), "propuestas": len(results), "detalle": results}


# ---------------------------------------------------------------- Decisiones del gestor (REQ-09)

def _require_pending(pid: int) -> dict:
    p = get_proposal(pid)
    if not p:
        raise LookupError(f"La propuesta #{pid} no existe")
    if p["status"] != "pendiente_gestor":
        raise ValueError(f"La propuesta #{pid} no está pendiente de decisión (estado: {p['status']})")
    return p


def manager_approve(pid: int, user: str, comment: str | None = None) -> str:
    _require_pending(pid)
    _set(pid, status="aprobada", manager=user, manager_comment=comment, decided_at=db.now_iso())
    audit.log(user, "gestor_aprueba", "propuesta", pid, {"comentario": comment}, actor_type="humano")
    return execute_proposal(pid, user)


def manager_reject(pid: int, user: str, comment: str | None = None) -> str:
    _require_pending(pid)
    _set(pid, status="rechazada_gestor", manager=user, manager_comment=comment, decided_at=db.now_iso())
    audit.log(user, "gestor_rechaza", "propuesta", pid, {"comentario": comment}, actor_type="humano")
    return "rechazada_gestor"


def manager_request_changes(pid: int, user: str, comment: str) -> None:
    p = _require_pending(pid)
    _set(pid, status="modificacion_solicitada", manager=user, manager_comment=comment, decided_at=db.now_iso())
    audit.log(user, "gestor_solicita_modificacion", "propuesta", pid, {"comentario": comment}, actor_type="humano")
    threading.Thread(target=_revise_for_manager, args=(p, comment), daemon=True).start()


def _revise_for_manager(p: dict, comment: str) -> None:
    activities, meta = state()
    target = next((a for a in activities if a["id"] == p["target_id"]), None)
    try:
        revised = executor.revise_proposal(p, f"Solicitud del gestor del proyecto: {comment}", activities, meta)
        new_id = _create_proposal(p["source"], p["group_key"], target,
                                  {**revised, "target_name": p["target_name"]}, p["problem"], p["impact"], p["id"])
        audit.log(EXECUTOR, "propuesta_revisada_por_solicitud", "propuesta", new_id, {"original": p["id"]})
        process_proposal(new_id, activities, meta)
    except Exception as e:  # noqa: BLE001
        audit.log(SYSTEM, "error_revision", "propuesta", p["id"], {"error": str(e)})
        audit.notify("critico", f"No se pudo revisar la propuesta #{p['id']}", str(e)[:200], "propuesta", p["id"])


# ---------------------------------------------------------------- Revisión de código (REQ-07)

@_exclusive("code")
def run_code_review(actor: str = SYSTEM) -> dict:
    gh = GitHubClient()
    sha_key = f"last_reviewed_sha:{gh.branch}"
    target = f"{gh.repo}@{gh.branch}"
    all_commits = gh.recent_commits(db.kv_get(sha_key))
    # Los merges repiten los cambios de los commits que integran: se omiten para no analizarlos dos veces.
    commits = [c for c in all_commits if len(c.get("parents", [])) <= 1][-10:]
    if not commits:
        if all_commits:
            db.kv_set(sha_key, all_commits[-1]["sha"])
        audit.log(EXECUTOR, "revision_codigo_sin_cambios", "repositorio", target)
        return {"commits": 0}
    details = [gh.commit_detail(c["sha"]) for c in commits]
    files = code_analysis.prepare_files(details)
    heuristics = code_analysis.static_checks(files)
    commit_info = [{"sha": c["sha"][:7], "autor": c["commit"]["author"]["name"],
                    "fecha": c["commit"]["author"]["date"], "mensaje": c["commit"]["message"][:200]} for c in commits]

    result = executor.review_code(commit_info, files, settings.standards_path.read_text(encoding="utf-8"), heuristics)
    audit.log(EXECUTOR, "analizar_codigo", "repositorio", target,
              {"commits": len(commits), "hallazgos": len(result.get("hallazgos", []))})
    validated = reviewer.review_code_findings(result, files)
    audit.log(REVIEWER, "validar_hallazgos_codigo", "repositorio", target,
              {"validos": len(validated["hallazgos"]), "notas": validated["notes"]})

    findings = validated["hallazgos"]
    rid = db.insert("code_reviews", {
        "created_at": db.now_iso(), "repo": target, "commit_from": commits[0]["sha"], "commit_to": commits[-1]["sha"],
        "commits_json": json.dumps(commit_info, ensure_ascii=False),
        "summary": result.get("resumen", "") + "\n\nRecomendaciones generales:\n" +
                   "\n".join(f"- {r}" for r in result.get("recomendaciones_generales", [])),
        "score": int(result.get("puntaje_calidad") or 0),
        "findings_json": json.dumps(findings, ensure_ascii=False), "review_notes": validated["notes"],
    })
    db.kv_set(sha_key, all_commits[-1]["sha"])

    severe = [h for h in findings if h.get("severidad") in ("alta", "critica")]
    audit.notify("critico" if severe else "info", f"Revisión de código: {len(findings)} hallazgos",
                 f"{len(severe)} de severidad alta/crítica. Puntaje {result.get('puntaje_calidad')}/100",
                 "revision_codigo", rid)
    if severe:
        body = "Hallazgos detectados por el agente de revisión (validados por el Agente Revisor):\n\n" + "\n".join(
            f"- **[{h['severidad']}] {h['archivo']}:{h.get('linea') or '?'}** — {h['descripcion']}\n"
            f"  - Recomendación: {h['recomendacion']}" for h in severe)
        alt = {"action_type": "crear_issue",
               "params": {"title": f"Revisión de código: {len(severe)} hallazgos de severidad alta/crítica",
                          "body": body},
               "justificacion": "Registrar los hallazgos graves para que el equipo los corrija mediante su "
                                "proceso normal de revisión (el agente no modifica el código).",
               "target_name": f"Repositorio {gh.repo}"}
        activities, meta = state()
        pid = _create_proposal("codigo", f"code:{rid}", None, alt, "Hallazgos graves en el código")
        process_proposal(pid, activities, meta, allow_revision=False)
    return {"commits": len(commits), "hallazgos": len(findings), "review_id": rid}


# ---------------------------------------------------------------- Reporte semanal (REQ-06)

@_exclusive("report")
def generate_weekly_report(actor: str = SYSTEM) -> int:
    try:
        sync_board(actor)
    except Exception as e:  # noqa: BLE001 — si Trello falla se usa el último estado conocido
        audit.log(SYSTEM, "sincronizacion_fallida", "tablero", settings.trello_board_id, {"error": str(e)})
    activities, meta = state()
    stats = reports.build_stats(activities, meta)

    narrative = executor.write_report_narrative(stats)
    audit.log(EXECUTOR, "redactar_reporte", "reporte")
    review = reviewer.review_report(stats, narrative)
    if not review.get("consistente", True):
        audit.log(REVIEWER, "reporte_inconsistente", "reporte", None, {"observaciones": review.get("observaciones")})
        narrative = executor.write_report_narrative(stats, review.get("observaciones"))
        review = reviewer.review_report(stats, narrative)
    audit.log(REVIEWER, "validar_reporte", "reporte", None, review)

    md = reports.render_markdown(stats, narrative, review.get("observaciones", ""))
    rid = db.insert("reports", {"created_at": db.now_iso(), "period_start": stats["periodo"]["inicio"],
                                "period_end": stats["periodo"]["fin"], "stats_json": json.dumps(stats, ensure_ascii=False),
                                "content_md": md, "review_notes": review.get("observaciones")})
    audit.log(APPROVER, "publicar_reporte", "reporte", rid,
              {"motivo": "Los reportes son de solo lectura; la política permite su publicación automática."})
    audit.notify("info", "Nuevo reporte semanal disponible",
                 f"Avance {stats['resumen']['progress_weighted']}%", "reporte", rid)
    return rid
