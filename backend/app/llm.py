"""Cliente de modelos de IA (OpenRouter o Gemini, ambos con API compatible con OpenAI) que devuelve JSON."""
import json
import re
import time

import httpx

from .config import settings
from .security import get_secret

# proveedor -> (endpoint de chat completions, nombre de la credencial cifrada)
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter_api_key"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini_api_key"),
}


class LLMError(RuntimeError):
    pass


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError("No se encontró JSON", text, 0)


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAYS = (5, 20, 60)  # segundos


def _post_with_retry(url: str, headers: dict, body: dict) -> httpx.Response:
    """Reintenta ante límites de cuota (429) o saturación temporal del proveedor (5xx)."""
    for delay in (*RETRY_DELAYS, None):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=180)
        except httpx.HTTPError as e:
            if delay is None:
                raise LLMError(f"Error de red con {settings.llm_provider}: {e}") from e
        else:
            if r.status_code not in RETRY_STATUSES or delay is None:
                return r
        time.sleep(delay)
    raise AssertionError("inalcanzable")


def chat_json(model: str, system: str, user: str, temperature: float = 0.2, max_tokens: int = 4000):
    """Envía un prompt y devuelve el JSON parseado. Reintenta una vez si la respuesta no es JSON válido."""
    if settings.llm_provider not in PROVIDERS:
        raise LLMError(f"LLM_PROVIDER '{settings.llm_provider}' no válido; opciones: {', '.join(PROVIDERS)}")
    url, secret_name = PROVIDERS[settings.llm_provider]
    headers = {"Authorization": f"Bearer {get_secret(secret_name)}"}
    extra = {}
    if settings.llm_provider == "openrouter":
        headers.update({"HTTP-Referer": "https://github.com/agente-seguimiento-proyectos",
                        "X-Title": "Agente Seguimiento Proyectos UTA"})
    else:
        # En Gemini el razonamiento interno consume tokens de salida: se limita y se deja margen.
        extra = {"reasoning_effort": "low"}
        max_tokens += 2048
    messages = [
        {"role": "system", "content": system + "\n\nResponde ÚNICAMENTE con JSON válido, sin texto adicional."},
        {"role": "user", "content": user},
    ]
    last_error = None
    for _ in range(2):
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, **extra}
        r = _post_with_retry(url, headers, body)
        if r.status_code != 200:
            raise LLMError(f"{settings.llm_provider} respondió {r.status_code}: {r.text[:300]}")
        data = r.json()
        if "choices" not in data:
            raise LLMError(f"Respuesta inesperada de {settings.llm_provider}: {str(data)[:300]}")
        content = data["choices"][0]["message"].get("content") or ""
        try:
            return _extract_json(content)
        except json.JSONDecodeError as e:
            last_error = e
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": "Tu respuesta no era JSON válido. Devuelve solo el JSON solicitado."},
            ]
    raise LLMError(f"El modelo {model} no devolvió JSON válido: {last_error}")
