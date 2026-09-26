import hashlib
import hmac
import os
import unittest
from unittest.mock import Mock, patch

from app.payment_service import create_payment_link, extract_paid_event, verify_webhook_signature


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
        self.assertEqual(event["payment_link_id"], "plink_123")
        self.assertEqual(event["amount"], 29900)

    @patch("app.payment_service.requests.post")
    def test_create_payment_link(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"id": "plink_123", "short_url": "https://rzp.io/i/test"}
        post.return_value = response
        with patch.dict(os.environ, {
            "RAZORPAY_KEY_ID": "rzp_test_key",
            "RAZORPAY_KEY_SECRET": "test_secret",
        }):
            result = create_payment_link(42, 299.0, "919999999999")
        self.assertEqual(result["id"], "plink_123")
        request = post.call_args
        self.assertEqual(request.kwargs["json"]["amount"], 29900)
        self.assertEqual(request.kwargs["json"]["reference_id"], "TF-42")


if __name__ == "__main__":
    unittest.main()
