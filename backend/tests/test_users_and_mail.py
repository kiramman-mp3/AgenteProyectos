import pytest
from fastapi.testclient import TestClient

from app import audit, db, mailer
from app.config import settings
from app.security import hash_password


@pytest.fixture
def client():
    db.insert("users", {"username": "johan", "password_hash": hash_password("clave-gestor"), "role": "gestor",
                        "email": "gestor@example.com", "created_at": db.now_iso()})
    from app.main import app
    c = TestClient(app)
    tok = c.post("/auth/login", json={"username": "johan", "password": "clave-gestor"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    return c


def login(c, user, pwd):
    return TestClient(c.app).post("/auth/login", json={"username": user, "password": pwd})


def test_gestor_manages_developers(client):
    r = client.post("/users", json={"username": "carol", "full_name": "Carol C.", "email": "", "role": "desarrollador"})
    assert r.status_code == 200, r.text
    temp, uid = r.json()["temporary_password"], r.json()["id"]
    assert client.post("/users", json={"username": "carol"}).status_code == 409

    # Primer ingreso con contraseña temporal: la app debe obligar a cambiarla.
    first = login(client, "carol", temp).json()
    assert first["must_change_password"] is True and first["role"] == "desarrollador"
    dev = TestClient(client.app, headers={"Authorization": f"Bearer {first['token']}"})
    assert dev.post("/auth/change-password", json={"current_password": "mala", "new_password": "nueva-clave-1"}).status_code == 400
    assert dev.post("/auth/change-password", json={"current_password": temp, "new_password": "nueva-clave-1"}).json() == {"ok": True}
    assert login(client, "carol", "nueva-clave-1").json()["must_change_password"] is False

    # Un desarrollador no administra usuarios ni decide propuestas.
    assert dev.get("/users").status_code == 403
    assert dev.post("/proposals/1/approve", json={}).status_code == 403
    assert dev.get("/dashboard").status_code == 200

    # El gestor restablece y desactiva.
    new_temp = client.post(f"/users/{uid}/reset-password").json()["temporary_password"]
    assert login(client, "carol", new_temp).status_code == 200
    assert client.patch(f"/users/{uid}", json={"active": False}).json()["active"] == 0
    assert login(client, "carol", new_temp).status_code == 401

    actions = {r["action"] for r in client.get("/audit").json()}
    assert {"usuario_creado", "contrasena_cambiada", "contrasena_restablecida", "usuario_actualizado"} <= actions


def test_gestor_cannot_lock_himself_out(client):
    me = client.get("/auth/me").json()
    assert client.patch(f"/users/{me['id']}", json={"active": False}).status_code == 400
    assert client.patch(f"/users/{me['id']}", json={"role": "desarrollador"}).status_code == 400
    assert client.patch(f"/users/{me['id']}", json={"email": "otro@example.com"}).status_code == 200


def test_critical_notification_emails_managers(client, monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "mail_transport", "smtp")
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html_body=None: sent.append((to, subject, text)))
    monkeypatch.setattr(mailer.threading, "Thread", lambda target, daemon: type("T", (), {"start": lambda self: target()})())
    audit.notify("info", "Sin importancia")
    audit.notify("critico", "Actividad retrasada: API", "Responsables: Luis")
    assert len(sent) == 1
    to, subject, text = sent[0]
    assert to == ["gestor@example.com"] and "Actividad retrasada: API" in subject and "Luis" in text
    assert db.query_one("SELECT action FROM audit_log WHERE action = 'correo_enviado'")


def test_apps_script_transport(monkeypatch):
    import httpx
    from app.security import set_secret
    captured = {}

    class Resp:
        status_code, text = 200, '{"ok": true}'

    def fake_post(url, timeout, follow_redirects, json):
        captured.update(url=url, **json)
        return Resp()

    monkeypatch.setattr(settings, "mail_transport", "apps_script")
    monkeypatch.setattr(settings, "mail_webhook_url", "https://script.google.com/macros/s/x/exec")
    monkeypatch.setattr(httpx, "post", fake_post)
    set_secret("mail_webhook_secret", "s3cr3t")
    mailer.send(["a@b.com"], "Asunto", "texto", "<p>html</p>")
    assert captured["secret"] == "s3cr3t" and captured["to"] == "a@b.com" and captured["htmlBody"] == "<p>html</p>"
