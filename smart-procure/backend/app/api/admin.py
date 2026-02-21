import asyncio
import json
import logging
import secrets
import time
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.database import get_db, User, InquirySheet
from ..auth.utils import decode_token, is_admin_user, require_admin_user, get_password_hash
from ..core.llm import get_llm_gateway_stats
from ..services.agent_runtime import get_tool_runtime_stats
from ..services.admin_progress_service import get_overview_daily_progress, get_user_daily_progress
from ..services.admin_progress_stream import (
    subscribe_admin_progress_stream,
    unsubscribe_admin_progress_stream,
)

router = APIRouter()

logger = logging.getLogger(__name__)

# Admin SSE 票据存储
_admin_stream_tickets: dict[str, tuple[str, float]] = {}
_ADMIN_TICKET_TTL = 30


def _create_admin_stream_ticket(user_id: str) -> str:
    now = time.time()
    expired = [k for k, v in _admin_stream_tickets.items() if v[1] < now]
    for k in expired:
        _admin_stream_tickets.pop(k, None)
    ticket = secrets.token_urlsafe(24)
    _admin_stream_tickets[ticket] = (user_id, now + _ADMIN_TICKET_TTL)
    return ticket


def _consume_admin_stream_ticket(ticket: str) -> str:
    now = time.time()
    expired = [k for k, v in _admin_stream_tickets.items() if v[1] < now]
    for k in expired:
        _admin_stream_tickets.pop(k, None)
    entry = _admin_stream_tickets.pop(ticket, None)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid or expired ticket")
    return entry[0]


@router.post("/admin/embeddings/rebuild")
async def rebuild_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Rebuild all embedding indexes (admin only)."""
    try:
        from ..services.embedding_index_service import EmbeddingIndexService

        service = EmbeddingIndexService(db)
        stats = service.rebuild_all_indexes()
        return {"status": "completed", "stats": stats}
    except Exception as e:
        logger.exception("Failed to rebuild embeddings")
        raise HTTPException(status_code=500, detail="Failed to rebuild embeddings")


@router.get("/admin/embeddings/stats")
async def get_embedding_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """Get embedding index stats (admin only)."""
    try:
        from ..services.embedding_index_service import EmbeddingIndexService

        service = EmbeddingIndexService(db)
        stats = service.get_index_stats()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("Failed to get stats")
        raise HTTPException(status_code=500, detail="Failed to get stats")


@router.get("/admin/runtime/stats")
async def get_runtime_stats(current_user: User = Depends(require_admin_user)):
    """Get runtime observability stats (admin only)."""
    return {
        "status": "ok",
        "llm": get_llm_gateway_stats(),
        "tools": get_tool_runtime_stats(),
    }


@router.get("/admin/progress/overview")
async def get_admin_progress_overview(
    date: Optional[str] = Query(default=None),
    tz: str = Query(default="Asia/Shanghai"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    del current_user
    try:
        return get_overview_daily_progress(db, date_str=date, tz_name=tz)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load overview: {exc}")


@router.get("/admin/progress/users/{user_id}")
async def get_admin_progress_user_detail(
    user_id: str,
    date: Optional[str] = Query(default=None),
    tz: str = Query(default="Asia/Shanghai"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    del current_user
    try:
        result = get_user_daily_progress(db, user_id=user_id, date_str=date, tz_name=tz)
        if not result.get("user"):
            raise HTTPException(status_code=404, detail="User not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load user detail: {exc}")


@router.post("/admin/progress/stream-ticket")
async def create_admin_stream_ticket(current_user: User = Depends(require_admin_user)):
    """生成 admin SSE 连接用的短时票据"""
    ticket = _create_admin_stream_ticket(current_user.id)
    return {"ticket": ticket}


def _verify_admin_stream_token(db: Session, token: str) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid stream token",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not is_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


@router.get("/admin/progress/stream")
async def stream_admin_progress(
    ticket: str = Query(..., min_length=10),
    date: Optional[str] = Query(default=None),
    tz: str = Query(default="Asia/Shanghai"),
):
    _consume_admin_stream_ticket(ticket)

    async def event_generator():
        queue = await subscribe_admin_progress_stream()
        try:
            ready_payload = json.dumps({"status": "connected", "date": date, "tz": tz}, ensure_ascii=False)
            yield f"event: ready\ndata: {ready_payload}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    data = json.dumps(payload, ensure_ascii=False)
                    yield f"event: progress_update\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await unsubscribe_admin_progress_stream(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ========== 用户管理 API ==========

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    role: str = Field("user", pattern="^(user|admin)$")


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=100)


@router.get("/admin/users")
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """获取所有用户列表"""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role or "user",
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in users
        ]
    }


@router.post("/admin/users")
async def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """创建新用户"""
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    new_user = User(
        id=str(uuid.uuid4()),
        username=request.username,
        password_hash=get_password_hash(request.password),
        display_name=request.display_name or request.username,
        role=request.role,
    )
    db.add(new_user)
    db.commit()
    return {"message": "用户创建成功", "user_id": new_user.id}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """删除用户"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # Check for related sheets
    sheet_count = db.query(InquirySheet).filter(InquirySheet.user_id == user_id).count()
    if sheet_count > 0:
        raise HTTPException(status_code=400, detail=f"该用户有 {sheet_count} 个表格，无法删除")

    db.delete(user)
    db.commit()
    return {"message": "用户已删除"}


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user),
):
    """重置用户密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = get_password_hash(request.new_password)
    db.commit()
    return {"message": "密码已重置"}
