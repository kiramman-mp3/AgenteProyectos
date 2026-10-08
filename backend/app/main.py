"""API REST consumida por la app móvil del gestor del proyecto."""
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import audit, bootstrap, db, orchestrator, scheduler
from .config import settings
from .security import (ROLES, create_token, current_user, generate_password, hash_password, require,
                       secrets_status, verify_password)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.conn()
    bootstrap.run()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Agente de Seguimiento de Proyectos", version="1.0.0", lifespan=lifespan)


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: str = "desarrollador"


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: str | None = None
    active: bool | None = None


USER_FIELDS = "id, username, full_name, email, role, active, must_change_password, created_at"


class DecisionIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ChangesIn(BaseModel):
    comment: str = Field(min_length=3, max_length=2000)


def _background(name: str, fn, actor: str) -> dict:
    """Lanza un proceso largo (que usa IA) en segundo plano para no bloquear a la app."""
    def run():
        try:
            fn(actor)
        except orchestrator.BusyError:
            pass
        except Exception as e:  # noqa: BLE001
            audit.log(audit.SYSTEM, f"error_{name}", details={"error": str(e)})
            audit.notify("critico", f"Error en {name.replace('_', ' ')}", str(e)[:300])
    threading.Thread(target=run, daemon=True).start()
    return {"status": "iniciado", "proceso": name}


# ---------------------------------------------------------------- Autenticación

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/login")
def login(body: LoginIn):
    user = db.query_one("SELECT * FROM users WHERE username = ? AND active = 1", (body.username,))
    if not user or not verify_password(body.password, user["password_hash"]):
        audit.log(body.username, "login_fallido", "usuario", actor_type="humano")
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    audit.log(user["username"], "login", "usuario", user["id"], actor_type="humano")
    return {"token": create_token(user), "username": user["username"], "role": user["role"],
            "full_name": user.get("full_name"), "must_change_password": bool(user.get("must_change_password"))}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@app.post("/auth/change-password")
def change_password(body: PasswordChangeIn, user=Depends(current_user)):
    row = db.query_one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(400, "La contraseña actual no es correcta")
    if body.new_password == body.current_password:
        raise HTTPException(400, "La nueva contraseña debe ser distinta de la actual")
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
               (hash_password(body.new_password), user["id"]))
    audit.log(user["username"], "contrasena_cambiada", "usuario", user["id"], actor_type="humano")
    return {"ok": True}


# ---------------------------------------------------------------- Usuarios (REQ-11, solo gestor)

def _user_or_404(uid: int) -> dict:
    u = db.query_one(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (uid,))
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    return u


@app.get("/users")
def users_list(user=Depends(require("users"))):
    return db.query(f"SELECT {USER_FIELDS} FROM users ORDER BY role, username")


@app.post("/users")
def user_create(body: UserCreateIn, user=Depends(require("users"))):
    if body.role not in ROLES:
        raise HTTPException(400, f"Rol inválido; opciones: {', '.join(ROLES)}")
    if db.query_one("SELECT id FROM users WHERE username = ?", (body.username,)):
        raise HTTPException(409, f"El usuario '{body.username}' ya existe")
    temp = generate_password()
    uid = db.insert("users", {"username": body.username, "password_hash": hash_password(temp), "role": body.role,
                              "full_name": body.full_name or None, "email": body.email or None,
                              "must_change_password": 1, "created_at": db.now_iso()})
    audit.log(user["username"], "usuario_creado", "usuario", uid, {"usuario": body.username, "rol": body.role},
              actor_type="humano")
    return {**_user_or_404(uid), "temporary_password": temp}


@app.patch("/users/{uid}")
def user_update(uid: int, body: UserUpdateIn, user=Depends(require("users"))):
    target = _user_or_404(uid)
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(400, f"Rol inválido; opciones: {', '.join(ROLES)}")
    if target["id"] == user["id"] and (changes.get("active") is False or changes.get("role", "gestor") != "gestor"):
        raise HTTPException(400, "No puedes desactivarte ni quitarte el rol de gestor a ti mismo")
    if "active" in changes:
        changes["active"] = 1 if changes["active"] else 0
    for k in ("full_name", "email"):
        if k in changes and not changes[k]:
            changes[k] = None
    if changes:
        db.update("users", uid, changes)
        audit.log(user["username"], "usuario_actualizado", "usuario", uid,
                  {"usuario": target["username"], **changes}, actor_type="humano")
    return _user_or_404(uid)


