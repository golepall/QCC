"""报告生成服务 — 汇总测试记录+Bug数据，生成结构化报告"""
import os
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ReportProject, TestRecord, BugRecord
from app.models.template import ReportTemplate, TestCategory, TestItem
from app.models.management import ReportBatch, ReportArtifact, ActivityLog


async def generate_report_data(db: AsyncSession, project_id: int) -> dict:
    """汇总项目数据，生成结构化报告数据"""
    # 获取项目
    proj_result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        return {"error": "项目不存在"}

    # 获取模板
    tpl_result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == project.template_id))
    template = tpl_result.scalar_one_or_none()

    # 获取分类和测试项
    cat_result = await db.execute(
        select(TestCategory).where(TestCategory.template_id == project.template_id).order_by(TestCategory.sort_order)
    )
    categories = list(cat_result.scalars().all())

    # 获取全部测试记录
    rec_result = await db.execute(select(TestRecord).where(TestRecord.project_id == project_id))
    all_records = list(rec_result.scalars().all())
    record_map = {r.item_id: r for r in all_records}

    # 获取全部Bug
    bug_result = await db.execute(select(BugRecord).where(BugRecord.project_id == project_id))
    all_bugs = list(bug_result.scalars().all())

    # 统计
    total = len(all_records)
    passed = sum(1 for r in all_records if r.result == "Pass")
    failed = sum(1 for r in all_records if r.result == "Fail")
    blocked = sum(1 for r in all_records if r.result == "Blocked")
    na = sum(1 for r in all_records if r.result == "NA")
    error = sum(1 for r in all_records if r.result == "Error")
    not_tested = sum(1 for r in all_records if not r.result or r.result in ("", "NotTested"))

    stats = {
        "total": total,
        "pass": passed,
        "fail": failed,
        "blocked": blocked,
        "na": na,
        "error": error,
        "not_tested": not_tested,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
    }

    # 按分类组织测试结果
    category_results = []
    for cat in categories:
        item_result = await db.execute(
            select(TestItem).where(TestItem.category_id == cat.id).order_by(TestItem.sort_order)
        )
        items = list(item_result.scalars().all())

        cat_items = []
        cat_pass = 0
        cat_fail = 0
        cat_total = 0

        for item in items:
            if item.is_header:
                cat_items.append({
                    "is_header": True,
                    "item_no": item.item_no,
                    "test_item": item.test_item,
                })
                continue

            record = record_map.get(item.id)
            result = record.result if record else ""
            comment = record.comment if record else ""

            if result:
                cat_total += 1
                if result == "Pass":
                    cat_pass += 1
                elif result in ("Fail", "Error"):
                    cat_fail += 1

            cat_items.append({
                "is_header": False,
                "item_no": item.item_no,
                "test_item": item.test_item,
                "test_case": item.test_case or item.condition_desc or "",
                "criteria": item.criteria or "",
                "result": result,
                "comment": comment,
            })

        category_results.append({
            "category_name": cat.category_name,
            "category_code": cat.category_code,
            "items": cat_items,
            "stats": {
                "total": cat_total,
                "pass": cat_pass,
                "fail": cat_fail,
                "pass_rate": round(cat_pass / cat_total * 100, 1) if cat_total > 0 else 0,
            }
        })

    # Bug统计
    bug_stats = {
        "total": len(all_bugs),
        "open": sum(1 for b in all_bugs if b.status == "open"),
        "closed": sum(1 for b in all_bugs if b.status == "closed"),
        "critical": sum(1 for b in all_bugs if b.severity == "critical"),
        "high": sum(1 for b in all_bugs if b.severity == "high"),
        "medium": sum(1 for b in all_bugs if b.severity == "medium"),
        "low": sum(1 for b in all_bugs if b.severity == "low"),
    }

    bug_list = [{
        "bug_id": b.bug_id,
        "title": b.title,
        "severity": b.severity,
        "status": b.status,
        "category": b.category,
        "description": b.description,
        "solution": b.solution,
        "tester": b.tester,
    } for b in all_bugs]

    return {
        "project": {
            "id": project.id,
            "project_code": project.project_code,
            "product_name": project.product_name,
            "product_model": project.product_model,
            "tester": project.tester,
            "reviewer": project.reviewer,
            "approver": project.approver,
            "test_type": project.test_type,
            "start_date": str(project.start_date) if project.start_date else "",
            "end_date": str(project.end_date) if project.end_date else "",
            "status": project.status,
            "conclusion": project.conclusion,
            "remark": project.remark,
        },
        "template": {
            "name": template.name if template else "",
            "doc_code": template.doc_code if template else "",
            "version": template.version if template else "",
        } if template else None,
        "stats": stats,
        "category_results": category_results,
        "bug_stats": bug_stats,
        "bug_list": bug_list,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


async def generate_report_html(db: AsyncSession, project_id: int) -> str:
    """生成HTML格式的测试报告"""
    data = await generate_report_data(db, project_id)
    if "error" in data:
        return f"<h1>{data['error']}</h1>"

    project = data["project"]
    template = data["template"]
    stats = data["stats"]
    bug_stats = data["bug_stats"]

    # 构建HTML报告
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{template['doc_code'] if template else ''} — {project['product_name']} 测试报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #333; line-height: 1.6; background: #f5f7fa; }}
.report-container {{ max-width: 1000px; margin: 0 auto; background: #fff; }}
.cover {{ text-align: center; padding: 80px 40px; background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: #fff; page-break-after: always; }}
.cover h1 {{ font-size: 28px; margin-bottom: 10px; }}
.cover h2 {{ font-size: 20px; font-weight: 400; margin-bottom: 40px; opacity: 0.9; }}
.cover .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px 30px; text-align: left; max-width: 500px; margin: 0 auto; }}
.cover .info-label {{ opacity: 0.7; font-size: 13px; }}
.cover .info-value {{ font-size: 15px; font-weight: 500; }}
.section {{ padding: 30px 40px; border-bottom: 1px solid #eee; }}
.section:last-child {{ border-bottom: none; }}
.section-title {{ font-size: 18px; color: #1e3a5f; border-left: 4px solid #2d5a87; padding-left: 12px; margin-bottom: 20px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }}
.stat-card {{ background: #f8fafc; border-radius: 8px; padding: 16px; text-align: center; border: 1px solid #e2e8f0; }}
.stat-value {{ font-size: 28px; font-weight: 700; color: #1e3a5f; }}
.stat-label {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
.stat-card.pass .stat-value {{ color: #16a34a; }}
.stat-card.fail .stat-value {{ color: #dc2626; }}
.stat-card.warn .stat-value {{ color: #f59e0b; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #f1f5f9; color: #475569; font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 2px solid #e2e8f0; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }}
tr:hover {{ background: #f8fafc; }}
.result-pass {{ color: #16a34a; font-weight: 600; }}
.result-fail {{ color: #dc2626; font-weight: 600; }}
.result-blocked {{ color: #f59e0b; font-weight: 600; }}
.result-na {{ color: #64748b; }}
.header-row {{ background: #e8eef6; font-weight: 600; }}
.bug-sev-critical {{ background: #fecaca; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
.bug-sev-high {{ background: #fed7aa; color: #9a3412; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
.bug-sev-medium {{ background: #fef08a; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
.bug-sev-low {{ background: #d1fae5; color: #065f46; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
.bug-status-open {{ color: #dc2626; }}
.bug-status-closed {{ color: #16a34a; }}
.conclusion-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; }}
.conclusion-box.fail {{ background: #fef2f2; border-color: #fecaca; }}
.footer {{ text-align: center; padding: 20px; color: #94a3b8; font-size: 12px; border-top: 1px solid #eee; }}
@media print {{
    body {{ background: #fff; }}
    .report-container {{ box-shadow: none; }}
    .section {{ page-break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="report-container">

<!-- 封面 -->
<div class="cover">
    <h1>{template['doc_code'] if template else '测试报告'}</h1>
    <h2>{project['product_name']}</h2>
    <div class="info-grid">
        <div><div class="info-label">项目编号</div><div class="info-value">{project['project_code']}</div></div>
        <div><div class="info-label">产品型号</div><div class="info-value">{project['product_model']}</div></div>
        <div><div class="info-label">测试人员</div><div class="info-value">{project['tester']}</div></div>
        <div><div class="info-label">审核人员</div><div class="info-value">{project['reviewer'] or '—'}</div></div>
        <div><div class="info-label">测试周期</div><div class="info-value">{project['start_date'] or '—'} ~ {project['end_date'] or '—'}</div></div>
        <div><div class="info-label">生成时间</div><div class="info-value">{data['generated_at']}</div></div>
    </div>
</div>

<!-- 测试概况 -->
<div class="section">
    <h2 class="section-title">一、测试概况</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{stats['total']}</div><div class="stat-label">测试总数</div></div>
        <div class="stat-card pass"><div class="stat-value">{stats['pass']}</div><div class="stat-label">通过</div></div>
        <div class="stat-card fail"><div class="stat-value">{stats['fail']}</div><div class="stat-label">失败</div></div>
        <div class="stat-card warn"><div class="stat-value">{stats['pass_rate']}%</div><div class="stat-label">通过率</div></div>
    </div>
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{stats['blocked']}</div><div class="stat-label">阻塞</div></div>
        <div class="stat-card"><div class="stat-value">{stats['na']}</div><div class="stat-label">不适用</div></div>
        <div class="stat-card"><div class="stat-value">{stats['error']}</div><div class="stat-label">错误</div></div>
        <div class="stat-card"><div class="stat-value">{stats['not_tested']}</div><div class="stat-label">未测试</div></div>
    </div>
</div>

<!-- 分类测试结果 -->
<div class="section">
    <h2 class="section-title">二、测试结果明细</h2>"""

    for cat in data["category_results"]:
        cat_stats = cat["stats"]
        html += f"""
    <h3 style="margin: 20px 0 10px; color: #334155;">{cat['category_name']}（通过率 {cat_stats['pass_rate']}%，{cat_stats['pass']}/{cat_stats['total']}）</h3>
    <table>
        <thead><tr><th style="width:60px">编号</th><th>测试项目</th><th>测试条件</th><th>判定标准</th><th style="width:80px">结果</th><th>备注</th></tr></thead>
        <tbody>"""
        for item in cat["items"]:
            if item["is_header"]:
                html += f'<tr class="header-row"><td colspan="6">{item["item_no"]} {item["test_item"]}</td></tr>'
            else:
                result = item["result"]
                result_class = f'result-{result.lower()}' if result else ''
                result_display = result or "未测"
                html += f"""<tr>
                    <td>{item['item_no']}</td>
                    <td>{item['test_item']}</td>
                    <td>{item['test_case']}</td>
                    <td>{item['criteria']}</td>
                    <td><span class="{result_class}">{result_display}</span></td>
                    <td>{item['comment']}</td>
                </tr>"""
        html += "</tbody></table>"

    html += "</div>"

    # Bug部分
    if data["bug_list"]:
        html += f"""
<!-- 缺陷统计 -->
<div class="section">
    <h2 class="section-title">三、缺陷统计</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{bug_stats['total']}</div><div class="stat-label">缺陷总数</div></div>
        <div class="stat-card fail"><div class="stat-value">{bug_stats['open']}</div><div class="stat-label">未关闭</div></div>
        <div class="stat-card pass"><div class="stat-value">{bug_stats['closed']}</div><div class="stat-label">已关闭</div></div>
        <div class="stat-card warn"><div class="stat-value">{bug_stats['critical']}</div><div class="stat-label">严重缺陷</div></div>
    </div>
    <table>
        <thead><tr><th>Bug编号</th><th>标题</th><th>严重程度</th><th>状态</th><th>解决方案</th></tr></thead>
        <tbody>"""
        for bug in data["bug_list"]:
            sev_class = f'bug-sev-{bug["severity"]}'
            status_class = f'bug-status-{bug["status"]}'
            html += f"""<tr>
                <td>{bug['bug_id']}</td>
                <td>{bug['title']}</td>
                <td><span class="{sev_class}">{bug['severity']}</span></td>
                <td><span class="{status_class}">{bug['status']}</span></td>
                <td>{bug['solution'] or '—'}</td>
            </tr>"""
        html += "</tbody></table></div>"

    # 结论
    conclusion = project["conclusion"] or "待填写"
    conclusion_class = "fail" if stats["fail"] > 0 else ""
    html += f"""
<!-- 测试结论 -->
<div class="section">
    <h2 class="section-title">{'四' if data['bug_list'] else '三'}、测试结论</h2>
    <div class="conclusion-box {conclusion_class}">
        <p style="font-size: 15px;">{conclusion}</p>
    </div>
</div>

<div class="footer">
    <p>本报告由 QCC 测试报告自动化平台生成 | {data['generated_at']}</p>
</div>

</div>
</body>
</html>"""

    return html


async def save_report_artifact(db: AsyncSession, project_id: int, html_content: str, user_id: int) -> dict:
    """保存报告文件并记录"""
    export_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "server", "exports")
    os.makedirs(export_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{project_id}_{timestamp}.html"
    file_path = os.path.join(export_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    file_size = os.path.getsize(file_path)

    # 记录批次
    batch = ReportBatch(
        project_id=project_id,
        batch_type="report_generate",
        source="system",
        status="completed",
        summary_json='{"type": "html_report"}',
        note=f"生成HTML测试报告",
        created_by=user_id,
    )
    db.add(batch)
    await db.flush()

    # 记录产物
    artifact = ReportArtifact(
        batch_id=batch.id,
        project_id=project_id,
        artifact_type="html_report",
        file_name=filename,
        file_path=file_path,
        file_size=file_size,
    )
    db.add(artifact)

    # 记录活动
    log = ActivityLog(
        user_id=user_id,
        action="generate",
        target_type="report",
        target_id=project_id,
        detail=f"生成HTML测试报告 {filename}",
    )
    db.add(log)
    await db.flush()

    return {
        "artifact_id": artifact.id,
        "filename": filename,
        "file_size": file_size,
        "file_path": file_path,
    }
