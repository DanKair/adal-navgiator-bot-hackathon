# Copilot instructions for Adal Navigator

## Project snapshot

This repository is the Adal Navigator civic-assistant prototype for Almaty. The app is a browser chat front end backed by FastAPI, Python business logic, and PostgreSQL + pgvector for dialogue state and verified source chunks.

The core product rule is: no verified source, no substantive claim. The dialogue flow requires a confirmation step before retrieval, source-backed answers must cite retrieved chunks, and unsupported questions fall back instead of guessing.

Primary docs to consult before deeper changes:
- `README.md`
- `AGENTS.md`
- `CONTEXT.md`

## Build, test, and validation commands

Install dependencies:

```bash
uv sync --all-groups
```

Run the full test suite:

```bash
uv run pytest
```

Run one test file:

```bash
uv run pytest tests/test_api.py
uv run pytest tests/test_dialogue.py
uv run pytest tests/test_guards.py
```

Run a single test by name:

```bash
uv run pytest tests/test_api.py -k health
uv run pytest tests/test_dialogue.py -k confirmation
```

Run the local stack:

```bash
docker compose up --build
```

Run the dev override with hot reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Inspect app logs:

```bash
docker compose logs -f app
```

The repo defines Ruff settings in `pyproject.toml`, but there is no project script wrapper for linting. If linting is needed in a local environment, use:

```bash
uvx ruff check app tests
```

## High-level architecture

The app is deliberately split into a few layers, and most behavior depends on wiring across them:

- Browser UI (`app/web/`) sends chat requests to the FastAPI service.
- `app/main.py` is the composition root: it wires settings, the database, the LLM router, the retrieval layer, the answer pipeline, and the dialogue service.
- `app/application/dialogue_service.py` owns the conversation state machine and enforces the confirmation/clarification flow. It does not reach into SQL or provider-specific logic directly.
- `app/ai/intent.py` classifies the user message (civic issue, principles question, small talk, out of scope) and extracts fields like category/summary/city.
- Retrieval (`app/ai/retrieval.py`) pulls only verified source chunks from PostgreSQL/pgvector using the same embedding model for indexing and querying.
- `app/ai/answer.py` and `app/ai/guards.py` implement the grounded-answer pipeline: retrieve chunks, generate an answer, validate citations and fact grounding, then fall back if the evidence is insufficient.
- `app/ai/llm/` contains the provider protocol and providers (Gemini, OpenRouter, Ollama), plus the router that retries/fails over between them.
- `app/persistence/` handles the async SQLAlchemy session and conversation storage.
- `data/` and `db/schema.sql` define the human-reviewed source registry and the PostgreSQL schema (`sources`, `chunks`, `conversations`).

The repo is intentionally not a microservice architecture; the main product boundary is "browser → FastAPI → dialogue logic → retrieval + LLM → PostgreSQL".

## Key conventions specific to this codebase

- Confirmation before retrieval is required. The LLM summary must be confirmed by the user before the app does any retrieval or answer generation.
- Only `status: verified` entries are eligible for search; unverified or excluded entries are ignored by the retrieval path.
- Session IDs are hashed with HMAC before persistence. The app stores compact state only and does not keep raw message history.
- Secrets never live in source files; they must come from `.env` and Compose environment variables. The repo expects `.env` to exist locally, and `.env.example` is the template.
- The app intentionally falls back for unsupported or weakly supported answers instead of guessing. Guard logic checks citations and grounded facts before returning an answer.
- The repo distinguishes Almaty-only guidance from other-city questions; non-Almaty cities trigger a fallback message instead of local contact recommendations.
- Language detection uses Kazakh-specific characters to choose Kazakh (`kk`); otherwise Russian (`ru`). `app/i18n.py` holds the localized strings.
- The database is initialized by Compose with a non-superuser application role, and the runtime only exposes the app port (`8000`) while PostgreSQL stays internal to the Compose network.
- Changes in retrieval or answer safety should be paired with the relevant regression tests (`tests/test_guards.py`, `tests/test_dialogue.py`, or API tests), not only with a broad suite.

## Working style for this repo

Prefer the smallest relevant path when fixing or extending behavior:

1. Read the task-specific docs (`README.md`, `AGENTS.md`, `CONTEXT.md`) and the affected runtime files.
2. Trace the request from `app/main.py` into the dialogue service and the exact collaborator being changed.
3. Add or update the matching test before finishing the implementation.
4. Validate with the narrowest relevant pytest command, then widen only if the change truly crosses boundaries.

This project is safety-sensitive and source-grounded: preserve the confirmation flow, citation requirements, and fallback behavior unless the task explicitly changes them.
