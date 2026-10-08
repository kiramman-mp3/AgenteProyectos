from app import code_analysis, tracking
from app.agents import reviewer
from app.security import get_secret, hash_password, set_secret, verify_password


def test_secrets_are_encrypted_at_rest():
    from app import db
    set_secret("trello_token", "super-secreto-123")
    raw = db.query_one("SELECT value_enc FROM secrets WHERE name = 'trello_token'")["value_enc"]
    assert "super-secreto" not in raw
    assert get_secret("trello_token") == "super-secreto-123"


def test_password_hash():
    h = hash_password("clave-segura")
    assert verify_password("clave-segura", h)
    assert not verify_password("otra", h)


def _meta(board):
    return {"lists": board["lists"], "members": board["members"], "labels": board["labels"]}


def test_reviewer_structural_checks(board):
    acts = tracking.build_activities(board)
    meta = _meta(board)
    errs, _ = reviewer.structural_checks(
        {"action_type": "reprogramar", "target_id": "C2", "params": {"due": "2000-01-01"}}, acts, meta)
    assert any("anterior a hoy" in e for e in errs)
    errs, _ = reviewer.structural_checks(
        {"action_type": "reasignar", "target_id": "C2", "params": {"add_members": ["Pedro"]}}, acts, meta)
    assert any("Pedro" in e for e in errs)
    errs, warns = reviewer.structural_checks(
        {"action_type": "reprogramar", "target_id": "C2", "params": {"due": "2099-01-01"}}, acts, meta)
    assert not errs and warns  # advierte que las dependientes vencen antes
    errs, _ = reviewer.structural_checks(
        {"action_type": "cambiar_estado", "target_id": "C3", "params": {"list_name": "En progreso"}}, acts, meta)
    assert not errs


def test_static_checks_line_numbers():
    files = [{"filename": "app.py", "patch": "@@ -1,2 +10,4 @@\n ctx\n+API_KEY = 'abcdef123456'\n-old\n+eval(x)\n"}]
    found = code_analysis.static_checks(files)
    assert {(f["linea"], f["categoria"]) for f in found} == {(11, "seguridad"), (12, "seguridad")}


def test_llm_provider_selection(monkeypatch):
    import httpx
    from app import llm
    from app.config import settings
    sent = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, auth=headers["Authorization"], body=json)
        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    set_secret("gemini_api_key", "g-key")
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    assert llm.chat_json("gemini-2.5-flash", "s", "u") == {"ok": True}
    assert "generativelanguage.googleapis.com" in sent["url"] and sent["auth"] == "Bearer g-key"
    assert sent["body"]["reasoning_effort"] == "low"

    set_secret("openrouter_api_key", "or-key")
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    llm.chat_json("google/gemini-2.5-flash", "s", "u")
    assert "openrouter.ai" in sent["url"] and "reasoning_effort" not in sent["body"]

    from app.security import secrets_status
    assert "gemini_api_key" not in secrets_status() and "openrouter_api_key" in secrets_status()


def test_llm_retries_transient_errors(monkeypatch):
    import httpx
    from app import llm
    from app.config import settings
    codes = iter([503, 429, 200])

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, "busy"
        def json(self):
            return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp(next(codes)))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    set_secret("gemini_api_key", "k")
    assert llm.chat_json("m", "s", "u") == {"ok": 1}


def test_bootstrap_from_environment(monkeypatch):
    from app import bootstrap, db
    monkeypatch.setenv("TRELLO_TOKEN", "tok-desde-render")
    monkeypatch.setenv("BOOTSTRAP_USERNAME", "johan")
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "clave-segura-1")
    bootstrap.run()
    bootstrap.run()  # idempotente
    assert get_secret("trello_token") == "tok-desde-render"
    users = db.query("SELECT username, role, password_hash FROM users")
    assert len(users) == 1 and users[0]["role"] == "gestor"
    assert verify_password("clave-segura-1", users[0]["password_hash"])
    # Si el usuario ya existe, el arranque no pisa la contraseña cambiada desde la app.
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "otra-clave-22")
    bootstrap.run()
    assert verify_password("clave-segura-1", db.query_one("SELECT password_hash FROM users")["password_hash"])
