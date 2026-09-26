from app.catalog import PRODUCTS

ALIASES = {
    "tamatar": "Tomato", "tomato": "Tomato",
    "aloo": "Potato", "potato": "Potato",
    "pyaz": "Onion", "onion": "Onion",
    "gajar": "Carrot", "carrot": "Carrot",
}

def calculate_cart(items: list[dict], prices: dict[str, float]) -> dict:
    lines, total = [], 0.0
    catalog_names = {p.name for p in PRODUCTS}
    for item in items:
        raw = str(item.get("product", "")).strip()
        name = ALIASES.get(raw.lower(), raw)
        quantity = float(item.get("quantity", 0))
        if name not in catalog_names or quantity <= 0:
            continue
        price = float(prices.get(name, 0))
        line_total = quantity * price
        lines.append({"product": name, "quantity": quantity, "unit_price": price, "line_total": line_total})
        total += line_total
    return {"items": lines, "total": round(total, 2)}
