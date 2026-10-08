"""Prueba de extremo a extremo del flujo Ejecutor -> Revisor -> Aprobador -> Gestor -> Ejecución,
con Trello y el modelo de IA simulados."""
import pytest
from fastapi.testclient import TestClient

from app import db, orchestrator
from app.security import hash_password


class FakeTrello:
    calls = []

    def __init__(self, board):
        self._board = board

    def fetch_board(self):
        return self._board

    def update_card(self, card_id, **fields):
        FakeTrello.calls.append(("update", card_id, fields))

    def add_comment(self, card_id, text):
        FakeTrello.calls.append(("comment", card_id, text))

    def ensure_label(self, name, color=None):
        return "LA"


def fake_llm(model, system, user, **kw):
    if "Agente Ejecutor" in system and "alternativas" in user:
        return {"analisis": [{"card_id": "C2", "causa_probable": "Sobrecarga de Luis", "impacto": "Retrasa login",
                              "alternativas": [
                                  {"action_type": "reprogramar", "params": {"due": "2099-01-05"},
                                   "justificacion": "Dar margen", "impacto_esperado": "Se libera presión"},
                                  {"action_type": "reasignar", "params": {"add_members": ["Ana Pérez"]},
                                   "justificacion": "Redistribuir", "impacto_esperado": "Avanza más rápido"},
                                  {"action_type": "comentar", "params": {"text": "Revisar bloqueo hoy"},
                                   "justificacion": "Seguimiento", "impacto_esperado": "Visibilidad"}]}]}
    if system.startswith("Eres el Agente Revisor"):
        return {"verdict": "aprobada", "notes": "Consistente con los datos"}
    if "Agente Aprobador" in system:
        return {"riesgo": "bajo", "justificacion": "Reversible"}
    raise AssertionError(f"Prompt inesperado: {user[:80]}")


@pytest.fixture
def env(board, monkeypatch):
    FakeTrello.calls = []
    monkeypatch.setattr(orchestrator, "TrelloClient", lambda: FakeTrello(board))
    monkeypatch.setattr("app.actions.TrelloClient", lambda: FakeTrello(board))
    for mod in ("executor", "reviewer", "approver"):
        monkeypatch.setattr(f"app.agents.{mod}.chat_json", fake_llm)
    db.insert("users", {"username": "gestor1", "password_hash": hash_password("clave1234"), "role": "gestor",
                        "created_at": db.now_iso()})
    db.insert("users", {"username": "obs", "password_hash": hash_password("clave1234"), "role": "observador",
                        "created_at": db.now_iso()})


