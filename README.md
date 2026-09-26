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


## Daily product prices

Set `ADMIN_API_TOKEN` in the environment. Send it as the `X-Admin-Token` header when managing prices.

- `GET /admin/prices` — view current product prices and stock
- `PUT /admin/prices/{product_id}` — update price and optional stock state
- `GET /admin/prices/{product_id}/history` — view recent price changes

Example request body:
```json
{"price": 55.0, "in_stock": true}
```

Customer orders always calculate totals from the current database price; the AI does not choose prices.
