"""Herramientas de administración por consola.

  python -m app.cli gen-key                     Genera una MASTER_KEY para el .env
  python -m app.cli set-secret <nombre>         Guarda una credencial cifrada (se pide sin mostrarla)
  python -m app.cli secrets                     Muestra qué credenciales están configuradas
  python -m app.cli create-user <usuario> <rol> Crea un usuario (rol: gestor | desarrollador)
  python -m app.cli set-password <usuario>      Cambia la contraseña de un usuario
  python -m app.cli check                       Prueba las conexiones con el proveedor de IA, Trello y GitHub
  python -m app.cli run <analisis|codigo|reporte|sync>  Ejecuta un proceso manualmente
"""
import getpass
import sys

from cryptography.fernet import Fernet

from . import audit, db
from .security import ROLES, SECRET_NAMES, hash_password, secrets_status, set_secret


def main(argv: list[str]) -> None:
    # La consola de Windows usa cp1252 por defecto y no puede imprimir ✔/✘.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]

    if cmd == "gen-key":
        print(Fernet.generate_key().decode())
    elif cmd == "set-secret":
        if not args or args[0] not in SECRET_NAMES:
            sys.exit(f"Nombre inválido. Opciones: {', '.join(SECRET_NAMES)}")
        value = getpass.getpass(f"Valor para {args[0]} (no se mostrará): ").strip()
        if not value:
            sys.exit("Valor vacío; no se guardó nada.")
        set_secret(args[0], value)
        audit.log("admin-cli", "credencial_actualizada", "credencial", args[0], actor_type="humano")
        print(f"Credencial '{args[0]}' guardada cifrada.")
    elif cmd == "secrets":
        for name, ok in secrets_status().items():
            print(f"  {'✔' if ok else '✘'} {name}")
    elif cmd == "create-user":
        if len(args) != 2 or args[1] not in ROLES:
            sys.exit(f"Uso: create-user <usuario> <{'|'.join(ROLES)}>")
        pwd = getpass.getpass("Contraseña: ")
        if len(pwd) < 8 or pwd != getpass.getpass("Repite la contraseña: "):
            sys.exit("Las contraseñas no coinciden o tienen menos de 8 caracteres.")
        db.insert("users", {"username": args[0], "password_hash": hash_password(pwd), "role": args[1],
                            "created_at": db.now_iso()})
        audit.log("admin-cli", "usuario_creado", "usuario", args[0], {"rol": args[1]}, actor_type="humano")
        print(f"Usuario '{args[0]}' creado con rol {args[1]}.")
    elif cmd == "set-password":
        if len(args) != 1 or not db.query_one("SELECT id FROM users WHERE username = ?", (args[0],)):
            sys.exit("Uso: set-password <usuario existente>")
        pwd = getpass.getpass("Nueva contraseña: ")
        if len(pwd) < 8 or pwd != getpass.getpass("Repite la contraseña: "):
            sys.exit("Las contraseñas no coinciden o tienen menos de 8 caracteres.")
        db.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(pwd), args[0]))
        audit.log("admin-cli", "contrasena_cambiada", "usuario", args[0], actor_type="humano")
        print(f"Contraseña de '{args[0]}' actualizada.")
    elif cmd == "check":
        _check()
    elif cmd == "run":
        from . import orchestrator
        jobs = {"analisis": orchestrator.run_delay_analysis, "codigo": orchestrator.run_code_review,
                "reporte": orchestrator.generate_weekly_report, "sync": orchestrator.sync_board}
        if not args or args[0] not in jobs:
            sys.exit(f"Uso: run <{'|'.join(jobs)}>")
        print(jobs[args[0]]("admin-cli"))
    else:
        print(__doc__)


def _check() -> None:
    from .config import settings
    from .integrations.github import GitHubClient
    from .integrations.trello import TrelloClient
    from .llm import chat_json

    def step(name, fn):
        try:
            print(f"  ✔ {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✘ {name}: {e}")

    step("Trello", lambda: (lambda b: f"tablero '{b['board']['name']}', {len(b['cards'])} tarjetas, "
                                      f"listas: {[x['name'] for x in b['lists']]}")(TrelloClient().fetch_board()))
    step("GitHub", lambda: f"{len(GitHubClient().recent_commits(None, 3))} commits recientes en {settings.github_repo}")
    for role, model in (("Ejecutor", settings.model_executor), ("Revisor", settings.model_reviewer),
                        ("Aprobador", settings.model_approver)):
        step(f"{settings.llm_provider} ({role}: {model})", lambda m=model: chat_json(m, "Eres un asistente.",
                                                                       'Devuelve {"ok": true}', max_tokens=50))


if __name__ == "__main__":
    main(sys.argv[1:])
