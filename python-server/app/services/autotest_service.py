"""自动测试服务 — 用例管理、执行调度、结果采集、报告生成"""
import json
import time
from datetime import datetime, date
from typing import Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.autotest import AutoTestRun, AutoTestResult
from app.models.project import ReportProject, TestRecord
from app.models.template import TestCategory, TestItem
from app.services import engine_service


# ── 用例管理 ──

async def get_test_plan(db: AsyncSession, project_id: int) -> dict:
    """获取项目的测试计划（从模板自动生成）"""
    proj = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj.scalar_one_or_none()
    if not project:
        return {"code": 404, "message": "项目不存在", "data": None}

    categories = await db.execute(
        select(TestCategory).where(TestCategory.template_id == project.template_id)
        .order_by(TestCategory.sort_order)
    )
    plan = {"project_id": project_id, "project_code": project.project_code,
            "categories": [], "total_items": 0, "auto_items": 0, "manual_items": 0}

    for cat in categories.scalars().all():
        items = await db.execute(
            select(TestItem).where(TestItem.category_id == cat.id).order_by(TestItem.sort_order)
        )
        cat_data = {"id": cat.id, "name": cat.category_name, "code": cat.category_code,
                    "items": []}
        for item in items.scalars().all():
            if item.is_header:
                continue
            mode = "auto" if item.test_case else "manual"
            cat_data["items"].append({
                "id": item.id, "item_no": item.item_no, "test_item": item.test_item,
                "test_case": item.test_case, "criteria": item.criteria,
                "execute_mode": mode
            })
            plan["total_items"] += 1
            if mode == "auto":
                plan["auto_items"] += 1
            else:
                plan["manual_items"] += 1
        plan["categories"].append(cat_data)

    return {"code": 200, "message": "success", "data": plan}


async def get_available_tests(db: AsyncSession) -> dict:
    """获取引擎中可用的测试项列表"""
    try:
        engine = engine_service._get_engine()
        tests = []
        for tid, info in engine.test_registry.items():
            tests.append({"id": tid, "name": info.get("name", tid),
                         "category": info.get("category", ""), "mode": "auto"})
        return {"code": 200, "message": "success", "data": tests}
    except Exception as e:
        return {"code": 200, "message": "success", "data": []}


# ── 执行调度 ──

async def create_run(db: AsyncSession, project_id: int, run_type: str = "full",
                     run_name: str = "", created_by: int = None) -> dict:
    """创建测试执行记录"""
    proj = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj.scalar_one_or_none()
    if not project:
        return {"code": 404, "message": "项目不存在", "data": None}

    plan = await get_test_plan(db, project_id)
    total = plan["data"]["total_items"] if plan["data"] else 0

    if not run_name:
        run_name = f"自动测试-{project.project_code}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    run = AutoTestRun(
        project_id=project_id, run_name=run_name, run_type=run_type,
        status="pending", trigger_type="manual", total_items=total,
        config_json=json.dumps({"run_type": run_type}, ensure_ascii=False),
        created_by=created_by
    )
    db.add(run)
    await db.flush()

    # 创建空结果记录
    for cat in plan["data"]["categories"]:
        for item in cat["items"]:
            result = AutoTestResult(
                run_id=run.id, item_id=item["id"], category_name=cat["name"],
                item_no=item["item_no"], test_item=item["test_item"],
                test_case=item.get("test_case", ""), execute_mode=item["execute_mode"],
                result="Pending"
            )
            db.add(result)

    await db.flush()
    return {"code": 200, "message": "success", "data": {"run_id": run.id, "run_name": run_name, "total_items": total}}


async def execute_run(db: AsyncSession, run_id: int) -> dict:
    """执行测试运行"""
    run_result = await db.execute(
        select(AutoTestRun).where(AutoTestRun.id == run_id).options(selectinload(AutoTestRun.results))
    )
    run = run_result.scalar_one_or_none()
    if not run:
        return {"code": 404, "message": "测试运行不存在", "data": None}

    run.status = "running"
    run.started_at = datetime.now()
    await db.flush()

    passed = failed = skipped = error = 0
    start_time = time.time()

    for result in run.results:
        if result.execute_mode == "auto" and result.test_case:
            try:
                test_result = engine_service.execute_test_item(result.test_case, timeout=30)
                if test_result.get("code") == 200 and test_result.get("data"):
                    data = test_result["data"]
                    result.result = data.get("verdict", "Pass")
                    result.actual_value = json.dumps(data.get("details", {}), ensure_ascii=False)
                    result.duration_ms = int(data.get("duration_ms", 0))
                    if result.result == "Pass":
                        passed += 1
                    elif result.result == "Fail":
                        failed += 1
                    else:
                        error += 1
                else:
                    result.result = "Error"
                    result.error_detail = test_result.get("message", "未知错误")
                    error += 1
            except Exception as e:
                result.result = "Error"
                result.error_detail = str(e)
                error += 1
        else:
            result.result = "Skipped"
            skipped += 1

        result.executed_at = datetime.now()

    duration = time.time() - start_time
    total = run.total_items or 1

    run.status = "completed"
    run.completed_at = datetime.now()
    run.passed_items = passed
    run.failed_items = failed
    run.skipped_items = skipped
    run.error_items = error
    run.pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    run.duration_seconds = round(duration, 2)
    run.summary_json = json.dumps({
        "passed": passed, "failed": failed, "skipped": skipped,
        "error": error, "duration": round(duration, 2)
    }, ensure_ascii=False)

    await db.flush()

    # 同步更新测试记录
    await _sync_to_test_records(db, run)

    return {"code": 200, "message": "执行完成", "data": {
        "run_id": run.id, "status": run.status,
        "passed": passed, "failed": failed, "skipped": skipped, "error": error,
        "pass_rate": run.pass_rate, "duration": run.duration_seconds
    }}


