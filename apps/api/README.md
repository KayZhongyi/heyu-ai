# API development

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

Tests use an isolated SQLite database. Production and Compose use PostgreSQL.

## Database migrations

Schema changes are managed with Alembic. Do not use `Base.metadata.create_all()` in
production.

```bash
alembic upgrade head
alembic current
```

To verify that a migration is reversible on a disposable database:

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Docker Compose runs `alembic upgrade head` before the API starts.

## AI providers

The default provider is deliberately offline and free:

```env
AI_PROVIDER=mock
AI_MODEL=deterministic-v1
```

It composes reviewed facts deterministically. It is not presented as a large
language model.

To connect a server that implements the OpenAI-compatible
`POST /v1/chat/completions` contract, copy `.env.example` to `.env` and set:

```env
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-model-name
AI_API_KEY=your-own-api-key
AI_TIMEOUT_SECONDS=45
```

The API key is read only from the runtime environment. It is not returned by
the API, persisted in the database, written to generation records, or committed
to the repository. Enabling this provider may incur charges from the provider;
the application never enables it automatically.

Provider responses must contain a JSON object. Invalid, timed-out, or
non-successful responses produce a generic `502` error without including the
credential or the upstream response body. Generation provenance records the
adapter name and configured model, while reviewed knowledge remains the only
context supplied as factual source material.
