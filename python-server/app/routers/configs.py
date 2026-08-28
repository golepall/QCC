"""设备配置管理路由"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.services import config_service

router = APIRouter(prefix="/api/configs", tags=["设备配置"])


@router.get("")
async def list_configs(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await config_service.get_configs(db)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{config_id}")
async def get_config(config_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await config_service.get_config(db, config_id)
    if data is None:
        return {"code": 404, "message": "配置不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.post("")
async def create_config(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await config_service.create_config(db, req)
    return {"code": 200, "message": "创建成功", "data": data}


@router.put("/{config_id}")
async def update_config(config_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok = await config_service.update_config(db, config_id, req)
    if not ok:
        return {"code": 404, "message": "配置不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.post("/import")
async def import_config(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await config_service.import_config(db, req)
    return {"code": 200, "message": "导入成功", "data": data}
