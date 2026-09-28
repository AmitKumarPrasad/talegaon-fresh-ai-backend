from app.order_details import get_customer_order, update_address, update_payment, save_payment_link
from app.order_repository import create_order
from app.order_service import lookup_prices, validate_cart
from app.payment_service import PaymentError, create_payment_link


class CustomerOrderError(ValueError):
    pass


def create_customer_order(
    customer_id: str,
    items: list[dict],
    address: str,
    payment_method: str,
) -> dict:
    if not customer_id.strip():
        raise CustomerOrderError("Customer ID is required.")
    if len(address.strip()) < 10:
        raise CustomerOrderError("Please provide a complete delivery address.")
    method = payment_method.strip().upper()
    if method not in {"UPI", "COD"}:
        raise CustomerOrderError("Payment method must be UPI or COD.")

    cart = validate_cart(items, lookup_prices())
    if not cart["items"]:
        raise CustomerOrderError("No valid in-stock products were found in the order.")
    if not cart["eligible"]:
        raise CustomerOrderError(cart["message"])

    order_id = create_order(customer_id.strip(), cart)
    if not update_address(order_id, address):
        raise CustomerOrderError("Unable to save delivery address.")

    if not update_payment(order_id, method):
        raise CustomerOrderError("Unable to save payment method.")

    payment_url = None
    if method == "UPI":
        try:
            link = create_payment_link(order_id, cart["total"], customer_id.strip())
            save_payment_link(order_id, link["id"], link["short_url"])
            payment_url = link["short_url"]
        except PaymentError:
            payment_url = None

    order = get_customer_order(order_id, customer_id.strip())
    if not order:
        raise CustomerOrderError("Order could not be loaded after creation.")

    return {
        "order": order,
        "items": cart["items"],
        "payment_url": payment_url,
    }