@app.post("/users/{uid}/reset-password")
def user_reset_password(uid: int, user=Depends(require("users"))):
    target = _user_or_404(uid)
    temp = generate_password()
    db.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?", (hash_password(temp), uid))
    audit.log(user["username"], "contrasena_restablecida", "usuario", uid, {"usuario": target["username"]},
              actor_type="humano")
    return {"username": target["username"], "temporary_password": temp}


# ---------------------------------------------------------------- Seguimiento

@app.get("/dashboard")
def dashboard(user=Depends(require("read"))):
    meta = db.kv_get("board_meta", {}) or {}
    activities = db.kv_get("activities", []) or []
    return {
        "board": {"name": meta.get("name"), "url": meta.get("url")},
        "summary": db.kv_get("summary"),
        "last_sync": db.kv_get("last_sync"),
        "attention": [a for a in activities if a["status"] in ("retrasada", "bloqueada") or a["at_risk"]],
        "pending_decisions": db.query_one("SELECT COUNT(*) n FROM proposals WHERE status = 'pendiente_gestor'")["n"],
        "unread_notifications": db.query_one("SELECT COUNT(*) n FROM notifications WHERE read = 0")["n"],
        "jobs": scheduler.jobs(),
        "credentials": secrets_status(),
    }


@app.get("/activities")
def activities(status: str | None = None, user=Depends(require("read"))):
    items = db.kv_get("activities", []) or []
    return [a for a in items if not status or a["status"] == status]


