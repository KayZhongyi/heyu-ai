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
