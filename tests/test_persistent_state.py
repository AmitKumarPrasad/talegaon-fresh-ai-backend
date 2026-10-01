import unittest
from unittest.mock import patch

from app.state import ConversationState, get_state, reset_state, save_state


class PersistentConversationStateTests(unittest.TestCase):
    @patch("app.state.SessionLocal")
    def test_get_state_creates_missing_customer(self, session_local):
        db = session_local.return_value
        db.get.return_value = None
        state = get_state("919999999999")
        self.assertEqual(state.step, "menu")
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @patch("app.state.SessionLocal")
    def test_save_state_persists_fields(self, session_local):
        db = session_local.return_value
        db.get.return_value = None
        state = ConversationState(
            customer_id="919999999999",
            step="address",
            cart=[{"product": "Tomato", "quantity": 2}],
            pending_order_id=101,
            status_order_lookup=False,
        )
        saved = save_state("919999999999", state)
        model = db.add.call_args.args[0]
        self.assertEqual(saved.step, "address")
        self.assertEqual(model.pending_order_id, 101)
        self.assertEqual(model.cart[0]["product"], "Tomato")

    @patch("app.state.SessionLocal")
    def test_reset_state_clears_conversation(self, session_local):
        db = session_local.return_value
        db.get.return_value = None
        state = reset_state("919999999999")
        model = db.add.call_args.args[0]
        self.assertEqual(state.step, "menu")
        self.assertIsNone(model.pending_order_id)
        self.assertFalse(model.status_order_lookup)


if __name__ == "__main__":
    unittest.main()
