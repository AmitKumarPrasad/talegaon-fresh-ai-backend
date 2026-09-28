import unittest

from app.payment_service import extract_paid_event


class RazorpayWebhookEventTests(unittest.TestCase):
    def test_payment_link_paid_uses_payment_id_when_top_level_event_id_missing(self):
        payload = {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {"entity": {"id": "plink_test_123", "reference_id": "TF-101"}},
                "payment": {"entity": {"id": "pay_test_123", "amount": 56500, "status": "captured"}},
            },
        }
        event = extract_paid_event(payload)
        self.assertEqual(event["event_id"], "payment_link.paid:pay_test_123")

    def test_top_level_event_id_is_preferred(self):
        payload = {
            "id": "evt_test_123",
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {"entity": {"id": "plink_test_123", "reference_id": "TF-101"}},
                "payment": {"entity": {"id": "pay_test_123", "amount": 56500, "status": "captured"}},
            },
        }
        event = extract_paid_event(payload)
        self.assertEqual(event["event_id"], "evt_test_123")


if __name__ == "__main__":
    unittest.main()
