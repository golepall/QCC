"""仪表盘与工作区路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await dashboard_service.get_dashboard_data(db)
    return {"code": 200, "message": "success", "data": data}


@router.get("/workspace")
async def get_workspace(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await dashboard_service.get_workspace_data(db, user.id)
    return {"code": 200, "message": "success", "data": data}