@app.post("/sync")
def sync(user=Depends(require("run"))):
    try:
        return orchestrator.sync_board(user["username"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo sincronizar con Trello: {e}")


@app.get("/changes")
def changes(limit: int = 100, user=Depends(require("read"))):
    return db.query("SELECT * FROM plan_changes ORDER BY id DESC LIMIT ?", (min(limit, 500),))


@app.post("/analysis/run")
def run_analysis(user=Depends(require("run"))):
    return _background("analisis_retrasos", orchestrator.run_delay_analysis, user["username"])


# ---------------------------------------------------------------- Propuestas (REQ-05, REQ-09)

@app.get("/proposals")
def proposals(status: str | None = None, user=Depends(require("read"))):
    sql, params = "SELECT * FROM proposals", ()
    if status:
        sql, params = sql + " WHERE status = ?", (status,)
    rows = db.query(sql + " ORDER BY id DESC LIMIT 200", params)
    for r in rows:
        r["params"] = json.loads(r.pop("params_json"))
    return rows


@app.get("/proposals/{pid}")
def proposal(pid: int, user=Depends(require("read"))):
    p = orchestrator.get_proposal(pid)
    if not p:
        raise HTTPException(404, "Propuesta no encontrada")
    p["history"] = db.query("SELECT * FROM audit_log WHERE entity = 'propuesta' AND entity_id = ? ORDER BY id", (str(pid),))
    p["alternatives"] = db.query("SELECT id, action_type, status FROM proposals WHERE group_key = ? AND id != ?",
                                 (p["group_key"], pid)) if p["group_key"] else []
    return p


def _decide(fn, pid: int, *args):
    try:
        return fn(pid, *args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/proposals/{pid}/approve")
def approve(pid: int, body: DecisionIn, user=Depends(require("decide"))):
    return {"status": _decide(orchestrator.manager_approve, pid, user["username"], body.comment)}


@app.post("/proposals/{pid}/reject")
def reject(pid: int, body: DecisionIn, user=Depends(require("decide"))):
    return {"status": _decide(orchestrator.manager_reject, pid, user["username"], body.comment)}


@app.post("/proposals/{pid}/request-changes")
def request_changes(pid: int, body: ChangesIn, user=Depends(require("decide"))):
    _decide(orchestrator.manager_request_changes, pid, user["username"], body.comment)
    return {"status": "modificacion_solicitada"}


# ---------------------------------------------------------------- Código (REQ-07)

@app.get("/code-reviews")
def code_reviews(user=Depends(require("read"))):
    rows = db.query("SELECT id, created_at, repo, commit_from, commit_to, score, summary, findings_json "
                    "FROM code_reviews ORDER BY id DESC LIMIT 50")
    for r in rows:
        findings = json.loads(r.pop("findings_json"))
        r["findings_count"] = len(findings)
        r["severe_count"] = sum(1 for h in findings if h.get("severidad") in ("alta", "critica"))
    return rows


@app.get("/code-reviews/{rid}")
def code_review(rid: int, user=Depends(require("read"))):
    r = db.query_one("SELECT * FROM code_reviews WHERE id = ?", (rid,))
    if not r:
        raise HTTPException(404, "Revisión no encontrada")
    r["findings"] = json.loads(r.pop("findings_json"))
    r["commits"] = json.loads(r.pop("commits_json") or "[]")
    return r


@app.post("/code-reviews/run")
def run_code_review(user=Depends(require("run"))):
    return _background("revision_codigo", orchestrator.run_code_review, user["username"])


# ---------------------------------------------------------------- Reportes (REQ-06)

@app.get("/reports")
def reports_list(user=Depends(require("read"))):
    return db.query("SELECT id, created_at, period_start, period_end FROM reports ORDER BY id DESC LIMIT 52")


@app.get("/reports/{rid}")
def report(rid: int, user=Depends(require("read"))):
    r = db.query_one("SELECT * FROM reports WHERE id = ?", (rid,))
    if not r:
        raise HTTPException(404, "Reporte no encontrado")
    r["stats"] = json.loads(r.pop("stats_json"))
    return r


@app.post("/reports/generate")
def generate_report(user=Depends(require("run"))):
    return _background("reporte_semanal", orchestrator.generate_weekly_report, user["username"])


# ---------------------------------------------------------------- Trazabilidad y notificaciones (REQ-10)

@app.get("/audit")
def audit_log(limit: int = 200, actor_type: str | None = None, user=Depends(require("read"))):
    sql, params = "SELECT * FROM audit_log", []
    if actor_type:
        sql += " WHERE actor_type = ?"
        params.append(actor_type)
    rows = db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, min(limit, 1000)))
    for r in rows:
        r["details"] = json.loads(r.pop("details_json") or "{}")
    return rows


@app.get("/notifications")
def notifications(user=Depends(require("read"))):
    return db.query("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")


@app.post("/notifications/read-all")
def read_all(user=Depends(require("read"))):
    db.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return {"ok": True}


@app.post("/notifications/test-email")
def test_email(user=Depends(require("users"))):
    """Envía un correo de prueba a los gestores para verificar la configuración del correo."""
    from . import mailer
    if not mailer.enabled():
        raise HTTPException(400, "El correo está desactivado (MAIL_TRANSPORT vacío)")
    to = mailer.manager_emails()
    if not to:
        raise HTTPException(400, "Ningún gestor tiene correo registrado")
    text, html_body = mailer._render("info", "Correo de prueba",
                                     f"Enviado por {user['username']} desde el Agente de Proyectos.\n"
                                     "Los avisos de retrasos críticos llegarán a esta dirección.")
    try:
        mailer.send(to, "[Agente de proyectos] Correo de prueba", text, html_body)
    except Exception as e:  # noqa: BLE001
        audit.log(user["username"], "correo_prueba_fallido", "correo", None, {"error": str(e)[:300]}, actor_type="humano")
        raise HTTPException(502, f"No se pudo enviar el correo: {e}")
    audit.log(user["username"], "correo_prueba_enviado", "correo", None, {"para": to}, actor_type="humano")
    return {"ok": True, "to": to, "transport": settings.mail_transport}


@app.get("/config")
def config(user=Depends(require("read"))):
    from .agents.approver import load_policy
    return {"provider": settings.llm_provider, "models": {"ejecutor": settings.model_executor, "revisor": settings.model_reviewer,
                       "aprobador": settings.model_approver},
            "policy": load_policy(), "board_id": settings.trello_board_id, "repo": settings.github_repo}
