import unittest
from unittest.mock import patch

from app.order_status import get_allowed_transitions, list_status_history, transition_order


class OrderStatusLifecycleTests(unittest.TestCase):
    def test_allowed_transitions(self):
        self.assertEqual(get_allowed_transitions("PENDING"), {"ADDRESS_CONFIRMED", "CANCELLED"})
        self.assertEqual(get_allowed_transitions("CONFIRMED"), {"PACKING", "CANCELLED"})
        self.assertEqual(get_allowed_transitions("PACKING"), {"OUT_FOR_DELIVERY"})
        self.assertEqual(get_allowed_transitions("OUT_FOR_DELIVERY"), {"DELIVERED"})
        self.assertEqual(get_allowed_transitions("DELIVERED"), set())

    @patch("app.order_status.SessionLocal")
    def test_cancel_restores_reserved_stock_once(self, session_local):
        db = session_local.return_value
        order = type("Order", (), {"id": 101, "status": "CONFIRMED", "stock_reserved": True, "customer_id": "customer-1"})()
        item = type("Item", (), {"product_name": "Tomato", "quantity": 2})()
        product = type("Product", (), {"stock_quantity": 5, "in_stock": True})()
        db.get.return_value = order
        query = db.query.return_value
        query.filter.return_value = query
        query.all.return_value = [item]
        query.first.return_value = product
        query.update.return_value = 1
        self.assertTrue(transition_order(101, "CANCELLED"))
        self.assertEqual(order.status, "CANCELLED")
        self.assertFalse(order.stock_reserved)
        query.update.assert_called_once()
        db.commit.assert_called_once()

        db.reset_mock()
        db.get.return_value = order
        self.assertFalse(transition_order(101, "CANCELLED"))
        db.commit.assert_not_called()


    @patch("app.order_status.SessionLocal")
    def test_valid_transition(self, session_local):
        db = session_local.return_value
        order = type("Order", (), {"id": 101, "status": "CONFIRMED", "stock_reserved": False, "customer_id": "customer-1"})()
        db.get.return_value = order
        self.assertTrue(transition_order(101, "PACKING"))
        self.assertEqual(order.status, "PACKING")
        db.commit.assert_called_once()
        db.add.assert_called_once()


    @patch("app.order_status.NotificationService.notify_customer_order_status")
    @patch("app.order_status.SessionLocal")
    def test_committed_status_change_sends_customer_push(self, session_local, notify):
        from app.models import CustomerModel, OrderModel

        db = session_local.return_value
        order = type("Order", (), {"id": 101, "customer_id": "customer-1", "status": "CONFIRMED", "stock_reserved": False})()
        customer = type("Customer", (), {"fcm_token": "device-token"})()
        db.get.side_effect = lambda model, key: order if model is OrderModel else customer if model is CustomerModel else None
        self.assertTrue(transition_order(101, "PACKING"))
        db.commit.assert_called_once()
        notify.assert_called_once_with("device-token", 101, "PACKING")

    @patch("app.order_status.SessionLocal")
    def test_status_history_is_read(self, session_local):
        db = session_local.return_value
        query = db.query.return_value
        query.filter.return_value = query
        query.join.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [type("History", (), {"id": 1, "from_status": "CONFIRMED", "to_status": "PACKING", "created_at": None})()]
        self.assertEqual(list_status_history(101), [{"id": 1, "from_status": "CONFIRMED", "to_status": "PACKING", "created_at": None}])
        self.assertEqual(list_status_history(101, "customer-1"), [{"id": 1, "from_status": "CONFIRMED", "to_status": "PACKING", "created_at": None}])

    @patch("app.order_status.SessionLocal")
    def test_transition_runs_order_update_and_records_history(self, session_local):
        db = session_local.return_value
        order = type("Order", (), {"id": 101, "status": "PENDING", "stock_reserved": False, "customer_id": "customer-1"})()
        db.get.return_value = order
        self.assertTrue(transition_order(101, "ADDRESS_CONFIRMED", lambda value: setattr(value, "address", "Talegaon")))
        self.assertEqual(order.address, "Talegaon")
        self.assertEqual(order.status, "ADDRESS_CONFIRMED")
        db.add.assert_called_once()

    @patch("app.order_status.SessionLocal")
    def test_invalid_transition_is_rejected(self, session_local):
        db = session_local.return_value
        order = type("Order", (), {"status": "PENDING"})()
        db.get.return_value = order
        self.assertFalse(transition_order(101, "DELIVERED"))
        self.assertEqual(order.status, "PENDING")
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
