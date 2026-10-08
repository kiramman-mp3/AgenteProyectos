"""Persistencia: proyecto, propuestas, bitácora de auditoría, reportes y credenciales cifradas.

Usa PostgreSQL (p. ej. Neon) si DATABASE_URL está definida; si no, un archivo SQLite local.
Las consultas se escriben con marcadores '?' y se adaptan al motor correspondiente.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import settings

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets (
    name TEXT PRIMARY KEY,
    value_enc TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS board_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    card_id TEXT,
    card_name TEXT,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL,              -- retraso | codigo | revision
    group_key TEXT,                    -- agrupa alternativas para un mismo problema
    action_type TEXT NOT NULL,
    target_id TEXT,
    target_name TEXT,
    params_json TEXT NOT NULL,
    problem TEXT,                      -- causa probable / problema detectado
    justification TEXT,
    impact TEXT,
    status TEXT NOT NULL,
    reviewer_verdict TEXT,
    reviewer_notes TEXT,
    approver_decision TEXT,
    approver_risk TEXT,
    approver_notes TEXT,
    manager TEXT,
    manager_comment TEXT,
    decided_at TEXT,
    executed_at TEXT,
    execution_result TEXT,
    revision_of INTEGER REFERENCES proposals(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL,          -- agente | humano | sistema
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    content_md TEXT NOT NULL,
    review_notes TEXT
);

CREATE TABLE IF NOT EXISTS code_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    repo TEXT,
    commit_from TEXT,
    commit_to TEXT,
    commits_json TEXT,
    summary TEXT,
    score INTEGER,
    findings_json TEXT NOT NULL,
    review_notes TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    level TEXT NOT NULL,               -- info | advertencia | critico
    title TEXT NOT NULL,
    body TEXT,
    entity TEXT,
    entity_id TEXT,
    read INTEGER NOT NULL DEFAULT 0
);
"""


# Columnas agregadas después de la primera versión del esquema (bases ya existentes).
MIGRATIONS = [
    ("users", "full_name", "TEXT"),
    ("users", "email", "TEXT"),
    ("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_postgres() -> bool:
    return settings.database_url.startswith(("postgres://", "postgresql://"))


_lock = threading.RLock()
_conn: sqlite3.Connection | None = None   # SQLite
_pool = None                              # PostgreSQL (psycopg_pool.ConnectionPool)


def _pg_sql(sql: str) -> str:
    return sql.replace("%", "%%").replace("?", "%s")


def _init_sqlite() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.db_path, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA)
    for table, column, ddl in MIGRATIONS:
        cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    c.commit()
    return c


def _init_postgres():
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(settings.database_url, min_size=1, max_size=4, open=True,
                          kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)
    with pool.connection() as c:
        c.execute(SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))
        for table, column, ddl in MIGRATIONS:
            c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
    return pool


def conn():
    """Inicializa la conexión (y el esquema) la primera vez."""
    global _conn, _pool
    with _lock:
        if is_postgres():
            if _pool is None:
                _pool = _init_postgres()
            return _pool
        if _conn is None:
            _conn = _init_sqlite()
        return _conn


def _run(sql: str, params: tuple, fetch: str | None):
    if is_postgres():
        with conn().connection() as c:
            cur = c.execute(_pg_sql(sql), params)
            if fetch == "all":
                return [dict(r) for r in cur.fetchall()]
            if fetch == "one":
                return cur.fetchone()
            return None
    with _lock:
        c = conn()
        try:
            cur = c.execute(sql, params)
            result = [dict(r) for r in cur.fetchall()] if fetch == "all" else (
                dict(r) if fetch == "one" and (r := cur.fetchone()) else None)
            if fetch == "id":
                result = cur.lastrowid
            c.commit()
            return result
        except Exception:
            c.rollback()
            raise


def query(sql: str, params: tuple = ()) -> list[dict]:
    return _run(sql, params, "all")


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> None:
    _run(sql, params, None)


def insert(table: str, data: dict) -> int:
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({marks})"
    if is_postgres():
        return _run(sql + " RETURNING id", tuple(data.values()), "one")["id"]
    return _run(sql, tuple(data.values()), "id")


def update(table: str, row_id: int, data: dict) -> None:
    sets = ", ".join(f"{k} = ?" for k in data)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), row_id))


def kv_get(key: str, default=None):
    row = query_one("SELECT value FROM kv WHERE key = ?", (key,))
    return json.loads(row["value"]) if row else default


def kv_set(key: str, value) -> None:
    execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)))
