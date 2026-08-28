"""SSH 远程执行路由（直接调用测试引擎，不再 HTTP 代理 Flask）"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.services import engine_service

router = APIRouter(prefix="/api/remote", tags=["SSH 远程"])


@router.post("/connect")
async def remote_connect(req: dict, user=Depends(get_current_user)):
    """SSH 连接测试"""
    host = req.get("host", "")
    username = req.get("username", "")
    if not host or not username:
        return {"code": 400, "message": "请填写主机IP和用户名", "data": None}
    return engine_service.remote_connect(
        host, req.get("port", 22), username, req.get("password", "")
    )


@router.post("/collect")
async def remote_collect(req: dict, user=Depends(get_current_user)):
    """SSH 远程采集系统信息"""
    return engine_service.remote_collect(
        req.get("host", ""), req.get("port", 22),
        req.get("username", ""), req.get("password", "")
    )


@router.post("/execute")
async def remote_execute(req: dict, user=Depends(get_current_user)):
    """SSH 远程执行测试"""
    return engine_service.remote_execute(
        req.get("host", ""), req.get("port", 22),
        req.get("username", ""), req.get("password", ""),
        req.get("testIds"), req.get("spec"), req.get("timeout", 30)
    )


@router.post("/run-and-save")
async def remote_run_and_save(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """SSH 远程执行全部测试并保存结果到项目"""
    from sqlalchemy import select
    from app.models.project import ReportProject
    from app.models.template import TestCategory, TestItem
    from app.models.management import ReportBatch, ActivityLog

    project_id = req.get("projectId")
    if not project_id:
        return {"code": 400, "message": "请指定项目ID", "data": None}

    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return {"code": 404, "message": "项目不存在", "data": None}

    items_result = await db.execute(
        select(TestItem).join(TestCategory).where(
            TestCategory.template_id == project.template_id,
            TestItem.is_header == 0,
            TestItem.test_case != "",
        ).order_by(TestCategory.sort_order, TestItem.sort_order)
    )
    test_ids = [item.test_case for item in items_result.scalars().all() if item.test_case]

    result = engine_service.remote_execute(
        req.get("host", ""), req.get("port", 22),
        req.get("username", ""), req.get("password", ""),
        test_ids, req.get("spec"), req.get("timeout", 30)
    )

    if result.get("code") == 200:
        batch = ReportBatch(
            project_id=project_id, batch_type="remote_execute",
            source="ssh", status="completed",
            summary_json=str(result.get("data", {})),
            note=f"SSH远程执行 {req.get('host')}",
            created_by=user.id,
        )
        db.add(batch)
        db.add(ActivityLog(user_id=user.id, action="execute", target_type="remote_report",
                          target_id=None, detail=f"远程执行 {project.project_code}"))
        await db.flush()
        result["data"] = {"results": result.get("data"), "batchId": batch.id}

    return result
