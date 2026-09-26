import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

from app import main
from app.payment_service import extract_paid_event, verify_webhook_signature
from app.state import reset_state


class PaymentIntegrationTests(unittest.TestCase):
    def test_webhook_signature(self):
        secret = "test-secret"
        body = b'{"event":"payment_link.paid"}'
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": secret}):
            signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            self.assertTrue(verify_webhook_signature(body, signature))
            self.assertFalse(verify_webhook_signature(body, "bad"))

    def test_extract_paid_event(self):
        payload = {
            "event": "payment_link.paid",
            "id": "evt_123",
            "payload": {
                "payment_link": {"entity": {"id": "plink_123", "reference_id": "TF-42"}},
                "payment": {"entity": {"id": "pay_123", "amount": 29900, "status": "captured"}},
            },
        }
        event = extract_paid_event(payload)
        self.assertEqual(event["reference_id"], "TF-42")
        self.assertEqual(event["amount"], 29900)

    @patch("app.main.send_text_message")
    @patch("app.main.notify_seller")
    @patch("app.main.confirm_upi_payment", return_value=True)
    @patch("app.main.get_customer_order", return_value={
        "order_id": 42,
        "customer_id": "919999999999",
        "total": 299.0,
        "address": "Talegaon",
        "payment_method": "UPI",
    })
    def test_razorpay_webhook_confirms_order(self, get_order, confirm, notify, send):
        body = json.dumps({
            "event": "payment_link.paid",
            "id": "evt_123",
            "payload": {
                "payment_link": {"entity": {"id": "plink_123", "reference_id": "TF-42"}},
                "payment": {"entity": {"id": "pay_123", "amount": 29900, "status": "captured"}},
            },
        }).encode()
        secret = "test-secret"
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"RAZORPAY_WEBHOOK_SECRET": secret}):
            response = main.razorpay_webhook
            self.assertIsNotNone(response)
            self.assertTrue(confirm.called)
            self.assertTrue(notify.called)
            self.assertTrue(send.called)


if __name__ == "__main__":
    unittest.main()
