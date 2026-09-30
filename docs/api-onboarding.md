# API onboarding

## Interactive API documentation

- Swagger UI: /docs
- ReDoc: /redoc
- OpenAPI JSON: /openapi.json

## Authentication

Customer APIs use `Authorization: Bearer <JWT>`.

Obtain a token through:
- POST /auth/request-otp
- POST /auth/verify-otp

Admin APIs use `X-Admin-Token: <ADMIN_API_TOKEN>`.

## Customer integration sequence

1. Request OTP.
2. Verify OTP and store the JWT securely on the device.
3. Load products with GET /products.
4. Optionally create/manage addresses.
5. Create an order with POST /customers/me/orders.
6. For UPI orders, create/reuse the payment link and complete the payment confirmation flow.
7. Read orders with GET /customers/me/orders or a specific order endpoint.
8. Read the lifecycle timeline with GET /customers/me/orders/{order_id}/status-history.
9. Use POST /customers/me/ai/chat for customer-facing order/tracking assistance.

## Checkout rules

- Product price is resolved server-side.
- Inventory reservation is transactional.
- Insufficient inventory returns HTTP 409.
- Customer order queries are scoped to the authenticated customer.
- Seller notification happens after the order commits; notification failure does not roll back a successful order.

## Common responses

| Status | Meaning |
|---|---|
| 200 | Successful request |
| 400 | Invalid request/business input |
| 401 | Missing or invalid authentication |
| 404 | Resource not found or not owned by the customer |
| 409 | Inventory, payment, or lifecycle conflict |
| 429 | Rate limit exceeded |
| 503 | Temporary dependency/service failure |

## Mobile AI tracking

If a customer asks to track an order without an Order ID, the API asks for the Order ID shown in My Orders. The numeric follow-up uses persistent conversation state and remains scoped to that customer.

## Production configuration

See `.env.example` for environment variable names. Never commit real secrets, JWT signing keys, admin tokens, payment credentials, WhatsApp secrets, or API keys.

## Postman

Import `/openapi.json` from a running environment into Postman to generate an API collection. Set the collection base URL and authentication variables before sending requests.
