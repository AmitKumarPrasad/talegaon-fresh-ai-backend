from dataclasses import dataclass, field


@dataclass
class ConversationState:
    step: str = "menu"
    cart: list[dict] = field(default_factory=list)
    pending_order_id: int | None = None
    status_order_lookup: bool = False


_SESSIONS: dict[str, ConversationState] = {}


def get_state(customer_id: str) -> ConversationState:
    return _SESSIONS.setdefault(customer_id, ConversationState())


def reset_state(customer_id: str) -> ConversationState:
    state = ConversationState()
    _SESSIONS[customer_id] = state
    return state
