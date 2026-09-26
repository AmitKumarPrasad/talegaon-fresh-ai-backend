# Talegaon Fresh AI Backend

WhatsApp AI ordering backend for Talegaon Fresh.

## Stack
- Python
- FastAPI
- OpenAI API
- WhatsApp Cloud API
- MySQL (next phase)

## Local setup

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Environment variables are documented in `.env.example`. Never commit secrets.


## Database migrations

This project uses Alembic for schema versioning.

Fresh database:
```bash
alembic upgrade head
```

Create a new migration after a model change:
```bash
alembic revision --autogenerate -m "describe change"
```

For an existing database already created with the legacy SQL files, verify that its schema matches the current Alembic baseline before running:
```bash
alembic stamp head
```
Do not stamp an unverified database; back up production data first.
