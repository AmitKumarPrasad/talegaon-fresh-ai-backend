# Talegaon Fresh AI Backend

Mobile-first backend for Talegaon Fresh, with optional AI assistance. WhatsApp and Razorpay integrations remain available in the codebase for later activation but are not required for the current mobile production deployment.

## Stack
- Python
- FastAPI
- PostgreSQL
- Redis
- OpenAI API (optional AI assistant)

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

### Product catalog categories

The customer catalog now carries a stable `category` field. Baseline categories are Vegetables, Leafy Greens, Fruits, Dairy, Grocery, Snacks, Masala & Spices, Beverages, Bakery & Breakfast, and Instant Food.

The baseline packaged-goods prices are reference values used only when a catalog item is first initialized. Retail prices vary by date and delivery area, and fresh-produce prices can move daily. Production selling prices remain server-authoritative and should be maintained with the admin price APIs; catalog seeding does not overwrite an existing product's price or stock.


## Production deployment

Build the image with Docker and provide production environment variables at runtime. By default, the image runs Alembic migrations before starting FastAPI and listens on 0.0.0.0 using PORT. Set `RUN_MIGRATIONS=false` when migrations are executed by a separate release/migration job (recommended for multi-instance deployments).

Liveness endpoint: GET /health  
Readiness endpoint: GET /ready

`/health` only confirms that the application process is running. `/ready` verifies the PostgreSQL and Redis dependencies and returns HTTP 503 while either dependency is unavailable. Configure the platform health check to use `/ready` when deployment should only receive traffic after both dependencies are reachable.

Set `ENVIRONMENT=production` in production.

### Required production environment

These variables are required for the mobile production service:

- `DATABASE_URL` using PostgreSQL
- `REDIS_URL` using `redis://` or `rediss://` for distributed rate limiting
- `ADMIN_API_TOKEN`
- `JWT_SECRET` — unique random secret, at least 32 characters; keep it stable across deployments

The service rejects SQLite and non-PostgreSQL production database URLs. Production also rejects non-Redis `REDIS_URL` values.

### Optional AI environment

`OPENAI_API_KEY` is optional. When configured, the backend can use the existing AI assistant functionality. When it is not configured, the mobile commerce APIs can still start and operate normally; AI-dependent responses return a safe configuration message instead of preventing application startup.

Keep `OPENAI_MODEL` configurable as needed.

### Deferred external integrations

The following are not required for the current mobile-only production deployment:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `SELLER_WHATSAPP_NUMBER`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`

Do not add these variables to Render unless/ until the corresponding integrations are activated.

For a multi-instance deployment, run Alembic as a separate release or migration job rather than concurrently from every application instance.

## Seller/admin order operations

Use the same `X-Admin-Token` header for protected order operations.

- `GET /admin/orders` — list recent orders; optional `status`, `limit`, and `offset` filters
- `GET /admin/orders/{order_id}` — view order details, items, payment, address, and allowed next statuses
- `PATCH /admin/orders/{order_id}/status` — advance an order through the validated lifecycle

## Mobile production scope

Dashboard revenue uses Indian calendar days (UTC+05:30), grouped by the order's
creation date. It counts verified UPI orders and delivered COD orders; cancelled,
unpaid, and undelivered COD orders are excluded. This is an order-cohort report,
not a payment settlement report.

Run the complete regression suite with `python -m pytest -q`. CI runs the same
suite, including PIN authentication, customer checkout, and revenue tests.

The current production path is:

`Flutter mobile app -> FastAPI -> PostgreSQL`

The core flow includes authentication, addresses, cart, product catalog, order creation, order history/details, server-authoritative pricing, inventory, and admin order operations.

AI is an optional layer on top of the core commerce flow; it must not determine prices, stock, payment results, or authoritative order totals.

