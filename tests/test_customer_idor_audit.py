import unittest
from unittest.mock import MagicMock, patch

from app.customer_api import (
    delete_address,
    get_customer_order_details,
    get_order_tracking,
    list_order_messages,
    send_order_message,
    update_address_api,
)
from app.delivery_service import (
    add_message_by_customer,
    get_tracking_info,
    list_messages_for_customer,
)
from app.models import CustomerModel


class CustomerIdorAuditTests(unittest.TestCase):
    def _customer(self, phone):
        return CustomerModel(phone=phone, name="Customer")

    def test_order_details_uses_authenticated_customer_scope(self):
        owner = self._customer("919999999999")
        with patch("app.customer_api.get_customer_order", return_value=None) as lookup:
            with self.assertRaises(Exception) as ctx:
                get_customer_order_details(42, owner)
        self.assertEqual(ctx.exception.status_code, 404)
        lookup.assert_called_once_with(42, owner.phone)

    def test_order_tracking_uses_authenticated_customer_scope(self):
        owner = self._customer("919999999999")
        with patch("app.customer_api.get_tracking_info", return_value=None) as lookup:
            with self.assertRaises(Exception) as ctx:
                get_order_tracking(42, owner)
        self.assertEqual(ctx.exception.status_code, 404)
        lookup.assert_called_once_with(42, owner.phone)

    def test_order_messages_read_uses_authenticated_customer_scope(self):
        owner = self._customer("919999999999")
        with patch("app.customer_api.list_messages_for_customer", return_value=None) as lookup:
            with self.assertRaises(Exception) as ctx:
                list_order_messages(42, owner)
        self.assertEqual(ctx.exception.status_code, 404)
        lookup.assert_called_once_with(42, owner.phone)

    def test_order_messages_write_uses_authenticated_customer_scope(self):
        owner = self._customer("919999999999")
        payload = type("Payload", (), {"message": "hello"})()
        with patch("app.customer_api.add_message_by_customer", return_value=None) as lookup:
            with self.assertRaises(Exception) as ctx:
                send_order_message(42, payload, owner)
        self.assertEqual(ctx.exception.status_code, 404)
        lookup.assert_called_once_with(42, owner.phone, "hello")

    def test_address_update_and_delete_require_owner(self):
        owner = self._customer("919999999999")
        payload = type("Payload", (), {
            "is_default": False,
            "model_dump": lambda self: {
                "label": "Home", "address": "Main Road", "city": "Talegaon",
                "pincode": "410507", "is_default": False,
            },
        })()
        db = MagicMock()
        row = MagicMock(customer_id="918888888888")
        db.get.return_value = row
        with patch("app.customer_api.SessionLocal", return_value=db):
            with self.assertRaises(Exception) as update_ctx:
                update_address_api(7, payload, owner)
            with self.assertRaises(Exception) as delete_ctx:
                delete_address(7, owner)
        self.assertEqual(update_ctx.exception.status_code, 404)
        self.assertEqual(delete_ctx.exception.status_code, 404)
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    def test_service_level_order_scope_rejects_other_customer(self):
        with patch("app.delivery_service.SessionLocal") as session_local:
            db = session_local.return_value
            order = MagicMock(customer_id="918888888888")
            db.get.return_value = order
            self.assertIsNone(get_tracking_info(42, "919999999999"))
            self.assertIsNone(list_messages_for_customer(42, "919999999999"))
        
    def test_service_level_message_write_rejects_other_customer(self):
        with patch("app.delivery_service.SessionLocal") as session_local:
            db = session_local.return_value
            db.get.return_value = MagicMock(customer_id="918888888888")
            self.assertIsNone(add_message_by_customer(42, "919999999999", "hello"))


if __name__ == "__main__":
    unittest.main()
