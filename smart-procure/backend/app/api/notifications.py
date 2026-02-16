from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.utils import get_current_user
from ..models.database import get_db, User
from ..services.notification_service import pop_notifications

router = APIRouter()


@router.get("/notifications")
async def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get and clear notifications for current user."""
    notifications = pop_notifications(db, current_user.id)
    return {"notifications": notifications}

