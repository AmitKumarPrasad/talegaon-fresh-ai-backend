import os
import unittest
from unittest.mock import MagicMock, patch

from starlette.requests import Request

from app.admin_orders import get_admin_order, list_orders
from app.main import (
    admin_inventory,
    admin_order,
    admin_orders,
    admin_update_inventory,
    admin_update_order_status,
)


def make_request(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"x-admin-token", token.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


class AdminOrderServiceTests(unittest.TestCase):
    @patch("app.admin_orders.SessionLocal")
    def test_list_orders_includes_items_and_allowed_statuses(self, session_local):
        db = session_local.return_value
        order = type(
            "Order",
            (),
            {
                "id": 7,
                "customer_id": "918788543135",
                "status": "CONFIRMED",
                "total": 320.0,
                "address": "Talegaon, Pune 410507",
                "payment_method": "COD",
                "payment_link_url": None,
                "payment_verified_at": None,
            },
        )()
        item = type(
            "Item",
            (),
            {
                "id": 1,
                "order_id": 7,
                "product_name": "Tomato",
                "quantity": 2.0,
                "unit_price": 40.0,
                "line_total": 80.0,
            },
        )()

        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.side_effect = [[order], [item]]
        db.query.return_value = query

        result = list_orders(status="confirmed")
        self.assertEqual(result[0]["order_id"], 7)
        self.assertEqual(result[0]["items"][0]["product"], "Tomato")
        self.assertEqual(result[0]["allowed_next_statuses"], ["CANCELLED", "PACKING"])


class AdminInventoryEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_inventory_requires_token(self):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        response = await admin_inventory(make_request("wrong"))
        self.assertEqual(response.status_code, 401)

    @patch("app.main.list_inventory")
    async def test_admin_inventory_lists_stock(self, list_inventory_mock):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        list_inventory_mock.return_value = [{"id": 1, "stock_quantity": 12, "in_stock": True}]
        response = await admin_inventory(make_request("secret"))
        self.assertEqual(response["products"][0]["stock_quantity"], 12)

    @patch("app.main.update_inventory")
    async def test_admin_inventory_updates_stock(self, update_inventory_mock):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        update_inventory_mock.return_value = {
            "id": 1, "stock_quantity": 25, "in_stock": True
        }
        payload = type("Payload", (), {"stock_quantity": 25})()
        response = await admin_update_inventory(1, payload, make_request("secret"))
        self.assertEqual(response["stock_quantity"], 25)
        update_inventory_mock.assert_called_once_with(1, 25)


class AdminOrderEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_order_requires_token(self):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        response = await admin_order(7, make_request("wrong"))
        self.assertEqual(response.status_code, 401)

    @patch("app.main.get_admin_order")
    async def test_admin_order_returns_order(self, get_order):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        get_order.return_value = {"order_id": 7, "status": "CONFIRMED"}
        response = await admin_order(7, make_request("secret"))
        self.assertEqual(response["order_id"], 7)

    @patch("app.main.list_orders")
    async def test_admin_orders_filters_status(self, list_orders_mock):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        list_orders_mock.return_value = []
        response = await admin_orders(make_request("secret"), status="packing")
        self.assertEqual(response["orders"], [])
        list_orders_mock.assert_called_once_with(status="packing", limit=50, offset=0)

    @patch("app.main.get_admin_order")
    @patch("app.main.transition_order_status")
    async def test_admin_status_transition_returns_updated_order(
        self, transition_mock, get_order
    ):
        os.environ["ADMIN_API_TOKEN"] = "secret"
        get_order.side_effect = [
            {"order_id": 7, "status": "CONFIRMED"},
            {"order_id": 7, "status": "PACKING"},
        ]
        transition_mock.return_value = True

        payload = type("Payload", (), {"status": "packing"})()
        response = await admin_update_order_status(7, payload, make_request("secret"))

        self.assertEqual(response["status"], "PACKING")
        transition_mock.assert_called_once_with(7, "packing")


if __name__ == "__main__":
    unittest.main()
