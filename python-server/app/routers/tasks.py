"""任务管理路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import task_service

router = APIRouter(prefix="/api/tasks", tags=["任务管理"])


@router.get("")
async def list_tasks(
    status: str = Query(""), priority: str = Query(""), project_id: str = Query(""),
    assigned_to: str = Query(""), keyword: str = Query(""),
    page: int = Query(1), pageSize: int = Query(100),
    db: AsyncSession = Depends(get_db),
):
    assigned = None
    if assigned_to == "me":
        assigned = 1  # 默认用户
    elif assigned_to:
        assigned = int(assigned_to)
    pid = int(project_id) if project_id else None
    data = await task_service.get_tasks(db, status, priority, pid, assigned, keyword, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/board")
async def get_board(
    project_id: str = Query(""), assigned_to: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    assigned = None
    if assigned_to == "me":
        assigned = 1
    elif assigned_to:
        assigned = int(assigned_to)
    pid = int(project_id) if project_id else None
    data = await task_service.get_task_board(db, pid, assigned)
    return {"code": 200, "message": "success", "data": data}


@router.get("/stats")
async def get_stats(assigned_to: str = Query(""), db: AsyncSession = Depends(get_db)):
    assigned = None
    if assigned_to == "me":
        assigned = 1
    elif assigned_to:
        assigned = int(assigned_to)
    data = await task_service.get_task_stats(db, assigned)
    return {"code": 200, "message": "success", "data": data}


@router.get("/users")
async def get_users(db: AsyncSession = Depends(get_db)):
    from app.models.user import User
    result = await db.execute(select(User.id, User.username, User.display_name).order_by(User.display_name))
    data = [{"id": r.id, "username": r.username, "display_name": r.display_name} for r in result.all()]
    return {"code": 200, "message": "success", "data": data}


@router.get("/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    data = await task_service.get_task_detail(db, task_id)
    if data is None:
        return {"code": 404, "message": "任务不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.post("")
async def create_task(req: dict, db: AsyncSession = Depends(get_db)):
    result = await task_service.create_task(db, req, 1)
    if "error" in result:
        return {"code": 400, "message": result["error"], "data": None}
    return {"code": 200, "message": "创建成功", "data": result}


@router.put("/{task_id}")
async def update_task(task_id: int, req: dict, db: AsyncSession = Depends(get_db)):
    ok = await task_service.update_task(db, task_id, req, 1)
    if not ok:
        return {"code": 404, "message": "任务不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.put("/{task_id}/status")
async def update_task_status(task_id: int, req: dict, db: AsyncSession = Depends(get_db)):
    ok = await task_service.update_task_status(db, task_id, req.get("status"))
    if not ok:
        return {"code": 404, "message": "任务不存在", "data": None}
    return {"code": 200, "message": "状态更新成功", "data": None}


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    ok = await task_service.delete_task(db, task_id)
    if not ok:
        return {"code": 404, "message": "任务不存在", "data": None}
    return {"code": 200, "message": "删除成功", "data": None}
