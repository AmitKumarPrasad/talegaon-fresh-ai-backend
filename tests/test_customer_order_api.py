from app import customer_orders


def test_create_customer_order_cod(monkeypatch):
    monkeypatch.setattr(customer_orders, "lookup_prices", lambda: {"Tomato": 120.0})
    monkeypatch.setattr(customer_orders, "create_order", lambda customer_id, cart: 42)
    monkeypatch.setattr(customer_orders, "update_address", lambda order_id, address: True)
    monkeypatch.setattr(customer_orders, "update_payment", lambda order_id, method: True)
    monkeypatch.setattr(
        customer_orders,
        "get_customer_order",
        lambda order_id, customer_id: {
            "order_id": 42,
            "customer_id": customer_id,
            "status": "CONFIRMED",
            "total": 240.0,
            "address": "Talegaon station road 410507",
            "payment_method": "COD",
            "payment_link_url": None,
        },
    )

    result = customer_orders.create_customer_order(
        "919999999999",
        [{"product": "Tomato", "quantity": 2}],
        "Talegaon station road 410507",
        "COD",
    )

    assert result["order"]["order_id"] == 42
    assert result["order"]["payment_method"] == "COD"
    assert result["payment_url"] is None
    assert result["items"][0]["product"] == "Tomato"


def test_create_customer_order_upi_returns_payment_link(monkeypatch):
    monkeypatch.setattr(customer_orders, "lookup_prices", lambda: {"Tomato": 120.0})
    monkeypatch.setattr(customer_orders, "create_order", lambda customer_id, cart: 43)
    monkeypatch.setattr(customer_orders, "update_address", lambda order_id, address: True)
    monkeypatch.setattr(customer_orders, "update_payment", lambda order_id, method: True)
    monkeypatch.setattr(
        customer_orders,
        "create_payment_link",
        lambda order_id, amount, customer_id: {
            "id": "plink_43",
            "short_url": "https://rzp.io/i/test43",
        },
    )
    monkeypatch.setattr(customer_orders, "save_payment_link", lambda *args: True)
    monkeypatch.setattr(
        customer_orders,
        "get_customer_order",
        lambda order_id, customer_id: {
            "order_id": 43,
            "customer_id": customer_id,
            "status": "PAYMENT_PENDING",
            "total": 240.0,
            "address": "Talegaon station road 410507",
            "payment_method": "UPI",
            "payment_link_url": "https://rzp.io/i/test43",
        },
    )

    result = customer_orders.create_customer_order(
        "919999999999",
        [{"product": "Tomato", "quantity": 2}],
        "Talegaon station road 410507",
        "UPI",
    )

    assert result["order"]["order_id"] == 43
    assert result["order"]["status"] == "PAYMENT_PENDING"
    assert result["payment_url"] == "https://rzp.io/i/test43"


def test_create_customer_order_rejects_below_minimum(monkeypatch):
    monkeypatch.setattr(customer_orders, "lookup_prices", lambda: {"Tomato": 120.0})

    try:
        customer_orders.create_customer_order(
            "919999999999",
            [{"product": "Tomato", "quantity": 1}],
            "Talegaon station road 410507",
            "COD",
        )
    except customer_orders.CustomerOrderError as exc:
        assert "Minimum order value" in str(exc)
    else:
        raise AssertionError("Expected minimum-order validation to fail")
