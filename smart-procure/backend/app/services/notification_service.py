"""
Notification service for persistent user notifications.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.datetime_utils import utc_now
from ..models.database import Notification, get_db_session

STATUS_UNREAD = "unread"
STATUS_READ = "read"
STATUS_ARCHIVED = "archived"
VALID_STATUSES = {STATUS_UNREAD, STATUS_READ, STATUS_ARCHIVED}

_notification_queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
_queue_lock = asyncio.Lock()


def _to_iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def serialize_notification(notification: Notification) -> Dict[str, Any]:
    return {
        "id": notification.id,
        "message": notification.message,
        "type": notification.type,
        "status": notification.status or STATUS_UNREAD,
        "created_at": _to_iso(notification.created_at),
        "read_at": _to_iso(notification.read_at),
        "archived_at": _to_iso(notification.archived_at),
    }


async def subscribe_notification_stream(user_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _queue_lock:
        _notification_queues[user_id].add(queue)
    return queue


async def unsubscribe_notification_stream(user_id: str, queue: asyncio.Queue) -> None:
    async with _queue_lock:
        queues = _notification_queues.get(user_id)
        if not queues:
            return
        queues.discard(queue)
        if not queues:
            _notification_queues.pop(user_id, None)


async def _publish_notification(user_id: str, payload: Dict[str, Any]) -> None:
    async with _queue_lock:
        queues = list(_notification_queues.get(user_id, set()))

    for queue in queues:
        if queue.full():
            try:
                queue.get_nowait()
            except Exception:
                pass
        try:
            queue.put_nowait(payload)
        except Exception:
            continue


def _publish_notification_sync(user_id: str, payload: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_publish_notification(user_id, payload))


def add_notification(user_id: str, message: str, type: str = "info") -> Optional[Dict[str, Any]]:
    """Persist a notification for a user and push it to live streams."""
    if not user_id or not message:
        return None

    db = next(get_db_session())
    try:
        notification = Notification(
            user_id=user_id,
            message=message,
            type=(type or "info"),
            status=STATUS_UNREAD,
            created_at=utc_now(),
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        payload = serialize_notification(notification)
    finally:
        db.close()

    _publish_notification_sync(user_id, payload)
    return payload


def list_notifications(
    db: Session,
    user_id: str,
    status: Optional[str] = STATUS_UNREAD,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if isinstance(status, str) and status in VALID_STATUSES:
        query = query.filter(Notification.status == status)
    elif status == "all":
        pass
    else:
        query = query.filter(Notification.status != STATUS_ARCHIVED)

    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [serialize_notification(row) for row in rows]


def mark_notification_read(
    db: Session,
    user_id: str,
    notification_id: int,
) -> Optional[Dict[str, Any]]:
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if row is None:
        return None
    if row.status != STATUS_ARCHIVED:
        row.status = STATUS_READ
        if row.read_at is None:
            row.read_at = utc_now()
    db.commit()
    db.refresh(row)
    return serialize_notification(row)


def mark_all_notifications_read(db: Session, user_id: str) -> int:
    rows = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.status == STATUS_UNREAD,
        )
        .all()
    )
    if not rows:
        return 0
    now = utc_now()
    for row in rows:
        row.status = STATUS_READ
        if row.read_at is None:
            row.read_at = now
    db.commit()
    return len(rows)


def archive_notification(
    db: Session,
    user_id: str,
    notification_id: int,
) -> Optional[Dict[str, Any]]:
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if row is None:
        return None
    row.status = STATUS_ARCHIVED
    row.archived_at = utc_now()
    if row.read_at is None:
        row.read_at = row.archived_at
    db.commit()
    db.refresh(row)
    return serialize_notification(row)


def pop_notifications(db: Session, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Compatibility helper for legacy callers.
    Returns unread notifications and marks them as read.
    """
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.status == STATUS_UNREAD)
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    now = utc_now()
    out = []
    for row in rows:
        row.status = STATUS_READ
        if row.read_at is None:
            row.read_at = now
        out.append(serialize_notification(row))
    db.commit()
    return out
