"""测试记录路由（挂载在 /api/projects 下）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.services import record_service

router = APIRouter(prefix="/api/projects", tags=["测试记录"])


@router.get("/{project_id}/records")
async def get_records(
    project_id: int, category_id: str = Query(""),
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    data = await record_service.get_records(db, project_id, category_id)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{project_id}/records/all")
async def get_all_records(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await record_service.get_all_records(db, project_id)
    if data is None:
        return {"code": 404, "message": "项目不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.put("/{project_id}/records/{record_id}")
async def update_record(project_id: int, record_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok = await record_service.update_record(db, project_id, record_id, req)
    if not ok:
        return {"code": 404, "message": "记录不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.put("/{project_id}/records/batch")
async def batch_update(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    records = req.get("records", [])
    if not isinstance(records, list):
        return {"code": 400, "message": "参数错误", "data": None}
    await record_service.batch_update_records(db, project_id, records)
    return {"code": 200, "message": "批量更新成功", "data": None}


@router.get("/{project_id}/records/stats")
async def record_stats(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await record_service.get_record_stats(db, project_id)
    return {"code": 200, "message": "success", "data": data}


@router.post("/{project_id}/records/batch-set")
async def batch_set(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    category_id = req.get("category_id")
    result_value = req.get("result")
    if not category_id or not result_value:
        return {"code": 400, "message": "参数错误", "data": None}
    await record_service.batch_set_records(db, project_id, int(category_id), result_value)
    return {"code": 200, "message": "批量设置成功", "data": None}
