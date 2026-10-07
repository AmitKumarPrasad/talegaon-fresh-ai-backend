# Customer reviewer checkout

Delivery checkout requires an address containing Talegaon, PCMC, Pimpri-Chinchwad or a recognized PCMC locality (including Ravet). This is a locality check, not proof that a GPS position or street address is authentic. Customers outside these localities can sign in and browse.

The dedicated test account is identified server-side by `REVIEWER_CUSTOMER_PHONES` (comma-separated). The default identifies the existing owner-approved reviewer account. Set this variable to an empty string to disable reviewer mode or supply different registered test accounts. Normal hashed PIN authentication and JWT ownership checks always apply; no PIN is stored in source code and no client-provided flag enables demo mode.

Run Alembic migrations before starting the new backend. Reviewer checkout writes only `reviewer_orders`, never production orders/items, stock, payouts, revenue, seller alerts or delivery partner notifications. Orders are immediately marked as simulated delivered orders to exercise details, tracking, messages and post-delivery suggestions without a physical delivery or payment. Reviewer messages and suggestions stay in the same isolated snapshot. Earlier real orders belonging to this account are not returned through the reviewer order endpoints.

Use the new customer build to display the reviewer banner. Reusable reviewer login works from any location; an address can be entered manually and no GPS or SMS OTP is required. Verify a demo order after deployment before completing the Google Play full-access declaration. Do not change the account PIN while Google reviews the app or updates.
