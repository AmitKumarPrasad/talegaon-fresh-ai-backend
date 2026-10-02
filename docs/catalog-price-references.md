# FRESHORA catalog references — 2 October 2026

The catalog contains 44 products across 10 categories. This batch adds thick
poha (500 g), moong dal (1 kg), turmeric powder (100 g), and aloo bhujia (200 g).
Product URLs, exact pack sizes, observed prices and check dates are recorded in
`app/catalog_references.json`. Prices are public online benchmarks, without a
Talegaon delivery postcode selected. They can vary by location, promotion and
date. They are defaults for missing products, not automatic live selling prices.

Existing admin prices, inventory, pack sizes and custom photos are retained by
both the migration and seed endpoint. New defaults for sunflower oil use the
currently listed 800 g pouch; existing stock retains its pack size until the
admin confirms the pack being sold. Existing price history is not rewritten.

Image URLs for 23 packaged products were opened from their retailer product
pages. Only empty images and the known fabricated CDN URLs from the previous
seed are replaced. Sugar uses bb Popular only as a price benchmark; its branded
package image is omitted because the catalog item is unbranded. Fresh produce
continues to use the bundled Flutter photos. Retailer image links depend on
external availability; Flutter already handles failed images with a fallback.

Migration 0015 inserts the four staples and fills images on deployment. The
existing `/products` API exposes category and image URL; the category filters
merged in Flutter PR #59 display these products without another app schema change.

Further assortment gaps: rava, besan, chana dal, masoor dal, sabudana, peanuts,
jaggery, ghee, buttermilk, coffee, additional seasonal produce, dry fruits and
household cleaning products. Eggs and frozen goods depend on the intended
assortment and handling facilities. Confirm supplier availability and local
purchase costs before expanding those lines or promising stock.
