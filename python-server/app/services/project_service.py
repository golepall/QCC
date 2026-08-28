"""项目管理业务逻辑"""
from datetime import date
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import ReportTemplate, TestCategory, TestItem
from app.models.config import DeviceConfig
from app.models.project import ReportProject, TestRecord
from app.models.user import User
from app.models.management import Product, ActivityLog
from app.utils.code_generator import generate_project_code


async def _log_activity(db: AsyncSession, user_id: int | None, action: str, target_id: int, detail: str):
    db.add(ActivityLog(user_id=user_id, action=action, target_type="project", target_id=target_id, detail=detail))


async def get_projects(
    db: AsyncSession, status: str = "", template_id: str = "", tester: str = "",
    keyword: str = "", product_id: str = "", parent_id: str = "",
    page: int = 1, page_size: int = 20,
) -> dict:
    """获取项目列表"""
    params = {}
    conditions = ["1=1"]

    if status:
        conditions.append("p.status = :status")
        params["status"] = status
    if template_id:
        conditions.append("p.template_id = :template_id")
        params["template_id"] = int(template_id)
    if tester:
        conditions.append("p.tester = :tester")
        params["tester"] = tester
    if product_id:
        conditions.append("p.product_id = :product_id")
        params["product_id"] = int(product_id)
    if parent_id == "root":
        conditions.append("p.parent_id IS NULL")
    elif parent_id:
        conditions.append("p.parent_id = :parent_id")
        params["parent_id"] = int(parent_id)
    if keyword:
        conditions.append("(p.product_model LIKE :kw OR p.product_name LIKE :kw OR p.project_code LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions)

    count_sql = f"SELECT COUNT(*) as cnt FROM report_project p WHERE {where}"
    result = await db.execute(text(count_sql), params)
    total = result.scalar()

    offset = (page - 1) * page_size
    list_sql = f"""
        SELECT p.*, t.name as template_name, t.template_code,
               u.display_name as creator_name,
               pr.name as product_name_ref,
               pr.line_name as product_line_name,
               parent.project_code as parent_project_code
        FROM report_project p
        LEFT JOIN report_template t ON p.template_id = t.id
        LEFT JOIN user u ON p.created_by = u.id
        LEFT JOIN product pr ON p.product_id = pr.id
        LEFT JOIN report_project parent ON p.parent_id = parent.id
        WHERE {where}
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset

    result = await db.execute(text(list_sql), params)
    rows = result.fetchall()

    list_data = []
    for row in rows:
        # 每个项目的测试记录统计
        stats_result = await db.execute(
            select(
                func.count().label("total"),
                func.coalesce(func.sum(text("CASE WHEN result = 'Pass' THEN 1 ELSE 0 END")), 0).label("pass"),
                func.coalesce(func.sum(text("CASE WHEN result = 'Fail' THEN 1 ELSE 0 END")), 0).label("fail"),
                func.coalesce(func.sum(text("CASE WHEN result = 'NA' THEN 1 ELSE 0 END")), 0).label("na"),
                func.coalesce(func.sum(text("CASE WHEN result = 'Blocked' THEN 1 ELSE 0 END")), 0).label("blocked"),
                func.coalesce(func.sum(text("CASE WHEN result = 'Error' THEN 1 ELSE 0 END")), 0).label("error"),
                func.coalesce(func.sum(text("CASE WHEN result = '' OR result IS NULL OR result = 'NotTested' THEN 1 ELSE 0 END")), 0).label("pending"),
            ).select_from(TestRecord).where(TestRecord.project_id == row.id)
        )
        stats = stats_result.one()

        item = {
            "id": row.id, "project_code": row.project_code,
            "template_id": row.template_id, "template_name": row.template_name, "template_code": row.template_code,
            "product_model": row.product_model, "product_name": row.product_name,
            "tester": row.tester, "reviewer": row.reviewer, "approver": row.approver,
            "test_type": row.test_type, "status": row.status, "conclusion": row.conclusion,
            "config_id": row.config_id, "created_by": row.created_by, "creator_name": row.creator_name,
            "product_id": row.product_id, "product_name_ref": row.product_name_ref,
            "product_line_name": row.product_line_name,
            "parent_id": row.parent_id, "parent_project_code": row.parent_project_code,
            "project_type": row.project_type, "view_mode": row.view_mode,
            "start_date": str(row.start_date) if row.start_date else None,
            "end_date": str(row.end_date) if row.end_date else None,
            "created_at": str(row.created_at) if row.created_at else None,
            "updated_at": str(row.updated_at) if row.updated_at else None,
            "stats": {
                "total": stats.total,
                "pass": getattr(stats, "pass", 0),
                "fail": getattr(stats, "fail", 0),
                "na": getattr(stats, "na", 0),
                "blocked": getattr(stats, "blocked", 0),
                "error": getattr(stats, "error", 0),
                "pending": getattr(stats, "pending", 0),
            },
        }
        list_data.append(item)

    return {"list": list_data, "total": total, "page": page, "pageSize": page_size}


async def get_project_detail(db: AsyncSession, project_id: int) -> dict | None:
    """获取项目详情"""
    result = await db.execute(
        select(ReportProject).where(ReportProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        return None

    # 关联模板
    tpl_result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == project.template_id))
    template = tpl_result.scalar_one_or_none()

    # 关联产品
    if project.product_id:
        pr_result = await db.execute(select(Product).where(Product.id == project.product_id))
        product = pr_result.scalar_one_or_none()
    else:
        product = None

    # 父项目
    if project.parent_id:
        parent_result = await db.execute(select(ReportProject).where(ReportProject.id == project.parent_id))
        parent = parent_result.scalar_one_or_none()
    else:
        parent = None

    # 设备配置
    config = None
    if project.config_id:
        cfg_result = await db.execute(select(DeviceConfig).where(DeviceConfig.id == project.config_id))
        config = cfg_result.scalar_one_or_none()

    return {
        "id": project.id, "project_code": project.project_code,
        "template_id": project.template_id,
        "template_name": template.name if template else "",
        "template_code": template.template_code if template else "",
        "doc_code": template.doc_code if template else "",
        "product_model": project.product_model, "product_name": project.product_name,
        "tester": project.tester, "reviewer": project.reviewer, "approver": project.approver,
        "test_type": project.test_type, "status": project.status, "conclusion": project.conclusion,
        "config_id": project.config_id, "created_by": project.created_by,
        "product_id": project.product_id,
        "product_name_ref": product.name if product else "",
        "product_line_name": product.line_name if product else "",
        "parent_id": project.parent_id,
        "parent_project_code": parent.project_code if parent else "",
        "project_type": project.project_type, "view_mode": project.view_mode,
        "start_date": str(project.start_date) if project.start_date else None,
        "end_date": str(project.end_date) if project.end_date else None,
        "created_at": str(project.created_at) if project.created_at else None,
        "updated_at": str(project.updated_at) if project.updated_at else None,
        "config": {
            "id": config.id, "config_name": config.config_name,
        } if config else None,
    }


async def create_project(db: AsyncSession, data: dict, user_id: int) -> dict:
    """创建项目并初始化测试记录"""
    required = ["template_id", "product_model", "product_name", "tester"]
    for field in required:
        if not data.get(field):
            return {"error": "缺少必填字段"}

    project_code = await generate_project_code(db)
    project = ReportProject(
        project_code=project_code,
        template_id=data["template_id"],
        product_model=data["product_model"],
        product_name=data["product_name"],
        tester=data["tester"],
        reviewer=data.get("reviewer", ""),
        approver=data.get("approver", ""),
        test_type=data.get("test_type", "new"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        config_id=data.get("config_id"),
        created_by=user_id,
        product_id=data.get("product_id"),
        parent_id=data.get("parent_id"),
        project_type=data.get("project_type", "project"),
        view_mode=data.get("view_mode", "list"),
    )
    db.add(project)
    await db.flush()

    # 初始化测试记录
    cat_result = await db.execute(
        select(TestCategory).where(TestCategory.template_id == data["template_id"]).order_by(TestCategory.sort_order)
    )
    for cat in cat_result.scalars().all():
        item_result = await db.execute(
            select(TestItem).where(TestItem.category_id == cat.id).order_by(TestItem.sort_order)
        )
        for item in item_result.scalars().all():
            if not item.is_header:
                db.add(TestRecord(project_id=project.id, item_id=item.id, result="", comment=""))

    await _log_activity(db, user_id, "create", project.id, f"创建项目 {project_code}")
    return {"id": project.id, "project_code": project_code}


async def update_project(db: AsyncSession, project_id: int, data: dict, user_id: int, user_role: str) -> dict | None:
    """更新项目。返回 None 表示项目不存在，{'error': '权限不足'} 表示无权限"""
    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return None

    if user_role != "admin" and project.created_by and project.created_by != user_id:
        return {"error": "权限不足，只能编辑自己创建的项目"}

    fields = ["product_model", "product_name", "tester", "reviewer", "approver",
              "test_type", "start_date", "end_date", "status", "conclusion",
              "config_id", "remark", "product_id", "parent_id", "project_type", "view_mode"]
    for field in fields:
        if data.get(field) is not None:
            setattr(project, field, data[field])

    await db.flush()
    await _log_activity(db, user_id, "update", project_id, f"更新项目 {project.project_code}")
    return {"ok": True}


async def delete_project(db: AsyncSession, project_id: int, user_id: int, user_role: str) -> dict:
    """删除项目及关联数据"""
    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return {"error": "项目不存在"}

    if user_role != "admin" and project.created_by and project.created_by != user_id:
        return {"error": "权限不足，只能删除自己创建的项目"}

    code = project.project_code
    await db.execute(text("DELETE FROM test_record WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM bug_record WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM product_image WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM heat_test_data WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM performance_data WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM report_project WHERE id = :pid"), {"pid": project_id})

    await _log_activity(db, user_id, "delete", project_id, f"删除项目 {code}")
    return {"ok": True}


async def update_project_status(db: AsyncSession, project_id: int, status: str, conclusion: str | None, user_id: int) -> dict | None:
    """快速更新项目状态"""
    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return None

    project.status = status
    if conclusion is not None:
        project.conclusion = conclusion

    await db.flush()
    await _log_activity(db, user_id, "status_change", project_id, f"项目 {project.project_code} 状态变更为 {status}")
    return {"ok": True}


async def get_project_summary(db: AsyncSession, project_id: int) -> dict | None:
    """获取项目摘要统计"""
    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return None

    # 按分类统计
    cat_sql = text("""
        SELECT tc.id, tc.category_name, tc.sheet_name,
            COUNT(tr.id) as total,
            SUM(CASE WHEN tr.result = 'Pass' THEN 1 ELSE 0 END) as pass,
            SUM(CASE WHEN tr.result = 'Fail' THEN 1 ELSE 0 END) as fail,
            SUM(CASE WHEN tr.result = 'NA' THEN 1 ELSE 0 END) as na,
            SUM(CASE WHEN tr.result = 'Blocked' THEN 1 ELSE 0 END) as blocked,
            SUM(CASE WHEN tr.result = 'Manual' THEN 1 ELSE 0 END) as manual,
            SUM(CASE WHEN tr.result = 'Error' THEN 1 ELSE 0 END) as error,
            SUM(CASE WHEN tr.result = '' OR tr.result IS NULL OR tr.result = 'NotTested' THEN 1 ELSE 0 END) as pending
        FROM test_category tc
        LEFT JOIN test_item ti ON ti.category_id = tc.id AND ti.is_header = 0
        LEFT JOIN test_record tr ON tr.item_id = ti.id AND tr.project_id = :pid
        WHERE tc.template_id = :tid
        GROUP BY tc.id
        ORDER BY tc.sort_order
    """)
    cat_result = await db.execute(cat_sql, {"pid": project_id, "tid": project.template_id})
    category_stats = [dict(r._mapping) for r in cat_result.all()]

    # Bug 统计
    from app.models.project import BugRecord
    bug_result = await db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(text("CASE WHEN status = 'open' THEN 1 ELSE 0 END")), 0),
        ).select_from(BugRecord).where(BugRecord.project_id == project_id)
    )
    bug_row = bug_result.one()

    return {"categoryStats": category_stats, "bugStats": {"total": bug_row.total, "open_count": bug_row[1]}}
