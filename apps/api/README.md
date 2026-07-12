# API development

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

Tests use an isolated SQLite database. Production and Compose use PostgreSQL.

