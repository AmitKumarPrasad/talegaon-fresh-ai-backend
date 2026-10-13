# FRESHORA customer MCP

The backend exposes two read-only tools using the official MCP Python SDK:
`search_products` and `get_my_order_status`. The transport is stateless
Streamable HTTP and returns JSON. It reads the existing database and does not
call OpenAI or need a model API key.

## Enable on the backend

Install the updated requirements and deploy normally. Set:

```dotenv
MCP_ENABLED=true
MCP_ALLOWED_HOSTS=YOUR_ACTUAL_BACKEND_HOST.onrender.com
```

The host must be the actual hostname, without scheme, path or wildcard. For
local development use `localhost:*,127.0.0.1:*`. DNS rebinding checks remain
enabled. Browser origins must also be in the existing `CORS_ALLOWED_ORIGINS`.
The endpoint is `https://YOUR_ACTUAL_BACKEND_HOST.onrender.com/mcp/` (trailing
slash). MCP is disabled by default; `/health`, `/ready` and all commerce APIs
continue to work. No migration or Flutter rebuild is required for these tools.

## Connect a trusted backend MCP client

Use a normal, current customer access token obtained via the existing customer
PIN login. Do not use admin or partner tokens. Keep the token server-side, never
in prompts, committed config, logs or shared screenshots. Launch one MCP client
per authenticated customer request and forward only that customer's token.
Never run all customers through one shared account/token.

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def read_order(endpoint: str, customer_access_token: str, order_id: int):
    async with streamablehttp_client(
        endpoint,
        headers={"Authorization": f"Bearer {customer_access_token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(
                "get_my_order_status", {"order_id": order_id}
            )
```

Every HTTP request rechecks signature, expiry, customer existence and session
revocation. The order tool derives the owner from verified identity, not tool
arguments. It excludes addresses, phone numbers, payment links and delivery
codes. Unknown/other customers' orders produce the same error. Discovery also
requires authentication; responses are not cacheable. Production uses the
existing Redis limiter (30 requests per IP per minute) and fails closed when
Redis is unavailable.

This transport supports programmatic clients with pre-issued FRESHORA bearer
tokens. It does **not** implement OAuth discovery/login and is not yet a
ChatGPT remote connector. No public OAuth endpoint or API key was created.
Do not paste customer credentials into ChatGPT connector fields.

## Scope and validation

When `MCP_ENABLED=true`, the existing `/customers/me/ai/chat` endpoint uses
the MCP tools with the existing Render `OPENAI_API_KEY` and `OPENAI_MODEL`.
The backend connects to its own authenticated MCP ASGI transport in-process:
customer JWTs are not sent to OpenAI or another network host. OpenAI receives
the chat message and redacted catalog/order tool results. Responses are sent
with `store=false`; this does not imply zero retention at the provider.
All reasoning and tool-call items are replayed within that one request.
Order lookups without an ID return only the authenticated customer's latest
order; an explicitly supplied ID is never replaced by a guessed/latest ID.

The loop allows at most three model rounds and four read-only tool calls,
has a 40-second overall deadline and makes no automatic provider retries.
Each customer request gets a fresh MCP session and no shared conversation.
Expired/revoked authentication, provider and transport failures return a safe
503, without an ungrounded AI fallback. Incomplete/empty/budget-exceeded model
responses direct the customer to Products/My Orders. MCP-disabled deployments
keep the existing deterministic chat behavior. Reviewer accounts keep their
isolated demo flow. No Flutter rebuild or additional API key is needed.

Admin/partner tools are follow-up integrations and must retain their own role
checks. There are no cancel/order/price-write tools.

Run `python -m pytest tests/test_mcp_server.py -q` for transport initialization,
tool discovery, real catalog reads, ownership isolation, revoked sessions,
redaction, input limits and host/origin security tests. The complete backend
suite is run by CI before merge. After deployment, connect with a valid test
customer session and call both tools before declaring the live integration
ready.
