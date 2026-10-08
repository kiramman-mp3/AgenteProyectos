"""Agente Ejecutor: obtiene información, analiza actividades y código, detecta desviaciones,
genera reportes y PROPONE acciones. Nunca ejecuta cambios por sí mismo."""
from ..config import settings
from ..llm import chat_json
from .common import ACTION_SPEC, board_context, dumps, today_local

ROLE = """Eres el Agente Ejecutor de un sistema multiagente de seguimiento de proyectos de software.
Analizas la planificación (tablero Trello) y el código del proyecto, detectas desviaciones y propones acciones.
Tus propuestas serán verificadas por un Agente Revisor y autorizadas por un Agente Aprobador y el gestor humano.
Sé concreto, realista y justifica cada propuesta con datos del proyecto. Escribe en español."""


def propose_corrective_actions(problems: list[dict], activities: list[dict], board_meta: dict) -> list[dict]:
    """REQ-04/05: analiza causas e impacto de cada actividad problemática y genera alternativas correctivas."""
    prompt = f"""Contexto completo del proyecto:
{board_context(activities, board_meta)}

Actividades retrasadas, bloqueadas o en riesgo que debes analizar:
{dumps([{"id": a["id"], "name": a["name"], "status": a["status"], "risk_reasons": a["risk_reasons"]} for a in problems])}

{ACTION_SPEC}

Para CADA actividad problemática:
1. Determina la causa probable del retraso/riesgo (usa responsables, carga de trabajo, dependencias, fechas, estado).
2. Evalúa el impacto sobre otras actividades (campo "blocks") y sobre la fecha de cierre del proyecto.
3. Propón de 1 a 3 alternativas de acción correctiva distintas (reprogramación, cambio de prioridad,
   redistribución/reasignación, cambio de estado, comentario de seguimiento). Las fechas deben ser posteriores a hoy.

Devuelve JSON con esta forma:
{{"analisis": [{{"card_id": "...", "causa_probable": "...", "impacto": "...",
  "alternativas": [{{"action_type": "...", "params": {{...}}, "justificacion": "...", "impacto_esperado": "..."}}]}}]}}"""
    result = chat_json(settings.model_executor, ROLE, prompt)
    return result.get("analisis", []) if isinstance(result, dict) else []


def revise_proposal(proposal: dict, feedback: str, activities: list[dict], board_meta: dict) -> dict:
    """Corrige una propuesta según observaciones del Revisor o la solicitud de modificación del gestor."""
    prompt = f"""Contexto del proyecto:
{board_context(activities, board_meta)}

{ACTION_SPEC}

Propuesta original:
{dumps({k: proposal.get(k) for k in ("action_type", "target_id", "target_name", "params", "problem", "justification", "impact")})}

Observaciones que debes atender:
{feedback}

Devuelve la propuesta corregida como JSON:
{{"action_type": "...", "params": {{...}}, "justificacion": "...", "impacto_esperado": "...", "cambios_realizados": "..."}}"""
    return chat_json(settings.model_executor, ROLE, prompt)


def review_code(commits: list[dict], files: list[dict], standards: str, heuristics: list[dict]) -> dict:
    """REQ-07: analiza los cambios recientes del repositorio."""
    prompt = f"""Estándares de programación definidos para el proyecto:
{standards}

Commits analizados:
{dumps(commits)}

Archivos modificados con su diff (puede estar truncado):
{dumps(files)}

Hallazgos preliminares de análisis estático (verifícalos):
{dumps(heuristics)}

Revisa el código e identifica: errores potenciales, duplicación de código, problemas de mantenibilidad,
complejidad innecesaria, vulnerabilidades de seguridad, oportunidades de optimización e incumplimientos de los estándares.
Solo reporta hallazgos sustentados en el diff. NO propongas aplicar cambios automáticamente: solo recomendaciones.

Devuelve JSON:
{{"resumen": "...", "puntaje_calidad": 0-100,
  "hallazgos": [{{"archivo": "...", "linea": número o null,
    "categoria": "error|duplicacion|mantenibilidad|complejidad|seguridad|optimizacion|buenas_practicas",
    "severidad": "baja|media|alta|critica", "descripcion": "...", "recomendacion": "...",
    "estandar_incumplido": "número/nombre del estándar o null"}}],
  "recomendaciones_generales": ["..."]}}"""
    return chat_json(settings.model_executor, ROLE, prompt, max_tokens=6000)


def write_report_narrative(stats: dict, feedback: str | None = None) -> dict:
    """REQ-06: redacta las secciones interpretativas del reporte semanal (las cifras se calculan sin IA)."""
    extra = f"\nCorrige estas observaciones del Agente Revisor:\n{feedback}\n" if feedback else ""
    prompt = f"""Fecha actual: {today_local()}
Datos del proyecto para el reporte semanal (cifras calculadas y verificadas):
{dumps(stats)}
{extra}
Redacta las secciones interpretativas del reporte semanal. No inventes cifras: usa solo las de los datos.

Devuelve JSON:
{{"resumen_ejecutivo": "...",
  "riesgos": [{{"riesgo": "...", "probabilidad": "baja|media|alta", "impacto": "...", "mitigacion": "..."}}],
  "desviaciones": ["desviación respecto de la planificación ..."],
  "recomendaciones_siguiente_semana": ["..."]}}"""
    return chat_json(settings.model_executor, ROLE, prompt)
