"""
Notification service for persistent user notifications.
"""
from typing import List, Dict
from datetime import datetime

from app.models.database import Notification, get_db_session


def add_notification(user_id: str, message: str, type: str = "info") -> None:
    """Persist a notification for a user."""
    if not user_id or not message:
        return
    db = next(get_db_session())
    try:
        db.add(
            Notification(
                user_id=user_id,
                message=message,
                type=(type or "info"),
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()


def pop_notifications(db, user_id: str, limit: int = 20) -> List[Dict[str, str]]:
    """
    Read and clear notifications for a user.
    Keeps API behavior consistent with previous in-memory pop semantics.
    """
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    notifications = [{"message": r.message, "type": r.type} for r in rows]
    for row in rows:
        db.delete(row)
    db.commit()
    return notifications

