import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["MASTER_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 32
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TRELLO_BOARD_ID"] = "board1"
os.environ["GITHUB_REPO"] = "demo/repo"
# Las pruebas no deben depender del .env local (correo o base de datos reales).
os.environ["MAIL_TRANSPORT"] = ""
os.environ["DATABASE_URL"] = ""


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """SQLite temporal por prueba. Con TEST_DATABASE_URL, usa un esquema PostgreSQL temporal que se borra al final."""
    from app import db
    from app.config import settings
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(db, "_pool", None)
    pg_url = os.getenv("TEST_DATABASE_URL")
    if not pg_url:
        monkeypatch.setattr(settings, "database_url", "")
        yield
        return
    import uuid
    import psycopg
    schema = f"test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in pg_url else "?"
    monkeypatch.setattr(settings, "database_url", f"{pg_url}{sep}options=-csearch_path%3D{schema}")
    try:
        yield
    finally:
        if db._pool is not None:
            db._pool.close()
        with psycopg.connect(pg_url, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


def iso(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


@pytest.fixture
def board():
    lists = [{"id": "L1", "name": "Pendiente"}, {"id": "L2", "name": "En progreso"},
             {"id": "L3", "name": "Hecho"}, {"id": "L4", "name": "Bloqueado"}]
    members = [{"id": "M1", "fullName": "Ana Pérez", "username": "ana"},
               {"id": "M2", "fullName": "Luis Mora", "username": "luis"}]
    labels = [{"id": "LA", "name": "Alta", "color": "red"}, {"id": "LB", "name": "Baja", "color": "green"}]

    def card(cid, name, lst, due=None, start=None, members=(), labels=(), desc="", checklist=None, done=False):
        return {"id": cid, "shortLink": "s" + cid, "name": name, "idList": lst, "due": due, "start": start,
                "dueComplete": done, "idMembers": list(members), "labels": [lb for lb in labels],
                "idLabels": [lb["id"] for lb in labels], "desc": desc, "url": f"https://trello.com/c/s{cid}",
                "checklists": [{"checkItems": checklist}] if checklist else [], "dateLastActivity": iso(-1)}

    cards = [
        card("C1", "Diseñar base de datos", "L3", due=iso(-10), members=["M1"], done=True),
        card("C2", "API de usuarios", "L2", due=iso(-2), start=iso(-8), members=["M2"], labels=[labels[0]],
             checklist=[{"state": "complete"}, {"state": "incomplete"}]),
        card("C3", "Pantalla de login", "L1", due=iso(1), members=["M1"], desc="Depende de: sC2"),
        card("C4", "Despliegue", "L1", due=iso(20), desc="Depende de: Pantalla de login"),
        card("C5", "Integración pagos", "L4", due=iso(5), members=["M2"]),
    ]
    return {"board": {"id": "board1", "name": "Proyecto Demo", "url": "https://trello.com/b/x"},
            "lists": lists, "members": members, "labels": labels, "cards": cards}
