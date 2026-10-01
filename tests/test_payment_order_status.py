import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.order_details import confirm_upi_payment, get_order


class PaymentOrderStatusTests(unittest.TestCase):
    def _order(self):
        return SimpleNamespace(
            id=1,
            customer_id="919999999999",
            status="PAYMENT_PENDING",
            total=565.0,
            address="Siddhivinayak housing society, PIN code 411044",
            payment_method="UPI",
            payment_link_url="https://rzp.io/i/test",
            razorpay_payment_link_id="plink_test_1",
            razorpay_payment_id=None,
            razorpay_event_id=None,
            payment_verified_at=None,
        )

    @patch("app.order_details.SessionLocal")
    def test_get_order_exposes_payment_link_id_for_webhook_validation(self, session_local):
        db = session_local.return_value
        db.get.return_value = self._order()

        order = get_order(1)

        self.assertEqual(order["razorpay_payment_link_id"], "plink_test_1")
        self.assertIsNone(order["razorpay_payment_id"])
        self.assertIsNone(order["payment_verified_at"])

    @patch("app.order_details.SessionLocal")
    def test_confirmed_payment_changes_order_status_to_confirmed(self, session_local):
        db = session_local.return_value
        order = self._order()
        db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = order

        confirmed = confirm_upi_payment(
            order_id=1,
            payment_link_id="plink_test_1",
            payment_id="pay_test_1",
            event_id="payment_link.paid:pay_test_1",
            amount_paise=56500,
        )

        self.assertTrue(confirmed)
        self.assertEqual(order.status, "CONFIRMED")
        self.assertEqual(order.razorpay_payment_id, "pay_test_1")
        self.assertEqual(order.razorpay_event_id, "payment_link.paid:pay_test_1")
        self.assertIsNotNone(order.payment_verified_at)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
