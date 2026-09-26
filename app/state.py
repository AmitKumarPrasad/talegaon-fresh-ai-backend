from dataclasses import dataclass, field

from app.db import SessionLocal
from app.models import ConversationStateModel


@dataclass
class ConversationState:
    customer_id: str
    step: str = "menu"
    cart: list[dict] = field(default_factory=list)
    pending_order_id: int | None = None
    status_order_lookup: bool = False
    _initialized: bool = field(default=False, repr=False, compare=False)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name != "_initialized" and getattr(self, "_initialized", False):
            self._persist()

    def _persist(self) -> None:
        db = SessionLocal()
        try:
            model = db.get(ConversationStateModel, self.customer_id)
            if not model:
                model = ConversationStateModel(customer_id=self.customer_id)
                db.add(model)
            model.step = self.step
            model.cart = self.cart
            model.pending_order_id = self.pending_order_id
            model.status_order_lookup = self.status_order_lookup
            db.commit()
        finally:
            db.close()


def _load_or_create(customer_id: str) -> ConversationState:
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
        return ConversationState(
            customer_id=customer_id,
            step=model.step,
            cart=model.cart or [],
            pending_order_id=model.pending_order_id,
            status_order_lookup=model.status_order_lookup,
            _initialized=True,
        )
    finally:
        db.close()


def get_state(customer_id: str) -> ConversationState:
    return _load_or_create(customer_id)


def save_state(customer_id: str, state: ConversationState) -> ConversationState:
    state.customer_id = customer_id
    state._initialized = True
    state._persist()
    return state


def reset_state(customer_id: str) -> ConversationState:
    return save_state(
        customer_id,
        ConversationState(customer_id=customer_id),
    )
