import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..auth.utils import decode_token, is_admin_user, require_admin_user
from ..core.llm import get_llm_gateway_stats
from ..services.agent_runtime import get_tool_runtime_stats
from ..services.admin_progress_service import get_overview_daily_progress, get_user_daily_progress
from ..services.admin_progress_stream import (
    subscribe_admin_progress_stream,
    unsubscribe_admin_progress_stream,
)

router = APIRouter()


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
        raise HTTPException(status_code=500, detail=f"Failed to rebuild embeddings: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


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
    token: str = Query(..., min_length=10),
    date: Optional[str] = Query(default=None),
    tz: str = Query(default="Asia/Shanghai"),
    db: Session = Depends(get_db),
):
    _verify_admin_stream_token(db, token)

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
