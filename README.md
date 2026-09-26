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

## Production deployment

Build the image with Docker and provide production environment variables at runtime. The image runs Alembic migrations before starting FastAPI and listens on 0.0.0.0 using PORT.

Health endpoint: GET /health

Set ENVIRONMENT=production in production. The application then requires its production configuration and rejects SQLite.

For a multi-instance deployment, run Alembic as a separate release or migration job rather than concurrently from every application instance.


## Seller/admin order operations

Use the same `X-Admin-Token` header for protected order operations.

- `GET /admin/orders` — list recent orders; optional `status`, `limit`, and `offset` filters
- `GET /admin/orders/{order_id}` — view order details, items, payment, address, and allowed next statuses
- `PATCH /admin/orders/{order_id}/status` — advance an order through the validated lifecycle

Example status update:
```json
{"status":"PACKING"}
```

Order status changes use the centralized lifecycle rules, so invalid jumps such as `PENDING -> DELIVERED` are rejected.
