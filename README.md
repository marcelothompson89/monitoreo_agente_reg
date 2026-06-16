# Agente de Monitoreo Regulatorio Personalizado

MVP local con FastAPI, SQLite, HTML, CSS y JavaScript vanilla para cargar alertas regulatorias desde CSV, configurar un perfil de empresa, evaluar impacto con OpenAI o una lógica mock y generar un informe semanal en Markdown.

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

## CSV

El archivo puede incluir estas columnas:

- `id`
- `title`
- `description`
- `source_type`
- `category`
- `country`
- `institution`
- `source_url`
- `presentation_date`
- `full_text`

Columnas mínimas:

- `title`
- `id` o `source_url`

Si `full_text` no existe, el cargador usa `description`. Esto permite cargar el export `alertas_alerta_rows (2).csv` que está en este workspace.

## Flujo recomendado

1. Subir `sample_alerts.csv` o `alertas_alerta_rows (2).csv`.
2. Configurar el perfil de empresa.
3. Elegir filtros de país, institución, categoría y fechas si querés acotar la corrida.
4. Presionar `Evaluar alertas pendientes`.
5. Revisar el dashboard.
6. Descargar el informe semanal `.md`.

## Endpoints

- `POST /upload-csv`
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
