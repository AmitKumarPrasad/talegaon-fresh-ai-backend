from unittest.mock import patch

from app.customer_api import create_customer_payment_link, get_customer_order_details
from app.delivery_service import _order_dict


def test_customer_order_view_does_not_expose_internal_customer_or_payment_ids():
    internal = {
        "order_id": 42,
        "customer_id": "919999999999",
        "status": "PAYMENT_PENDING",
        "total": 120.0,
        "address": "Talegaon",
        "payment_method": "UPI",
        "payment_link_url": "https://rzp.io/i/example",
        "razorpay_payment_link_id": "plink_secret",
        "razorpay_payment_id": "pay_secret",
        "payment_verified_at": None,
    }
    with patch("app.customer_api.get_customer_order", return_value={
        "order_id": internal["order_id"],
        "status": internal["status"],
        "total": internal["total"],
        "address": internal["address"],
        "payment_method": internal["payment_method"],
        "payment_link_url": internal["payment_link_url"],
        "payment_verified_at": internal["payment_verified_at"],
    }):
        customer = type("Customer", (), {"phone": internal["customer_id"]})()
        response = get_customer_order_details(42, customer)

    assert response["order_id"] == 42
    assert response["payment_link_url"] == internal["payment_link_url"]
    assert "customer_id" not in response
    assert "razorpay_payment_link_id" not in response
    assert "razorpay_payment_id" not in response


def test_customer_payment_link_response_does_not_expose_provider_id():
    order = {
        "order_id": 42,
        "status": "PAYMENT_PENDING",
        "total": 120.0,
        "address": "Talegaon",
        "payment_method": "UPI",
        "payment_link_url": "https://rzp.io/i/example",
        "razorpay_payment_link_id": "plink_secret",
        "payment_verified_at": None,
    }
    customer = type("Customer", (), {"phone": "919999999999"})()
    with patch("app.customer_api.get_customer_order", return_value=order):
        response = create_customer_payment_link(42, customer)

    assert response["payment_link_url"] == order["payment_link_url"]
    assert "razorpay_payment_link_id" not in response


def test_customer_tracking_does_not_expose_delivery_phone():
    order = type(
        "Order",
        (),
        {
            "id": 42,
            "status": "OUT_FOR_DELIVERY",
            "address": "Talegaon",
            "delivery_person_name": "Driver",
            "delivery_person_phone": "919888888888",
            "delivery_lat": 18.7,
            "delivery_lng": 73.6,
            "delivery_location_updated_at": None,
        },
    )()
    response = _order_dict(order)
    assert response["delivery_person_name"] == "Driver"
    assert "delivery_person_phone" not in response
