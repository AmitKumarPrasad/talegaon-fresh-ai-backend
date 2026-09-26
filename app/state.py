from dataclasses import dataclass

from app.db import SessionLocal
from app.models import ConversationStateModel


@dataclass
class ConversationState:
    step: str = "menu"
    cart: list[dict] | None = None
    pending_order_id: int | None = None
    status_order_lookup: bool = False


def _to_state(model: ConversationStateModel) -> ConversationState:
    return ConversationState(
        step=model.step,
        cart=model.cart or [],
        pending_order_id=model.pending_order_id,
        status_order_lookup=model.status_order_lookup,
    )


def get_state(customer_id: str) -> ConversationState:
    db = SessionLocal()
    try:
        model = db.get(ConversationStateModel, customer_id)
        if not model:
            model = ConversationStateModel(
                customer_id=customer_id,
                step="menu",
                cart=[],
                pending_order_id=None,
                status_order_lookup=False,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
        return _to_state(model)
    finally:
        db.close()


def save_state(customer_id: str, state: ConversationState) -> ConversationState:
    db = SessionLocal()
    try:
        model = db.get(ConversationStateModel, customer_id)
        if not model:
            model = ConversationStateModel(customer_id=customer_id)
            db.add(model)
        model.step = state.step
        model.cart = state.cart or []
        model.pending_order_id = state.pending_order_id
        model.status_order_lookup = state.status_order_lookup
        db.commit()
        db.refresh(model)
        return _to_state(model)
    finally:
        db.close()


def reset_state(customer_id: str) -> ConversationState:
    state = ConversationState()
    return save_state(customer_id, state)
