"""通知管理路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import notification_service

router = APIRouter(prefix="/api/notifications", tags=["通知"])


@router.get("")
async def list_notifications(
    is_read: str = Query(None), page: int = Query(1), pageSize: int = Query(50),
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    read_filter = int(is_read) if is_read is not None else None
    data = await notification_service.get_notifications(db, user.id, read_filter, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    cnt = await notification_service.get_unread_count(db, user.id)
    return {"code": 200, "message": "success", "data": {"count": cnt}}


@router.put("/{noti_id}/read")
async def mark_read(noti_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await notification_service.mark_as_read(db, noti_id, user.id)
    return {"code": 200, "message": "ok", "data": None}


@router.put("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await notification_service.mark_all_read(db, user.id)
    return {"code": 200, "message": "ok", "data": None}


@router.delete("/{noti_id}")
async def delete_notification(noti_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await notification_service.delete_notification(db, noti_id, user.id)
    return {"code": 200, "message": "ok", "data": None}