def test_full_flow(env):
    result = orchestrator.run_delay_analysis("test")
    states = {d["estado"] for d in result["detalle"]}
    # Comentar se autoejecuta por política; reprogramar y reasignar esperan al gestor.
    assert states == {"ejecutada", "pendiente_gestor"}
    assert any(c[0] == "comment" for c in FakeTrello.calls)
    assert not any(c[0] == "update" for c in FakeTrello.calls)

    from app.main import app
    client = TestClient(app)
    tok = client.post("/auth/login", json={"username": "gestor1", "password": "clave1234"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    pending = client.get("/proposals?status=pendiente_gestor", headers=h).json()
    resched = next(p for p in pending if p["action_type"] == "reprogramar")

    r = client.post(f"/proposals/{resched['id']}/approve", json={"comment": "OK"}, headers=h)
    assert r.json()["status"] == "ejecutada"
    assert ("update", "C2") in {(c[0], c[1]) for c in FakeTrello.calls}
    # La alternativa restante del mismo problema queda descartada.
    assert client.get("/proposals?status=pendiente_gestor", headers=h).json() == []

    # No se puede decidir dos veces sobre la misma propuesta.
    assert client.post(f"/proposals/{resched['id']}/reject", json={}, headers=h).status_code == 409

    actors = {row["actor"] for row in client.get("/audit", headers=h).json()}
    assert {"Agente Ejecutor", "Agente Revisor", "Agente Aprobador", "gestor1"} <= actors


def test_permissions(env):
    from app.main import app
    client = TestClient(app)
    assert client.get("/dashboard").status_code == 401
    tok = client.post("/auth/login", json={"username": "obs", "password": "clave1234"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/dashboard", headers=h).status_code == 200
    assert client.post("/proposals/1/approve", json={}, headers=h).status_code == 403
    assert client.post("/auth/login", json={"username": "obs", "password": "mala"}).status_code == 401


def test_weekly_report(env, monkeypatch):
    def llm(model, system, user, **kw):
        if system.startswith("Eres el Agente Revisor"):
            return {"consistente": True, "observaciones": "Cifras consistentes"}
        return {"resumen_ejecutivo": "Avance moderado", "riesgos": [{"riesgo": "API retrasada", "probabilidad": "alta",
                "impacto": "Login bloqueado", "mitigacion": "Reasignar"}], "desviaciones": ["API 2 días tarde"],
                "recomendaciones_siguiente_semana": ["Cerrar API de usuarios"]}
    monkeypatch.setattr("app.agents.executor.chat_json", llm)
    monkeypatch.setattr("app.agents.reviewer.chat_json", llm)
    rid = orchestrator.generate_weekly_report("test")
    md = db.query_one("SELECT content_md FROM reports WHERE id = ?", (rid,))["content_md"]
    assert "Avance ponderado:** 30.0%" in md
    assert "| Retrasadas | 1 |" in md and "| Bloqueadas | 1 |" in md
    assert "Cerrar API de usuarios" in md


class FakeGitHub:
    repo = "demo/repo"
    branch = "main"

    def recent_commits(self, since, limit=10):
        return [{"sha": "abc1234567", "parents": [{}], "commit": {"author": {"name": "Luis", "date": "2026-10-07"}, "message": "login"}},
                {"sha": "merge99999", "parents": [{}, {}], "commit": {"author": {"name": "Ana", "date": "2026-10-08"}, "message": "Merge PR"}}]

    def commit_detail(self, sha):
        return {"files": [{"filename": "auth.py", "status": "modified", "additions": 2, "deletions": 0,
                           "patch": "@@ -1,1 +1,3 @@\n import os\n+PASSWORD = 'admin12345'\n+q = \"SELECT * FROM u WHERE id=\" + uid\n"}]}


def test_code_review_creates_issue_proposal_but_never_modifies_code(env, monkeypatch):
    def llm(model, system, user, **kw):
        if system.startswith("Eres el Agente Ejecutor"):
            return {"resumen": "Credencial expuesta", "puntaje_calidad": 55, "recomendaciones_generales": ["Usar .env"],
                    "hallazgos": [{"archivo": "auth.py", "linea": 2, "categoria": "seguridad", "severidad": "critica",
                                   "descripcion": "Contraseña en código", "recomendacion": "Variables de entorno"},
                                  {"archivo": "otro.py", "linea": 1, "categoria": "error", "severidad": "alta",
                                   "descripcion": "Inventado", "recomendacion": "-"}]}
        if "Hallazgos reportados" in user:
            return {"validaciones": [{"indice": 0, "valido": True, "severidad": "critica"}]}
        return fake_llm(model, system, user)
    monkeypatch.setattr(orchestrator, "GitHubClient", FakeGitHub)
    for mod in ("executor", "reviewer", "approver"):
        monkeypatch.setattr(f"app.agents.{mod}.chat_json", llm)
    out = orchestrator.run_code_review("test")
    assert out["hallazgos"] == 1  # el hallazgo sobre un archivo no modificado se descarta
    assert out["commits"] == 1    # el commit de merge no se analiza
    assert db.kv_get("last_reviewed_sha:main") == "merge99999"  # pero queda marcado como revisado
    p = db.query_one("SELECT * FROM proposals WHERE source = 'codigo'")
    assert p["action_type"] == "crear_issue" and p["status"] == "pendiente_gestor"
