# Agente inteligente para seguimiento y control de proyectos de software

Sistema multiagente (Ejecutor → Revisor → Aprobador → Ejecución autorizada) que supervisa un proyecto en
**Trello**, revisa el código en **GitHub** y asiste al gestor del proyecto mediante una **app móvil Android (APK)**.
Los modelos de IA se consumen vía **OpenRouter** o directamente con la **API de Gemini** (`LLM_PROVIDER` en `.env`),
y cada agente puede usar un modelo distinto.

```
┌────────────────────┐    HTTPS/JWT    ┌───────────────────────────── backend (FastAPI) ─────────────────────────────┐
│  App móvil (Expo)  │ ◀────────────▶ │  API REST ─▶ Orquestador ─▶ Agente Ejecutor ─▶ Agente Revisor ─▶ Agente Aprobador │
│  Panel, Propuestas │                 │                    │                                         │                │
│  Código, Reportes  │                 │   Planificador ────┘     SQLite (bitácora, propuestas,       ▼                │
│  Bitácora          │                 │   (APScheduler)          reportes, credenciales cifradas)   Ejecución ─▶ Trello / GitHub
└────────────────────┘                 └──────────────────────────────────────────────────────────────────────────────┘
```

## Estructura

| Carpeta / archivo | Contenido |
|---|---|
| `backend/app/tracking.py` | Estados, avance, riesgos, dependencias y detección de cambios (lógica determinista, sin IA) |
| `backend/app/agents/executor.py` | **Agente Ejecutor**: analiza retrasos y código, redacta reportes, propone acciones |
| `backend/app/agents/reviewer.py` | **Agente Revisor**: validaciones automáticas + verificación técnica con IA |
| `backend/app/agents/approver.py` | **Agente Aprobador**: aplica `policy.json` y evalúa el riesgo |
| `backend/app/orchestrator.py` | Flujo multiagente, decisiones del gestor, revisión de código, reporte semanal |
| `backend/app/actions.py` | Único módulo que escribe en Trello/GitHub, y solo con propuestas autorizadas |
| `backend/app/security.py` | Cifrado de credenciales (Fernet), contraseñas PBKDF2, JWT, roles |
| `backend/policy.json` | Reglas de autorización (qué se autoejecuta, qué requiere al gestor, qué está prohibido) |
| `backend/standards.md` | Estándares de programación del proyecto que usa la revisión de código |
| `mobile/` | App Expo / React Native (Expo Router) para el gestor |

## 1. Backend

Requisitos: Python 3.10+.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

El archivo `.env` ya tiene `MASTER_KEY` y `JWT_SECRET` generados. Completa en él:

