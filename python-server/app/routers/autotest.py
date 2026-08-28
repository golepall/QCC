"""自动测试模块路由 — 用例管理、执行调度、结果采集、报告生成"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import autotest_service, engine_service

router = APIRouter(prefix="/api/autotest", tags=["自动测试"])


# ── 用例管理 ──

@router.get("/plan/{project_id}")
async def get_test_plan(project_id: int, db: AsyncSession = Depends(get_db)):
    """获取项目测试计划"""
    return await autotest_service.get_test_plan(db, project_id)


@router.get("/available-tests")
async def get_available_tests(db: AsyncSession = Depends(get_db)):
    """获取引擎可用测试项"""
    return await autotest_service.get_available_tests(db)


# ── 执行调度 ──

@router.post("/run/create")
async def create_run(data: dict, db: AsyncSession = Depends(get_db)):
    """创建测试运行"""
    project_id = data.get("project_id")
    if not project_id:
        return {"code": 400, "message": "缺少 project_id", "data": None}
    return await autotest_service.create_run(
        db, project_id,
        run_type=data.get("run_type", "full"),
        run_name=data.get("run_name", "")
    )


@router.post("/run/{run_id}/execute")
async def execute_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """执行测试运行"""
    return await autotest_service.execute_run(db, run_id)


@router.post("/run/{run_id}/cancel")
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """取消测试运行"""
    return await autotest_service.cancel_run(db, run_id)


@router.delete("/run/{run_id}")
async def delete_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """删除测试运行"""
    return await autotest_service.delete_run(db, run_id)


@router.get("/run/{run_id}")
async def get_run_detail(run_id: int, db: AsyncSession = Depends(get_db)):
    """获取测试运行详情"""
    return await autotest_service.get_run_detail(db, run_id)


@router.get("/runs")
async def get_run_list(project_id: int = None, page: int = 1, size: int = 20,
                       db: AsyncSession = Depends(get_db)):
    """获取测试运行列表"""
    return await autotest_service.get_run_list(db, project_id, page, size)


# ── 结果采集 ──

@router.get("/statistics")
async def get_statistics(project_id: int = None, db: AsyncSession = Depends(get_db)):
    """获取自动测试统计"""
    return await autotest_service.get_statistics(db, project_id)


# ── 系统采集 ──

@router.get("/system/collect")
async def collect_system():
    """采集本机系统信息"""
    return engine_service.collect_system()


@router.post("/system/validate")
async def validate_config(data: dict):
    """验证设备配置"""
    return engine_service.validate_config(data.get("config"), data.get("spec"))


# ── 报告生成 ──

@router.get("/run/{run_id}/report")
async def get_run_report(run_id: int, db: AsyncSession = Depends(get_db)):
    """获取测试运行 HTML 报告"""
    return await autotest_service.generate_run_report(db, run_id)


@router.get("/run/{run_id}/report/html", response_class=HTMLResponse)
async def preview_run_report(run_id: int, db: AsyncSession = Depends(get_db)):
    """预览测试运行 HTML 报告"""
    result = await autotest_service.generate_run_report(db, run_id)
    if result["code"] == 200:
        return result["data"]["html"]
    return HTMLResponse(content=f"<h1>报告生成失败：{result['message']}</h1>", status_code=404)
