"""REQ-07: preparación de diffs y análisis estático ligero que complementa la revisión con IA."""
import re

SKIP_PATTERNS = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|\.min\.(js|css)$|"
    r"\.(png|jpe?g|gif|ico|svg|pdf|zip|jar|apk|woff2?|ttf|mp4|lock)$)", re.I)
MAX_PATCH_PER_FILE = 6000
MAX_TOTAL_CHARS = 80000

RULES = [
    ("seguridad", "critica", re.compile(r"(api[_-]?key|secret|password|passwd|pwd|token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]", re.I),
     "Posible credencial escrita directamente en el código"),
    ("seguridad", "alta", re.compile(r"\beval\s*\("), "Uso de eval(): riesgo de ejecución de código arbitrario"),
    ("seguridad", "alta", re.compile(r"(SELECT|INSERT|UPDATE|DELETE)\b.*['\"]\s*(\+|%|\.format|\$\{)", re.I),
     "Consulta SQL construida concatenando cadenas: riesgo de inyección SQL"),
    ("seguridad", "media", re.compile(r"innerHTML\s*=|dangerouslySetInnerHTML"), "Inserción de HTML sin sanitizar (XSS)"),
    ("error", "media", re.compile(r"except\s*:\s*(pass)?\s*$|catch\s*\([^)]*\)\s*\{\s*\}"), "Excepción silenciada"),
    ("buenas_practicas", "baja", re.compile(r"console\.log\(|\bprint\("), "Salida de depuración en el código"),
    ("mantenibilidad", "baja", re.compile(r"\b(TODO|FIXME|HACK)\b"), "Comentario pendiente (TODO/FIXME)"),
]
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def prepare_files(commit_details: list[dict]) -> list[dict]:
    """Agrupa los archivos modificados en los commits, omitiendo binarios y lockfiles, con límite de tamaño."""
    files: dict[str, dict] = {}
    for c in commit_details:
        for f in c.get("files", []):
            name = f["filename"]
            if SKIP_PATTERNS.search(name) or not f.get("patch"):
                continue
            entry = files.setdefault(name, {"filename": name, "status": f.get("status"), "additions": 0,
                                            "deletions": 0, "patch": ""})
            entry["additions"] += f.get("additions", 0)
            entry["deletions"] += f.get("deletions", 0)
            entry["patch"] += f["patch"] + "\n"
    total, result = 0, []
    for entry in sorted(files.values(), key=lambda e: -(e["additions"] + e["deletions"])):
        if len(entry["patch"]) > MAX_PATCH_PER_FILE:
            entry["patch"] = entry["patch"][:MAX_PATCH_PER_FILE] + "\n... (diff truncado)"
        if total + len(entry["patch"]) > MAX_TOTAL_CHARS:
            break
        total += len(entry["patch"])
        result.append(entry)
    return result


def static_checks(files: list[dict]) -> list[dict]:
    """Aplica reglas de expresiones regulares solo sobre las líneas agregadas del diff."""
    findings = []
    for f in files:
        line_no = 0
        for raw in f["patch"].splitlines():
            m = _HUNK.match(raw)
            if m:
                line_no = int(m.group(1))
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                code = raw[1:]
                for categoria, severidad, pattern, desc in RULES:
                    if pattern.search(code):
                        findings.append({"archivo": f["filename"], "linea": line_no, "categoria": categoria,
                                         "severidad": severidad, "descripcion": desc, "codigo": code.strip()[:160]})
                line_no += 1
            elif not raw.startswith("-"):
                line_no += 1
    return findings