- `TRELLO_BOARD_ID`: el identificador que aparece en la URL del tablero (`trello.com/b/<ID>/...`).
- `GITHUB_REPO` (`usuario/repositorio`) y `GITHUB_BRANCH`.
- Los nombres de tus listas de Trello (`LISTS_PENDING`, `LISTS_IN_PROGRESS`, `LISTS_DONE`, `LISTS_BLOCKED`).
- El proveedor de IA (`LLM_PROVIDER=openrouter` o `gemini`) y el modelo de cada agente (`MODEL_EXECUTOR`,
  `MODEL_REVIEWER`, `MODEL_APPROVER`). Con OpenRouter los identificadores llevan prefijo
  (`google/gemini-3.5-flash`, ver https://openrouter.ai/models); con Gemini directo van sin prefijo
  (`gemini-3.8-flash`, ver https://ai.google.dev/gemini-api/docs/models).

Guarda las credenciales **cifradas** (se piden sin mostrarse en pantalla y no quedan en ningún archivo de texto):

```powershell
python -m app.cli set-secret openrouter_api_key   # si LLM_PROVIDER=openrouter: https://openrouter.ai/keys
python -m app.cli set-secret gemini_api_key       # si LLM_PROVIDER=gemini: https://aistudio.google.com/apikey
python -m app.cli set-secret trello_api_key       # https://trello.com/power-ups/admin → API key
python -m app.cli set-secret trello_token         # token generado desde la misma página
python -m app.cli set-secret github_token         # token fine-grained: Contents=Read, Issues=Read/Write
python -m app.cli create-user gestor1 gestor      # también: admin, observador
python -m app.cli check                           # prueba las conexiones con Trello, GitHub y los 3 modelos
```

Inicia el servidor (escuchando en la red local para que el teléfono pueda conectarse):

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Documentación interactiva de la API: `http://localhost:8000/docs`. Pruebas: `pytest`.

Ejecución manual de procesos: `python -m app.cli run sync|analisis|codigo|reporte`.

### Convenciones en Trello

- **Estado**: según la lista donde está la tarjeta; "completada" también si se marca la fecha como cumplida;
  "bloqueada" si está en la lista de bloqueados o tiene la etiqueta `Bloqueado`; "retrasada" si venció sin completarse.
- **Prioridad**: etiquetas `Alta`, `Media`, `Baja` (configurables).
- **Dependencias**: en la descripción de la tarjeta, una línea `Depende de: <nombre de tarjeta o shortLink>`.
  Se usan para calcular el impacto de un retraso sobre otras actividades.
- **Avance**: completada = 100 %; si tiene checklist, el porcentaje de ítems marcados; en progreso sin checklist = 50 %.

## 2. App móvil

```powershell
cd mobile
npm install
npx expo start          # desarrollo con Expo Go (escanear el QR)
```

En la pantalla de inicio de sesión escribe la dirección del backend, por ejemplo `http://192.168.1.10:8000`
(la IP de tu computadora en la red Wi-Fi; obténla con `ipconfig`).

### Generar el APK

```powershell
npm install -g eas-cli
eas login                 # cuenta gratuita en expo.dev
eas build -p android --profile preview
```

Al terminar, EAS entrega un enlace para descargar el `.apk` e instalarlo en el teléfono.

> La app permite HTTP sin cifrar (`usesCleartextTraffic`) para poder usar el backend en la red local durante el
> desarrollo y la demostración. En producción, publica el backend detrás de HTTPS (por ejemplo, en Render o Railway, o
> con un túnel como Cloudflare Tunnel) y desactiva esa opción en `app.json`.

## 3. Flujo multiagente

1. **Ejecutor** sincroniza Trello, detecta actividades retrasadas, bloqueadas o en riesgo, analiza causa e impacto y
   propone de 1 a 3 alternativas correctivas por problema.
2. **Revisor** valida cada propuesta: verificaciones automáticas (la tarjeta existe, las fechas son futuras y coherentes,
   el miembro pertenece al tablero, la lista existe, conflictos con dependencias) y luego una verificación técnica con
   IA. Si pide ajustes, el Ejecutor corrige la propuesta una vez.
3. **Aprobador** aplica `policy.json`: deniega acciones prohibidas, escala reprogramaciones grandes, autoejecuta
   solo las acciones de bajo impacto (comentarios) y envía el resto al **gestor**.
4. **Gestor** (desde la app) aprueba, rechaza o **solicita modificaciones**; si pide cambios, el Ejecutor genera una
   nueva versión que vuelve a pasar por el Revisor y el Aprobador.
5. **Ejecución**: solo las propuestas autorizadas se aplican en Trello o GitHub. Al ejecutar una alternativa, las otras
   alternativas del mismo problema se descartan. Todo queda en la bitácora.

El código fuente **nunca se modifica automáticamente**: los hallazgos graves se proponen como *issues* de GitHub que el
gestor debe aprobar.

Tareas automáticas: análisis de retrasos cada `ANALYSIS_INTERVAL_MINUTES`, revisión de código cada
`CODE_REVIEW_INTERVAL_HOURS` y reporte semanal cada `REPORT_DAY` a las `REPORT_HOUR`.

## 4. Matriz de requerimientos (evidencia)

| ID | Requerimiento | Evidencia en el sistema |
|---|---|---|
| REQ-01 | Planificación: actividades, responsables, fechas, prioridades, estados | `tracking.build_activities`; app → pestaña **Actividades** |
| REQ-02 | Estado de cada tarea y avance general | 5 estados + avance ponderado y por completadas (`tracking.summarize`); app → **Panel** |
| REQ-03 | Datos de Trello y detección de cambios | `integrations/trello.py`; comparación de snapshots (`tracking.diff_snapshots`), tabla `plan_changes`, endpoint `/changes` |
| REQ-04 | Detección automática de retrasos/riesgos, causas e impacto | Riesgo por vencimiento y por avance vs. tiempo transcurrido; impacto por dependencias transitivas (`blocks`); causa analizada por el Ejecutor |
| REQ-05 | Alternativas correctivas presentadas al gestor | `executor.propose_corrective_actions` (reprogramar, prioridad, reasignar, estado, comentario); app → **Propuestas** |
| REQ-06 | Reporte semanal automático | `orchestrator.generate_weekly_report` (cifras calculadas sin IA + redacción del Ejecutor validada por el Revisor); app → **Reportes** |
| REQ-07 | Revisión de código | `orchestrator.run_code_review`: diffs de GitHub + análisis estático (`code_analysis.py`) + IA según `standards.md`; el Revisor descarta falsos positivos; app → **Código** |
| REQ-08 | Flujo Ejecutor → Revisor → Aprobador | `orchestrator.process_proposal`; detalle de cada etapa en la pantalla de la propuesta |
| REQ-09 | Gestor acepta, rechaza o modifica | Endpoints `/proposals/{id}/approve`, `/reject` y `/request-changes`; notificaciones en la app |
| REQ-10 | Historial completo con fecha/hora y actor | Tabla `audit_log` (agente, humano o sistema); app → **Bitácora** (icono de reloj en el Panel) |
| REQ-11 | Permisos y protección de credenciales | Credenciales cifradas con Fernet (AES-128-CBC + HMAC) usando `MASTER_KEY`; roles admin/gestor/observador; JWT; contraseñas PBKDF2-SHA256; token de sesión en el almacenamiento seguro del teléfono (`expo-secure-store`); las credenciales de Trello/GitHub nunca llegan a la app |

Pruebas automatizadas (`backend/tests`): estados, riesgo, dependencias, avance, detección de cambios, cifrado,
validaciones del Revisor, análisis estático, flujo multiagente completo con aprobación del gestor, permisos por rol,
reporte semanal y revisión de código que crea un issue sin tocar el código.
