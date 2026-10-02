import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.main import razorpay_webhook


@pytest.mark.asyncio
async def test_confirmed_payment_notifies_once_and_replay_does_not_notify():
    payload = {
        "event": "payment_link.paid", "id": "evt_42",
        "payload": {
            "payment_link": {"entity": {"id": "plink_42", "reference_id": "TF-42"}},
            "payment": {"entity": {"id": "pay_42", "amount": 29900, "status": "captured"}},
        },
    }
    request = Mock(headers={"X-Razorpay-Signature": "test-signature"})
    request.body = AsyncMock(return_value=json.dumps(payload).encode())
    order = {"customer_id": "9876543210", "total": 299, "address": "Talegaon",
             "payment_method": "UPI", "razorpay_payment_link_id": "plink_42"}
    with (patch("app.main.verify_webhook_signature", return_value=True),
          patch("app.main._order_for_payment", return_value=order),
          patch("app.main.confirm_upi_payment", side_effect=[True, False]),
          patch("app.main.claim_event") as claim,
          patch("app.main.notify_seller") as seller,
          patch("app.main.send_text_message") as customer):
        assert await razorpay_webhook(request) == {"status": "processed"}
        assert await razorpay_webhook(request) == {"status": "processed"}
    seller.assert_called_once_with(42, "9876543210", 299, "Talegaon", "UPI")
    customer.assert_called_once()
    claim.assert_called_once_with("razorpay", "evt_42")