async def _sync_to_test_records(db: AsyncSession, run: AutoTestRun):
    """将自动测试结果同步到测试记录表"""
    for result in run.results:
        if result.item_id and result.result in ("Pass", "Fail", "Error"):
            rec = await db.execute(
                select(TestRecord).where(and_(
                    TestRecord.project_id == run.project_id,
                    TestRecord.item_id == result.item_id
                ))
            )
            record = rec.scalar_one_or_none()
            if record:
                record.result = result.result
                record.comment = result.comment or result.error_detail
                record.tester = "AutoTest"
                record.test_date = date.today()


async def get_run_detail(db: AsyncSession, run_id: int) -> dict:
    """获取测试运行详情"""
    run_result = await db.execute(
        select(AutoTestRun).where(AutoTestRun.id == run_id).options(selectinload(AutoTestRun.results))
    )
    run = run_result.scalar_one_or_none()
    if not run:
        return {"code": 404, "message": "测试运行不存在", "data": None}

    data = {
        "id": run.id, "project_id": run.project_id, "run_name": run.run_name,
        "run_type": run.run_type, "status": run.status, "trigger_type": run.trigger_type,
        "total_items": run.total_items, "passed_items": run.passed_items,
        "failed_items": run.failed_items, "skipped_items": run.skipped_items,
        "error_items": run.error_items, "pass_rate": run.pass_rate,
        "duration_seconds": run.duration_seconds,
        "started_at": str(run.started_at) if run.started_at else None,
        "completed_at": str(run.completed_at) if run.completed_at else None,
        "created_at": str(run.created_at),
        "results": [{
            "id": r.id, "category_name": r.category_name, "item_no": r.item_no,
            "test_item": r.test_item, "execute_mode": r.execute_mode,
            "result": r.result, "actual_value": r.actual_value,
            "comment": r.comment, "duration_ms": r.duration_ms,
            "error_detail": r.error_detail,
            "executed_at": str(r.executed_at) if r.executed_at else None
        } for r in run.results]
    }
    return {"code": 200, "message": "success", "data": data}


# ── 结果采集 ──

async def get_run_list(db: AsyncSession, project_id: int = None, page: int = 1, size: int = 20) -> dict:
    """获取测试运行列表"""
    query = select(AutoTestRun).order_by(AutoTestRun.created_at.desc())
    if project_id:
        query = query.where(AutoTestRun.project_id == project_id)

    # 总数
    count_q = select(func.count(AutoTestRun.id))
    if project_id:
        count_q = count_q.where(AutoTestRun.project_id == project_id)
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    runs = []
    for r in result.scalars().all():
        runs.append({
            "id": r.id, "project_id": r.project_id, "run_name": r.run_name,
            "run_type": r.run_type, "status": r.status,
            "total_items": r.total_items, "passed_items": r.passed_items,
            "failed_items": r.failed_items, "pass_rate": r.pass_rate,
            "duration_seconds": r.duration_seconds,
            "started_at": str(r.started_at) if r.started_at else None,
            "completed_at": str(r.completed_at) if r.completed_at else None,
            "created_at": str(r.created_at)
        })
    return {"code": 200, "message": "success",
            "data": {"runs": runs, "total": total, "page": page, "size": size}}


async def get_statistics(db: AsyncSession, project_id: int = None) -> dict:
    """获取自动测试统计"""
    query = select(AutoTestRun)
    if project_id:
        query = query.where(AutoTestRun.project_id == project_id)
    result = await db.execute(query)
    runs = result.scalars().all()

    total_runs = len(runs)
    completed_runs = sum(1 for r in runs if r.status == "completed")
    failed_runs = sum(1 for r in runs if r.status == "failed")
    avg_pass_rate = sum(r.pass_rate for r in runs if r.status == "completed") / completed_runs if completed_runs > 0 else 0
    total_tests = sum(r.total_items for r in runs)
    total_passed = sum(r.passed_items for r in runs)
    total_failed = sum(r.failed_items for r in runs)

    # 最近一次运行
    latest = runs[0] if runs else None

    data = {
        "total_runs": total_runs, "completed_runs": completed_runs,
        "failed_runs": failed_runs, "avg_pass_rate": round(avg_pass_rate, 1),
        "total_tests": total_tests, "total_passed": total_passed,
        "total_failed": total_failed,
        "latest_run": {
            "id": latest.id, "run_name": latest.run_name, "status": latest.status,
            "pass_rate": latest.pass_rate, "created_at": str(latest.created_at)
        } if latest else None
    }
    return {"code": 200, "message": "success", "data": data}


