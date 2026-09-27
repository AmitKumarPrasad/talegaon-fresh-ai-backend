# Talegaon Fresh AI Backend

WhatsApp AI ordering backend for Talegaon Fresh.

## Stack
- Python
- FastAPI
- OpenAI API
- WhatsApp Cloud API
- PostgreSQL

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

Set ENVIRONMENT=production in production. The application then requires its production configuration, including a PostgreSQL DATABASE_URL, and rejects SQLite and non-PostgreSQL production database URLs.

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

## Production WhatsApp and Razorpay E2E checklist

Before switching to live payment processing, validate the production integration in Razorpay test mode.

### Required production environment

Set `ENVIRONMENT=production` and configure:

- `OPENAI_API_KEY`
- `DATABASE_URL` using PostgreSQL
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `SELLER_WHATSAPP_NUMBER`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `ADMIN_API_TOKEN`

Never commit these values to Git.

### E2E sequence

1. Verify `GET /health`.
2. Verify the Meta WhatsApp webhook challenge against `WHATSAPP_VERIFY_TOKEN`.
3. Send a test WhatsApp message and confirm the backend receives the webhook.
4. Place a test order and confirm the order is persisted with the current database prices.
5. Provide an address and select COD; verify `CONFIRMED` status and seller notification.
6. Start another test order and select UPI.
7. Confirm a Razorpay payment link is generated for the exact order total.
8. Configure Razorpay's webhook endpoint as `POST /razorpay/webhook` and use the configured webhook secret.
9. Complete a Razorpay test payment and verify the webhook changes the order to `CONFIRMED`.
10. Verify duplicate WhatsApp/Razorpay webhook deliveries do not create duplicate processing or notifications.
11. Exercise admin order status changes through `PACKING -> OUT_FOR_DELIVERY -> DELIVERED`.
12. Only after all test-mode checks pass, replace test credentials with live credentials and repeat a controlled low-value live transaction.

The application cannot perform these external-provider checks from CI because they require real Meta/Razorpay credentials and provider-side configuration.
