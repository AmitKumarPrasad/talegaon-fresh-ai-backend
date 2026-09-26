from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import ProcessedWebhookModel


def claim_event(provider: str, event_id: str | None) -> bool:
    """Atomically claim an event. False means it was already processed/claimed."""
    if not event_id:
        return False

    db = SessionLocal()
    try:
        db.add(
            ProcessedWebhookModel(
                provider=provider,
                event_id=event_id,
                processed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    finally:
        db.close()
