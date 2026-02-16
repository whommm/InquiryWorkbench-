from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..auth.utils import require_admin_user
from ..core.llm import get_llm_gateway_stats
from ..services.agent_runtime import get_tool_runtime_stats

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
