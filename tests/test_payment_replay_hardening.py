import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.order_details import confirm_upi_payment


class PaymentReplayHardeningTests(unittest.TestCase):
    def _order(self, **overrides):
        values = {
            "id": 42,
            "payment_method": "UPI",
            "total": 299.0,
            "razorpay_payment_link_id": "plink_42",
            "razorpay_payment_id": None,
            "razorpay_event_id": None,
            "payment_verified_at": None,
            "status": "PAYMENT_PENDING",
        }
        values.update(overrides)
        return type("Order", (), values)()

    @patch("app.order_details.SessionLocal")
    def test_already_confirmed_order_rejects_different_replay(self, session_local):
        db = session_local.return_value
        order = self._order(
            status="CONFIRMED",
            razorpay_payment_id="pay_original",
        )
        query = db.query.return_value
        query.filter.return_value = query
        query.with_for_update.return_value = query
        query.first.return_value = order

        result = confirm_upi_payment(42, "plink_42", "pay_replay", "evt_replay", 29900)

        self.assertFalse(result)
        db.commit.assert_not_called()

    @patch("app.order_details.SessionLocal")
    def test_valid_payment_is_committed_once(self, session_local):
        db = session_local.return_value
        order = self._order()
        query = db.query.return_value
        query.filter.return_value = query
        query.with_for_update.return_value = query
        query.first.return_value = order

        result = confirm_upi_payment(42, "plink_42", "pay_42", "evt_42", 29900)

        self.assertTrue(result)
        self.assertEqual(order.razorpay_payment_id, "pay_42")
        self.assertEqual(order.razorpay_event_id, "evt_42")
        self.assertEqual(order.status, "CONFIRMED")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
