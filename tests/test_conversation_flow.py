import unittest
from unittest.mock import patch

from app import main
from app.state import reset_state


class ConversationFlowTests(unittest.TestCase):
    def setUp(self):
        reset_state("919999999999")

    @patch("app.main.send_text_message", return_value={"status": "skipped"})
    @patch("app.main.process_order_message")
    def test_order_to_address_to_cod(self, process_order, _send):
        process_order.return_value = {
            "status": "order_created",
            "order_id": 101,
            "message": "Order created."
        }
        customer = "919999999999"
        self.assertIn("place your order", main.handle_conversation(customer, "1").lower())
        self.assertEqual(main.get_state(customer).step, "products")
        self.assertEqual(main.handle_conversation(customer, "2 kg tomato"), "Order created.")
        self.assertEqual(main.get_state(customer).step, "address")

        with patch("app.main.update_address", return_value=True):
            reply = main.handle_conversation(customer, "12 Main Road, Talegaon, Pune 410507")
        self.assertIn("Choose payment method", reply)
        self.assertEqual(main.get_state(customer).step, "payment")

        with patch("app.main.update_payment", return_value=True), patch(
            "app.main.get_customer_order",
            return_value={"order_id": 101, "total": 299.0, "address": "12 Main Road", "payment_method": "COD"},
        ), patch("app.main.notify_seller", return_value={"status": "sent"}):
            reply = main.handle_conversation(customer, "2")
        self.assertIn("confirmed", reply.lower())
        self.assertEqual(main.get_state(customer).step, "menu")

    @patch("app.main.send_text_message", return_value={"status": "skipped"})
    @patch("app.main.process_order_message")
    def test_cod_confirmation_survives_seller_notification_failure(self, process_order, _send):
        process_order.return_value = {
            "status": "order_created",
            "order_id": 102,
            "message": "Order created."
        }
        customer = "919999999999"
        main.handle_conversation(customer, "1")
        main.handle_conversation(customer, "2 kg tomato")
        with patch("app.main.update_address", return_value=True):
            main.handle_conversation(customer, "12 Main Road, Talegaon, Pune 410507")
        with patch("app.main.update_payment", return_value=True), patch(
            "app.main.get_customer_order",
            return_value={"order_id": 102, "total": 299.0, "address": "12 Main Road", "payment_method": "COD"},
        ), patch(
            "app.main.notify_seller",
            side_effect=RuntimeError("WhatsApp temporarily unavailable"),
        ):
            reply = main.handle_conversation(customer, "2")

        self.assertIn("confirmed", reply.lower())
        self.assertIn("cash on delivery", reply.lower())
        self.assertIn("exact amount", reply.lower())
        self.assertEqual(main.get_state(customer).step, "menu")

    @patch("app.main.get_customer_order")
    def test_order_status_is_customer_scoped(self, get_order):
        customer = "919999999999"
        main.handle_conversation(customer, "3")
        get_order.return_value = None
        reply = main.handle_conversation(customer, "101")
        self.assertIn("not found", reply.lower())


if __name__ == "__main__":
    unittest.main()
