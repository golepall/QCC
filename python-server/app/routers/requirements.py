"""需求管理路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import requirement_service

router = APIRouter(prefix="/api/requirements", tags=["需求管理"])


@router.get("")
async def list_requirements(
    status: str = Query(""), req_type: str = Query(""), priority: str = Query(""),
    keyword: str = Query(""), project_id: str = Query(""), assigned_to: str = Query(""),
    page: int = Query(1), pageSize: int = Query(50),
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    assigned = None
    if assigned_to == "me":
        assigned = user.id
    elif assigned_to:
        assigned = int(assigned_to)
    pid = int(project_id) if project_id else None
    data = await requirement_service.get_requirements(db, status, req_type, priority, keyword, pid, assigned, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/stats")
async def get_stats(assigned_to: str = Query(""), db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    assigned = None
    if assigned_to == "me":
        assigned = user.id
    elif assigned_to:
        assigned = int(assigned_to)
    data = await requirement_service.get_req_stats(db, assigned)
    return {"code": 200, "message": "success", "data": data}


@router.get("/users")
async def get_users(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await requirement_service.get_assignable_users(db)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{req_id}")
async def get_requirement(req_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await requirement_service.get_requirement_detail(db, req_id)
    if data is None:
        return {"code": 404, "message": "需求不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.post("")
async def create_requirement(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await requirement_service.create_requirement(db, req, user.id)
    if "error" in result:
        return {"code": 400, "message": result["error"], "data": None}
    return {"code": 200, "message": "创建成功", "data": result}


@router.put("/{req_id}")
async def update_requirement(req_id: int, data: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok = await requirement_service.update_requirement(db, req_id, data, user.id)
    if not ok:
        return {"code": 404, "message": "需求不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.delete("/{req_id}")
async def delete_requirement(req_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok = await requirement_service.delete_requirement(db, req_id)
    if not ok:
        return {"code": 404, "message": "需求不存在", "data": None}
    return {"code": 200, "message": "删除成功", "data": None}
