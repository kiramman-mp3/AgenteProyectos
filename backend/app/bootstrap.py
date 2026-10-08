"""Inicialización desde variables de entorno para despliegues en la nube (p. ej. Render), donde el disco
puede ser efímero: en cada arranque se cifran las credenciales en la base y se asegura el usuario inicial.

Variables reconocidas (todas opcionales):
  OPENROUTER_API_KEY, GEMINI_API_KEY, TRELLO_API_KEY, TRELLO_TOKEN, GITHUB_TOKEN
  BOOTSTRAP_USERNAME, BOOTSTRAP_PASSWORD, BOOTSTRAP_ROLE (por defecto 'gestor')
"""
import logging
import os

from . import audit, db
from .security import SECRET_NAMES, get_secret, hash_password, set_secret, verify_password

log = logging.getLogger("agente.bootstrap")


def run() -> None:
    for name in SECRET_NAMES:
        value = os.getenv(name.upper(), "").strip()
        if not value:
            continue
        try:
            unchanged = get_secret(name) == value
        except RuntimeError:
            unchanged = False
        if not unchanged:
            set_secret(name, value)
            audit.log(audit.SYSTEM, "credencial_cargada_desde_entorno", "credencial", name)
            log.info("Credencial '%s' cargada desde el entorno y cifrada", name)

    username = os.getenv("BOOTSTRAP_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_PASSWORD", "")
    role = os.getenv("BOOTSTRAP_ROLE", "gestor").strip()
    if not (username and password):
        return
    if len(password) < 8 or role not in ("admin", "gestor", "observador"):
        log.error("BOOTSTRAP_PASSWORD debe tener 8+ caracteres y BOOTSTRAP_ROLE ser admin|gestor|observador")
        return
    user = db.query_one("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    if user is None:
        db.insert("users", {"username": username, "password_hash": hash_password(password), "role": role,
                            "created_at": db.now_iso()})
        audit.log(audit.SYSTEM, "usuario_creado_desde_entorno", "usuario", username, {"rol": role})
    elif not verify_password(password, user["password_hash"]):
        db.execute("UPDATE users SET password_hash = ?, role = ? WHERE id = ?", (hash_password(password), role, user["id"]))
        audit.log(audit.SYSTEM, "usuario_actualizado_desde_entorno", "usuario", username, {"rol": role})