async def cancel_run(db: AsyncSession, run_id: int) -> dict:
    """取消测试运行"""
    run_result = await db.execute(select(AutoTestRun).where(AutoTestRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        return {"code": 404, "message": "测试运行不存在", "data": None}
    if run.status not in ("pending", "running"):
        return {"code": 400, "message": "只能取消待执行或执行中的任务", "data": None}

    run.status = "cancelled"
    run.completed_at = datetime.now()
    await db.flush()
    return {"code": 200, "message": "已取消", "data": {"run_id": run_id}}


async def delete_run(db: AsyncSession, run_id: int) -> dict:
    """删除测试运行"""
    run_result = await db.execute(
        select(AutoTestRun).where(AutoTestRun.id == run_id).options(selectinload(AutoTestRun.results))
    )
    run = run_result.scalar_one_or_none()
    if not run:
        return {"code": 404, "message": "测试运行不存在", "data": None}

    await db.delete(run)
    await db.flush()
    return {"code": 200, "message": "已删除", "data": {"run_id": run_id}}


# ── 报告生成 ──

async def generate_run_report(db: AsyncSession, run_id: int) -> dict:
    """生成测试运行 HTML 报告"""
    run_detail = await get_run_detail(db, run_id)
    if run_detail["code"] != 200:
        return run_detail

    run = run_detail["data"]

    # 按分类分组结果
    categories = {}
    for r in run["results"]:
        cat = r["category_name"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    html = _build_report_html(run, categories)
    return {"code": 200, "message": "success", "data": {"html": html, "run_name": run["run_name"]}}


def _build_report_html(run: dict, categories: dict) -> str:
    """构建 HTML 报告"""
    status_colors = {"Pass": "#22c55e", "Fail": "#ef4444", "Error": "#f59e0b",
                     "Skipped": "#94a3b8", "Pending": "#94a3b8"}

    rows_html = ""
    for cat_name, items in categories.items():
        rows_html += f'<tr><td colspan="7" style="background:#f1f5f9;font-weight:600;">{cat_name}</td></tr>'
        for item in items:
            color = status_colors.get(item["result"], "#94a3b8")
            rows_html += f'''<tr>
                <td>{item["item_no"]}</td><td>{item["test_item"]}</td>
                <td>{item["execute_mode"]}</td>
                <td style="color:{color};font-weight:600;">{item["result"]}</td>
                <td>{item.get("actual_value","")[:100]}</td>
                <td>{item["comment"]}</td>
                <td>{item.get("duration_ms",0)}ms</td>
            </tr>'''

    pass_rate_color = "#22c55e" if run["pass_rate"] >= 90 else "#f59e0b" if run["pass_rate"] >= 70 else "#ef4444"

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
    <title>自动测试报告 - {run["run_name"]}</title>
    <style>
        body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:20px;color:#1e293b;}}
        h1{{color:#0f172a;border-bottom:3px solid #3b82f6;padding-bottom:10px;}}
        .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0;}}
        .card{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;text-align:center;}}
        .card .value{{font-size:28px;font-weight:700;margin:4px 0;}}
        .card .label{{font-size:13px;color:#64748b;}}
        table{{width:100%;border-collapse:collapse;margin:20px 0;}}
        th,td{{border:1px solid #e2e8f0;padding:8px 12px;text-align:left;font-size:13px;}}
        th{{background:#f1f5f9;font-weight:600;}}
        .footer{{margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;}}
    </style></head><body>
    <h1>自动测试报告</h1>
    <p><strong>测试名称：</strong>{run["run_name"]}</p>
    <p><strong>执行时间：</strong>{run.get("started_at","N/A")} ~ {run.get("completed_at","N/A")}</p>
    <p><strong>耗时：</strong>{run["duration_seconds"]}秒</p>
    <div class="summary">
        <div class="card"><div class="value">{run["total_items"]}</div><div class="label">总项数</div></div>
        <div class="card"><div class="value" style="color:#22c55e;">{run["passed_items"]}</div><div class="label">通过</div></div>
        <div class="card"><div class="value" style="color:#ef4444;">{run["failed_items"]}</div><div class="label">失败</div></div>
        <div class="card"><div class="value" style="color:#f59e0b;">{run["error_items"]}</div><div class="label">错误</div></div>
        <div class="card"><div class="value">{run["skipped_items"]}</div><div class="label">跳过</div></div>
        <div class="card"><div class="value" style="color:{pass_rate_color};">{run["pass_rate"]}%</div><div class="label">通过率</div></div>
    </div>
    <table><thead><tr>
        <th>编号</th><th>测试项</th><th>执行方式</th><th>结果</th><th>实际值</th><th>备注</th><th>耗时</th>
    </tr></thead><tbody>{rows_html}</tbody></table>
    <div class="footer">QCC 自动测试平台 | 报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
    </body></html>'''
