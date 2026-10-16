# Adal Navigator

Adal Navigator is an early RU/KK prototype for helping Almaty residents understand where to start with common municipal issues. The first interface is a small web chat; the backend is a FastAPI service that can later be reused by a thin Telegram client.

The assistant confirms its understanding before looking up guidance. It only answers civic questions from verified knowledge-base chunks, cites those sources, and falls back when evidence is missing. It does not submit appeals or provide general legal advice.

## Run locally

1. Install [`uv`](https://docs.astral.sh/uv/).
2. Copy `.env.example` to `.env`. Set unique values for `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, and `CHAT_ID_HMAC_SECRET`; configure at least one LLM provider. 
The example file is a template, not a ready-to-use production configuration.
3. Install locked dependencies:

   ```sh
   uv sync --all-groups
   ```

4. Start the production-style stack:

   ```sh
   docker compose up --build
   ```

5. Open `http://localhost:8000`. The API health endpoint is `http://localhost:8000/health`.

For active development, start the override instead:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- The development override mounts `app/` (and read-only `data/`) into the container and enables Uvicorn reload, so Python and browser-client edits take effect without rebuilding. 
- Changes to application dependencies or the app Dockerfile require rebuilding; source edits do not. 
- The base Compose file runs without reload and sets `APP_ENV=production`. It does not mount host source into `/app`; the database mounts only its two read-only initialization scripts. 
- PostgreSQL is not published to the host and uses a non-superuser application role. 
- Ollama must be reachable from the app container; on Linux Compose maps `host.docker.internal` to the host gateway.

The database uses the prebuilt `pgvector/pgvector:pg16` image; Compose pulls it from its registry when it is not already local. No project-specific database image or registry upload is needed. The SQL and role setup scripts are mounted read-only into PostgreSQL's initialization directory. PostgreSQL runs those scripts only when creating a new, empty `postgres_data` volume; edits to them do not reinitialize an existing database. Use a real migration for an existing database, or reset only the development database volume if you intentionally want a fresh database.

## Development workflow and applying changes

### Start the development stack

From the repository root, make sure `.env` is configured, then start the development Compose configuration:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Compose merges the two files, with `docker-compose.dev.yml` overriding or extending the base configuration. The development override mounts the local `app/` and read-only `data/` directories into the app container and enables Uvicorn reload. Keep this terminal open to see startup output and stop the stack with `Ctrl+C`.

To run it in the background instead:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

Open `http://localhost:8000` for the chat and `http://localhost:8000/health` for development diagnostics. Run tests on the host (not inside the app container, whose production image does not include the test suite or development dependencies):

```sh
uv sync --all-groups
uv run pytest
```

For a focused test, pass its path, for example `uv run pytest tests/test_dialogue.py`. Most unit/API tests use fakes; database-backed retrieval or ingestion also needs the Compose database and a reachable Ollama embedding model.

### What the log command means

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f app
```

- The first `-f docker-compose.yml` selects the base Compose file.
- The second `-f docker-compose.dev.yml` adds the development overrides.
- `logs` reads output from containers in the selected Compose project.
- The `-f` after `logs` means **follow**: keep printing new log lines as they appear. Press `Ctrl+C` to stop following; this does not stop the containers.
- `app` selects only the app service. Use `db` to view PostgreSQL logs, or omit the service name to follow all services.

For example:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f db
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

### Which changes need a restart or rebuild?

| Change | Development stack | Production-style stack |
|---|---|---|
| Python files under `app/` | The bind mount and Uvicorn reload apply changes automatically. | Rebuild/recreate the app: `docker compose up -d --build app`. |
| Browser files under `app/web/` | The bind mount exposes changes; refresh the browser (hard-refresh if cached). | Rebuild/recreate the app, then refresh: `docker compose up -d --build app`. |
| `.env` values used by Compose or the app | Recreate the affected service so it receives the new environment. For app settings: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate app`. | For app settings: `docker compose up -d --force-recreate app`. A rebuild is not normally needed unless the image/build inputs changed. |
| `pyproject.toml`, `uv.lock`, or app `Dockerfile` | Rebuild/recreate the app: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build app`. | Rebuild/recreate the app: `docker compose up -d --build app`. |
| Compose YAML | Re-run `up` with the same file list; use `--force-recreate` if you need to ensure the changed service configuration is applied. | Re-run `docker compose up -d`; use `--force-recreate` if needed. |
| `data/registry.yaml` or source Markdown | The data bind mount makes the files visible, but rebuild the knowledge index with the command below. | Data is copied into the image, so rebuild/recreate the app first, then run the index build. |
| `db/schema.sql` or the role-init script | These are first-initialization scripts, not migrations. Apply a deliberate SQL migration to an existing database. | Same behavior: container recreation does not rerun initialization scripts on an existing database volume. |

For the full source-index command while using development Compose:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app \
  uv run --no-sync python -m scripts.build_knowledge_base
```

For production-style Compose, the equivalent command is:

```sh
docker compose exec app uv run --no-sync python -m scripts.build_knowledge_base
```

An app restart is not the same as an image rebuild: use `--force-recreate` to apply changed environment values, and `--build` when dependencies, the Dockerfile, or files copied into the image have changed. Running `up` with the same Compose file list is important so the correct configuration is used.

Changing `APP_DB_PASSWORD` in `.env` alone does not rotate the password of the already-created PostgreSQL role. The database role must be updated too, and then the app container recreated with the new URL/password. Likewise, `POSTGRES_PASSWORD` initializes PostgreSQL's administrator password only when its data volume is first created. Do not publish or paste `.env` values into logs or support messages.

To stop containers without deleting database data:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

Do not add `-v` unless you intentionally want to delete the database volume and all its stored data.

## Configure the model providers

Set `LLM_PROVIDER_ORDER` to an ordered comma-separated list of `gemini`, `openrouter`, and `ollama`. Providers without required credentials/model configuration are omitted. Configure model IDs and API keys only through `.env`; do not put them in source files. For Ollama, configure `OLLAMA_MODEL`, run Ollama on the host, and pull the selected chat and embedding models there.

Provider inputs and outputs are never logged. The router makes one structured-output repair attempt, then fails over to the next provider. If all providers fail, the user receives a localized temporary-unavailability message.

## Debugging and logs

Logging stays enabled in both environments. Set `LOG_LEVEL=DEBUG` in `.env` for more server-side diagnostics, or leave it at `INFO` for routine use. The development Compose override sets `DEBUG`; production defaults to `INFO`. The API writes timestamped logs to standard output. While running the development stack, follow app logs with:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f app
```

For the production-style stack, use `docker compose logs -f app`. In both commands, `logs -f` follows new output; `Ctrl+C` stops following logs, not the containers.

The server logs a request ID with route, status, duration, and safe stage/error metadata; it deliberately omits chat text, session IDs, API keys, and database URLs. Development API errors may show an allowlisted stage, exception type, HTTP status, and request ID in the chat for debugging. Production chat errors show only a localized generic message; the request ID remains server-side. Stack traces, exception messages, database/provider details, and submitted request data are never included in API error responses. Production `/health` returns only readiness status; development `/health` includes subsystem diagnostics.

Router failures now log a safe `error_category` and, when available, the public model ID and HTTP status. Common categories:

- `rate_limited` — provider returned HTTP 429; check provider quotas and `Retry-After`.
- `provider_overloaded_or_unavailable` — provider returned a 5xx response; retry/failover is attempted.
- `authentication_failed` / `permission_denied` — check the API key, account access, and model permissions. Key values are never logged.
- `model_or_endpoint_not_found` — check the configured model ID and provider endpoint.
- `billing_or_credits` — provider returned HTTP 402; check account credits/billing.
- `invalid_request_or_model_parameters` — the request or structured-output settings may not be supported by that model.
- `provider_timeout` / `connection_error` — check connectivity, service availability, and timeout settings.
- `invalid_structured_output` / `malformed_provider_response` — provider responded but did not return the expected JSON shape.
- `missing_api_key`, `missing_model`, or `missing_models` — provider was disabled during startup because required configuration was absent.

Logs contain provider/model identifiers, status, and error categories only—not prompt text, response bodies, API keys, or raw exception messages.

In development, check `http://localhost:8000/health` for the database state, configured LLM provider names, last provider used, and indexed verified-chunk count. In production, health intentionally reports only `ok`, `degraded`, or `unavailable`. For deployment diagnosis, check that `.env` exists, `DATABASE_URL` points to the `db` Compose service, and the database container completed schema initialization. Configure at least one provider key and model in `.env`. `docker compose logs -f db` shows PostgreSQL startup and initialization errors.

Typical failure meanings:

- **Browser says the service is unavailable:** the API may be stopped or a backend dependency may be unavailable. Use server logs and `/health` during development; production intentionally shows no internal diagnostics.
- **HTTP 503:** `DATABASE_URL` is missing/wrong, PostgreSQL is stopped/unreachable, or initialization did not create the schema. In the current local prototype, without Docker or a separate PostgreSQL server, this response is expected.
- **Temporary LLM-unavailable message:** the health payload has no configured providers, or each configured provider timed out/failed. Set a provider API key and model, or ensure Ollama is reachable.
- **Fallback saying verified information was not found:** service/model connection succeeded, but there are no relevant verified chunks. Review and index source text; this is intentionally not treated as a service error.

For local diagnosis, after copying `.env.example` and starting a local PostgreSQL server, use `APP_ENV=development LOG_LEVEL=DEBUG uv run uvicorn app.main:app --reload` and inspect the terminal running Uvicorn. In Compose, use the development override above and `docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f app`. The `.env.example` uses `DATABASE_URL` for a locally installed PostgreSQL; Compose overrides its host to `db`. Do not paste database URLs, API keys, or user messages into bug reports.

## Add sources and populate the vector database

The assistant does not learn or fine-tune its chat model when you add documents. This project uses retrieval-augmented generation (RAG): it stores reviewed text chunks and their embedding vectors in PostgreSQL with pgvector, finds relevant chunks for a user's question, then asks the chat model to answer using that evidence. Only chunks from `verified` sources can be retrieved.

The initial Adilet registry entry points to [the supplied document](https://old.adilet.zan.kz/rus/docs/K2000000350), but remains `needs_verification`; its Markdown file contains no legal text and is not indexed.

### 1. Prepare a source file

Use an official publisher and identify the exact page or document passage relevant to an in-scope question. Check the current wording, effective date, jurisdiction, and applicability. A URL, downloaded PDF, or automated text extraction is not by itself verification.

Add the reviewed passage as plain Markdown in `data/sources/<source_id>.md`. The filename must exactly match the registry entry's `source_id`. Keep each instruction, rule, or contact block self-contained; keep qualifications, contact details, and what a contact is for together. The ingestion script splits long text on paragraph and sentence boundaries into chunks of up to about 800 characters. Do not add secrets or personal data.

PDFs and web pages are not ingested automatically in this MVP. You may copy or extract the relevant text into the Markdown file, but a human must compare it with the official source before marking it verified. Do not paraphrase legal text as if it were a quotation or official wording.

### 2. Add the source metadata

Add a matching entry to `data/registry.yaml`. Use a unique, stable `source_id`; `category` must be one of the supported categories (`garbage`, `lighting`, `heating`, `water`, `roads`, `playground`, `snow`, `appeals`, `principles`, or `general`).

```yaml
- source_id: almaty-lighting-procedure
  title: "Exact title from the official page"
  publisher: "Official publisher"
  url: "https://official.example.kz/page"
  language: ru
  category: lighting
  checked_at: 2026-10-15
  status: needs_verification
  claims:
    - "A short statement of what the passage confirms"
```

Replace the example title, publisher, URL, date, and claim with facts checked against the real source. `language` must be `ru` or `kk`. Keep `status: needs_verification` while the text is awaiting review. Once a human has verified the content and metadata, change it to `verified`. Sources with `needs_verification` or `excluded` status are not indexed; the `claims` list documents the scope of the source and does not replace the source text.

### 3. Confirm PostgreSQL and the embedding model are ready

Start the stack, if it is not already running:

```sh
docker compose up -d
```

Ollama must be running on the host and reachable from the app container at the URL configured by `OLLAMA_EMBEDDING_URL` (default in Compose: `http://host.docker.internal:11434/api/embed`). Check the installed models on the host:

```sh
curl http://localhost:11434/api/tags
```

The embedding model configured by `EMBEDDING_MODEL` must be installed in Ollama and return 1024-dimensional vectors, because `db/schema.sql` declares `embedding vector(1024)`. Use the same embedding model and settings for indexing and later retrieval; changing embedding models requires rebuilding the vectors for all sources.

### 4. Build or refresh the index

Run this after the source file and registry entry are ready:

```sh
docker compose exec app uv run --no-sync python -m scripts.build_knowledge_base
```

The command reports how many verified chunks were indexed. It embeds `source title + chunk text` with Ollama and stores the chunk text, source metadata, and vector in PostgreSQL. Re-running it replaces the chunks for each verified source, so edits to source text are reflected in the index. It also removes chunks for sources no longer verified or removed from the registry; review registry changes carefully before running it.

When developing with the reload override, use the same Compose files for commands:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app \
  uv run --no-sync python -m scripts.build_knowledge_base
```

The production-style Compose service does not mount host source/data files into the app container. After changing source files or the registry, rebuild the app image before running ingestion there:

```sh
docker compose up -d --build app
docker compose exec app uv run --no-sync python -m scripts.build_knowledge_base
```

### 5. Verify stored text, vectors, and retrieval

Check source and chunk counts, and confirm every stored vector has the required dimension:

```sh
docker compose exec -T db psql -U postgres -d adal -c \
  "SELECT s.source_id, s.status, count(c.chunk_id) AS chunks
   FROM sources s LEFT JOIN chunks c USING (source_id)
   GROUP BY s.source_id, s.status ORDER BY s.source_id;"

docker compose exec -T db psql -U postgres -d adal -c \
  "SELECT count(*) AS chunks,
          count(embedding) AS chunks_with_embeddings,
          min(vector_dims(embedding)) AS min_dimensions,
          max(vector_dims(embedding)) AS max_dimensions
   FROM chunks;"
```

Inspect a few stored passages (do not print the full embedding vectors):

```sh
docker compose exec -T db psql -U postgres -d adal -c \
  "SELECT c.chunk_id, s.status, s.category, s.title, c.content
   FROM chunks c JOIN sources s USING (source_id) LIMIT 5;"
```

Finally, test retrieval with likely Russian and Kazakh phrasings and the matching category:

```sh
docker compose exec app uv run --no-sync python -m scripts.inspect_retrieval \
  "не работает уличное освещение" --category lighting
docker compose exec app uv run --no-sync python -m scripts.inspect_retrieval \
  "көше жарығы жұмыс істемейді" --category lighting
```

The script prints matching chunks and scores after embedding the query with the configured Ollama model. No results can mean the source is not verified, no chunks were indexed, the query embedding failed, or the text is not sufficiently similar; check logs and the database counts before adjusting `RETRIEVAL_MIN_SCORE`. Also test unrelated queries to ensure they do not retrieve misleading passages. The app should fall back when verified evidence is absent or insufficient.

## API contract

- `GET /health` — production returns readiness status only; development also reports subsystem status and the last provider used. Neither mode exposes user text or secrets.
- `POST /chat` — JSON request:

  ```json
  {"session_id":"opaque-browser-session","message":"Во дворе не вывезли мусор","action":"message"}
  ```

  `action` may be `message`, `confirm`, `correct`, or `reset`. Responses have a status (`confirmation`, `clarification`, `answer`, `fallback`, `reset`, or `error`), localized reply, and optional citations.

The browser stores only a random opaque session key; PostgreSQL stores an HMAC-SHA256 digest and compact dialogue fields, not raw message history. Avoid sending IIN, passwords, EDS keys, or unnecessary personal information.

For civic issues, an unnamed city defaults to Almaty. The assistant does not ask for the city or repeat a recognized problem category; it asks a follow-up only when a missing place/detail could change the instructions. Explicitly naming a city outside Almaty still triggers the scope fallback.

## Architecture

```text
Browser web chat
      │ POST /chat
      ▼
FastAPI ── DialogueService (Python-owned state transitions)
                 ├── LLM router: Gemini → OpenRouter → Ollama
                 ├── answer/relevance/citation guards
                 ├── local Ollama embeddings
                 └── persistence and verified-only retrieval
                           │
                    PostgreSQL + pgvector
```

The dialogue service coordinates injected classifier, retriever, answerer, and repository interfaces; it does not issue SQL or call providers directly. The web client only renders state and sends user actions. A future Telegram adapter should call the same API and must not implement a second copy of the business flow.

## Code tour

- `app/main.py` wires runtime dependencies, exposes the API and health diagnostics, and logs request IDs/status/duration without message bodies.
- `app/application/dialogue_service.py` owns confirmation-before-retrieval, clarification, city boundary, and compact privacy-conscious state.
- `app/ai/intent.py` defines the structured issue classification contract; `app/ai/llm/` implements provider adapters and fallback/circuit-breaker behavior.
- `app/ai/retrieval.py` embeds the query locally and asks PostgreSQL for verified chunks only; `app/ai/answer.py` and `app/ai/guards.py` enforce evidence and citations.
- `app/knowledge/` reads human-reviewed files and indexes only registry entries marked `verified`.
- `app/web/` is a thin browser client; it sends messages/actions to `/chat`, displays citations, and follows the development/production error-disclosure policy.
- `db/schema.sql` defines source metadata, vector chunks, and compact conversation state.

## Test

Unit/API tests use a fake provider and in-memory conversation repository; they require no database, real model, or API keys:

```sh
uv run pytest
```

The integration path that exercises pgvector requires the Compose services to be running, Ollama with the configured embedding model, and verified source material.

## Current limitations

- The provided Adilet source has not yet been reviewed for a specific passage and remains excluded from retrieval.
- The prototype starts without seeded verified civic chunks; until sources are reviewed and indexed, substantive questions correctly fall back.
- The initial chat UI is intentionally minimal. Telegram, evaluation corpus expansion, database TTL cleanup, and PDF/OCR processing are follow-on work.
