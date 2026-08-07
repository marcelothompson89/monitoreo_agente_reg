# Agente de Monitoreo Regulatorio Personalizado

MVP local con FastAPI, SQLite, HTML, CSS y JavaScript vanilla que trae alertas regulatorias desde Supabase, configura un perfil de empresa, evalúa impacto con OpenAI o una lógica mock y genera un informe semanal branded (HTML + email).

## Requisitos

- Python 3.10+
- Opcional: `OPENAI_API_KEY` para usar IA real. Si no existe, la app usa evaluación mock por país, categoría, keywords y temas excluidos.

## Configurar OpenAI

Editá el archivo `.env` local:

```env
OPENAI_API_KEY=tu_api_key_acá
OPENAI_MODEL=gpt-4o-mini
```

No hace falta exportar la variable manualmente: FastAPI carga `.env` al iniciar.

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecutar

```bash
uvicorn backend.main:app --reload
```

En Windows, usando el entorno virtual local ya creado:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Abrí la app en:

```text
http://127.0.0.1:8000
```

## Flujo recomendado

1. Configurar el perfil de empresa (países, categorías, keywords, temas excluidos).
2. Ejecutar el agente desde la vista **Informes**: trae las alertas desde Supabase, las evalúa con IA y genera el informe semanal.
3. Revisar el dashboard y el historial de corridas.
4. Descargar el informe (`.html`) o recibirlo por email.

## Endpoints

- `GET /alerts`
- `GET /filters`
- `POST /company-profile`
- `GET /company-profile`
- `POST /evaluate-alerts`
- `GET /assessments`
- `GET /dashboard-summary`
- `GET /generate-report`

## Base de datos

La base SQLite se crea automáticamente en:

```text
data/regulatory_mvp.db
```

Las tablas son:

- `regulatory_alerts`
- `company_profiles`
- `alert_assessments`

La app evita duplicados de alertas por `id` o `source_url`, y evita duplicados de evaluación por combinación `company_id + alert_id`.
