# LIA Utilization Assistant

Read-only chat beside a faculty-utilisation dashboard. Known questions use fixed SQL. Unmatched questions go to a guarded SQL agent. Templates answer with no Gemini key and no Ollama.

## Run

```bash
docker compose up -d --build
```

- API: http://localhost:8010/api/health
- Web: http://localhost:8090

Host ports are 8010 and 8090 because 8000 and 8080 were already in use on the build machine. `docker compose` does not start Ollama. Start it and load the model the API calls (`llama3.2`):

```bash
docker compose --profile ollama up -d
docker exec lia-ollama-1 ollama pull llama3.2
```

The model stays in the `lia-ollama` volume. Ollama listens on port 11434. The API uses `OLLAMA_BASE_URL=http://ollama:11434`. Known questions still skip the model.

Load the Excel files again without duplicating rows:

```bash
docker compose exec -T api python -m app.ingest
```

Unit tests, from `apps/api`:

```bash
uv sync --group dev
uv run pytest
```

## Personas

No passwords. `dean_cs` is limited to the School of Computer Science. `university` sees every school. The school predicate is added by the server after SQL is parsed.

## Data

Universe A is the staff master, room master, and timetable. Universe B is `staff_load`, PhD supervision, and LTPE. They are both loaded and are not joined by person name. When a fact is missing, the answer says so.

Sana Bhardwaj (staff id 26982489) has 20 timetable hours against an Assistant Professor mandate of 14, so she is over mandate. PhD hours are 0 because she is absent from the supervision extract. Experiential hours are excluded because LTPE codes do not match the timetable.

## Environment

Copy `.env.example`. Secrets stay empty unless you set them. Do not commit real keys.

| Variable | Role |
| --- | --- |
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Gemini for unmatched questions |
| `GEMINI_MODEL` | Defaults to `gemini-2.5-flash` |
| `OLLAMA_BASE_URL` | Used when that URL answers `/api/tags` |
| `OLLAMA_MODEL` | Defaults to `llama3.2` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Optional trace export |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `DATA_OWNER_EMAIL` | Real SMTP, only after confirm |
| `DATABASE_URL`, `READONLY_DATABASE_URL` | Admin and read-only roles |
| `QDRANT_URL` | Schema and metric retrieval |
| `DATA_DIR` | Excel folder |
| `TRACE_DIR` | Local JSONL traces |

If neither Gemini nor Ollama is available, template questions still answer. An unmatched question says no model is configured and suggests templates.

Email is stored as a draft until `POST /api/chat/confirm-email` with `{"confirm": true}`. Without SMTP settings that call returns a configuration error and does not open a connection.
