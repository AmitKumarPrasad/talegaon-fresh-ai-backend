import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.delivery_service import DELIVERY_TOKEN_TTL, _token_is_active, assign_delivery_person, get_order_by_delivery_token


class DeliveryTokenSecurityTests(unittest.TestCase):
    def _order(self, expires_at=None):
        return type(
            "Order",
            (),
            {
                "id": 7,
                "delivery_token": None,
                "delivery_token_expires_at": expires_at,
                "delivery_person_name": None,
                "delivery_person_phone": None,
                "delivery_status": "OUT_FOR_DELIVERY",
                "status": "OUT_FOR_DELIVERY",
                "address": "Talegaon",
                "delivery_lat": None,
                "delivery_lng": None,
                "delivery_location_updated_at": None,
            },
        )()

    def test_active_token_requires_future_expiry(self):
        now = datetime.now(timezone.utc)
        order = self._order(now + timedelta(minutes=1))
        self.assertTrue(_token_is_active(order, now))
        order.delivery_token_expires_at = now
        self.assertFalse(_token_is_active(order, now))
        order.delivery_token_expires_at = None
        self.assertFalse(_token_is_active(order, now))

    @patch("app.delivery_service.SessionLocal")
    def test_assignment_creates_24_hour_token(self, session_local):
        db = session_local.return_value
        order = self._order()
        db.get.return_value = order
        before = datetime.now(timezone.utc)

        result = assign_delivery_person(7, "Driver", "919888888888")

        after = datetime.now(timezone.utc)
        self.assertIsNotNone(result["delivery_token"])
        self.assertTrue(len(result["delivery_token"]) >= 32)
        self.assertGreaterEqual(order.delivery_token_expires_at, before + DELIVERY_TOKEN_TTL - timedelta(seconds=1))
        self.assertLessEqual(order.delivery_token_expires_at, after + DELIVERY_TOKEN_TTL + timedelta(seconds=1))

    def test_terminal_status_invalidates_unexpired_token(self):
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        for status in ("CANCELLED", "DELIVERED"):
            order = self._order(expiry)
            order.delivery_token = "still-stored-token"
            order.status = status
            self.assertFalse(_token_is_active(order))

    @patch("app.delivery_service.SessionLocal")
    def test_reassignment_rotates_an_active_delivery_token(self, session_local):
        db = session_local.return_value
        order = self._order(datetime.now(timezone.utc) + timedelta(hours=1))
        order.delivery_token = "old-partner-token"
        order.delivery_person_phone = "919111111111"
        db.get.return_value = order

        result = assign_delivery_person(7, "New Driver", "919222222222")

        self.assertNotEqual(result["delivery_token"], "old-partner-token")
        self.assertEqual(order.delivery_person_phone, "919222222222")
        self.assertEqual(order.delivery_status, "ASSIGNED")

    @patch("app.delivery_service.SessionLocal")
    def test_expired_token_is_rejected(self, session_local):
        db = session_local.return_value
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = self._order(datetime.now(timezone.utc) - timedelta(seconds=1))
        db.query.return_value = query

        self.assertIsNone(get_order_by_delivery_token("expired-token"))


    @patch("app.delivery_service.SessionLocal")
    def test_terminal_order_token_lookup_is_rejected(self, session_local):
        db = session_local.return_value
        query = MagicMock()
        query.filter.return_value = query
        order = self._order(datetime.now(timezone.utc) + timedelta(hours=1))
        order.delivery_token = "terminal-order-token"
        order.status = "CANCELLED"
        query.first.return_value = order
        db.query.return_value = query

        self.assertIsNone(get_order_by_delivery_token("terminal-order-token"))


if __name__ == "__main__":
    unittest.main()
