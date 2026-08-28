"""Bug 管理路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import bug_service

router = APIRouter(prefix="/api/projects", tags=["Bug 管理"])


@router.get("/bugs/all")
async def list_all_bugs(
    status: str = Query(""), severity: str = Query(""), keyword: str = Query(""),
    page: int = Query(1), pageSize: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    data = await bug_service.get_all_bugs(db, status, severity, keyword, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{project_id}/bugs")
async def get_bugs(
    project_id: int, status: str = Query(""), severity: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    data = await bug_service.get_project_bugs(db, project_id, status, severity)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{project_id}/bugs/stats")
async def get_bug_stats(project_id: int, db: AsyncSession = Depends(get_db)):
    data = await bug_service.get_bug_stats(db, project_id)
    return {"code": 200, "message": "success", "data": data}


@router.post("/{project_id}/bugs")
async def create_bug(project_id: int, req: dict, db: AsyncSession = Depends(get_db)):
    result = await bug_service.create_bug(db, project_id, req)
    if "error" in result:
        return {"code": 400, "message": result["error"], "data": None}
    return {"code": 200, "message": "Bug创建成功", "data": result}


@router.get("/{project_id}/bugs/{bug_id}")
async def get_bug(project_id: int, bug_id: int, db: AsyncSession = Depends(get_db)):
    bug = await bug_service.get_bug_detail(db, project_id, bug_id)
    if bug is None:
        return {"code": 404, "message": "Bug不存在", "data": None}
    data = {c.name: getattr(bug, c.name) for c in bug.__table__.columns}
    for key in ("open_date", "close_date", "created_at", "updated_at"):
        if data.get(key):
            data[key] = str(data[key])
    return {"code": 200, "message": "success", "data": data}


@router.put("/{project_id}/bugs/{bug_id}")
async def update_bug(project_id: int, bug_id: int, req: dict, db: AsyncSession = Depends(get_db)):
    ok = await bug_service.update_bug(db, project_id, bug_id, req)
    if not ok:
        return {"code": 404, "message": "Bug不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.put("/{project_id}/bugs/{bug_id}/status")
async def update_bug_status(project_id: int, bug_id: int, req: dict, db: AsyncSession = Depends(get_db)):
    ok = await bug_service.update_bug_status(db, project_id, bug_id, req.get("status"), req.get("close_date"))
    if not ok:
        return {"code": 404, "message": "Bug不存在", "data": None}
    return {"code": 200, "message": "状态更新成功", "data": None}
