import asyncio
import json
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth.utils import decode_token, get_current_user
from ..models.database import User, get_db
from ..services.notification_service import (
    archive_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    subscribe_notification_stream,
    unsubscribe_notification_stream,
)

router = APIRouter()

# 短时票据存储: {ticket: (user_id, expire_time)}
_stream_tickets: dict[str, tuple[str, float]] = {}
_TICKET_TTL = 30  # 票据有效期30秒


def _cleanup_expired_tickets():
    """清理过期票据"""
    now = time.time()
    expired = [k for k, v in _stream_tickets.items() if v[1] < now]
    for k in expired:
        _stream_tickets.pop(k, None)


def _create_stream_ticket(user_id: str) -> str:
    """创建短时票据"""
    _cleanup_expired_tickets()
    ticket = secrets.token_urlsafe(24)
    _stream_tickets[ticket] = (user_id, time.time() + _TICKET_TTL)
    return ticket


def _consume_stream_ticket(ticket: str) -> str:
    """消费票据，返回 user_id，票据一次性使用"""
    _cleanup_expired_tickets()
    entry = _stream_tickets.pop(ticket, None)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid or expired ticket")
    return entry[0]


@router.get("/notifications")
async def get_notifications(
    status_filter: str = Query(default="unread", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get notifications for current user without deleting them."""
    notifications = list_notifications(db, current_user.id, status=status_filter, limit=limit)
    unread_count = len([n for n in notifications if n.get("status") == "unread"])
    return {"notifications": notifications, "unread_count": unread_count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = mark_notification_read(db, current_user.id, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"notification": notification}


@router.post("/notifications/read-all")
async def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    changed = mark_all_notifications_read(db, current_user.id)
    return {"updated": changed}


@router.post("/notifications/{notification_id}/archive")
async def archive_notification_endpoint(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = archive_notification(db, current_user.id, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"notification": notification}


@router.post("/notifications/stream-ticket")
async def create_stream_ticket(current_user: User = Depends(get_current_user)):
    """生成 SSE 连接用的短时票据"""
    ticket = _create_stream_ticket(current_user.id)
    return {"ticket": ticket}


def _verify_stream_token(token: str) -> str:
    payload = decode_token(token)
    user_id = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid stream token",
        )
    return user_id


@router.get("/notifications/stream")
async def stream_notifications(ticket: str = Query(..., min_length=10)):
    """
    SSE stream for push notifications.
    Use POST /notifications/stream-ticket to get a short-lived ticket first.
    """
    user_id = _consume_stream_ticket(ticket)

    async def event_generator():
        queue = await subscribe_notification_stream(user_id)
        try:
            ready_payload = json.dumps({"status": "connected"}, ensure_ascii=False)
            yield f"event: ready\ndata: {ready_payload}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    data = json.dumps(payload, ensure_ascii=False)
                    yield f"event: notification\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await unsubscribe_notification_stream(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
