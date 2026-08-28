"""项目管理路由（/api/projects）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["项目管理"])


@router.get("")
async def list_projects(
    status: str = Query(""), template_id: str = Query(""), tester: str = Query(""),
    keyword: str = Query(""), product_id: str = Query(""), parent_id: str = Query(""),
    page: int = Query(1), pageSize: int = Query(20),
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    data = await project_service.get_projects(db, status, template_id, tester, keyword, product_id, parent_id, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await project_service.get_project_detail(db, project_id)
    if data is None:
        return {"code": 404, "message": "项目不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.post("")
async def create_project(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await project_service.create_project(db, req, user.id)
    if "error" in result:
        return {"code": 400, "message": result["error"], "data": None}
    return {"code": 200, "message": "创建成功", "data": result}


@router.put("/{project_id}")
async def update_project(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await project_service.update_project(db, project_id, req, user.id, user.role)
    if result is None:
        return {"code": 404, "message": "项目不存在", "data": None}
    if "error" in result:
        return {"code": 403, "message": result["error"], "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await project_service.delete_project(db, project_id, user.id, user.role)
    if "error" in result:
        code = 404 if result["error"] == "项目不存在" else 403
        return {"code": code, "message": result["error"], "data": None}
    return {"code": 200, "message": "删除成功", "data": None}


@router.put("/{project_id}/status")
async def update_status(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await project_service.update_project_status(db, project_id, req.get("status"), req.get("conclusion"), user.id)
    if result is None:
        return {"code": 404, "message": "项目不存在", "data": None}
    return {"code": 200, "message": "状态更新成功", "data": None}


@router.get("/{project_id}/summary")
async def project_summary(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    data = await project_service.get_project_summary(db, project_id)
    if data is None:
        return {"code": 404, "message": "项目不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}
