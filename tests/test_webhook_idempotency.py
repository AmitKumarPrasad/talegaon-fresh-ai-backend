import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import webhook_idempotency


class WebhookIdempotencyTests(unittest.TestCase):
    @patch("app.webhook_idempotency.SessionLocal")
    def test_claim_event_first_time(self, session_local):
        db = session_local.return_value
        self.assertTrue(webhook_idempotency.claim_event("whatsapp", "wamid.123"))
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.rollback.assert_not_called()
        event = db.add.call_args.args[0]
        self.assertEqual(event.provider, "whatsapp")
        self.assertEqual(event.event_id, "wamid.123")
        self.assertIsInstance(event.processed_at, datetime)
        self.assertIsNotNone(event.processed_at.tzinfo)

    @patch("app.webhook_idempotency.SessionLocal")
    def test_duplicate_event_returns_false(self, session_local):
        from sqlalchemy.exc import IntegrityError

        db = session_local.return_value
        db.commit.side_effect = IntegrityError("duplicate", None, None)
        self.assertFalse(webhook_idempotency.claim_event("razorpay", "evt_123"))
        db.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
