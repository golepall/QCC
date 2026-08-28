"""Bug 管理业务逻辑"""
from datetime import date
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import BugRecord, ReportProject


async def get_all_bugs(
    db: AsyncSession, status: str = "", severity: str = "", keyword: str = "",
    page: int = 1, page_size: int = 50,
) -> dict:
    """全局 Bug 列表（跨项目）"""
    conditions = ["1=1"]
    params = {}

    if status:
        conditions.append("b.status = :status")
        params["status"] = status
    if severity:
        conditions.append("b.severity = :severity")
        params["severity"] = severity
    if keyword:
        conditions.append("(b.title LIKE :kw OR b.bug_id LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions)

    count_sql = f"SELECT COUNT(*) as cnt FROM bug_record b WHERE {where}"
    result = await db.execute(text(count_sql), params)
    total = result.scalar()

    offset = (page - 1) * page_size
    list_sql = f"""
        SELECT b.*, p.project_code, p.product_model, p.product_name
        FROM bug_record b
        LEFT JOIN report_project p ON b.project_id = p.id
        WHERE {where}
        ORDER BY b.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    result = await db.execute(text(list_sql), params)
    list_data = [dict(r._mapping) for r in result.all()]
    for item in list_data:
        for key in ("open_date", "close_date", "created_at", "updated_at"):
            if item.get(key):
                item[key] = str(item[key])

    return {"list": list_data, "total": total, "page": page, "pageSize": page_size}


async def get_project_bugs(
    db: AsyncSession, project_id: int, status: str = "", severity: str = ""
) -> list[dict]:
    """获取项目 Bug 列表"""
    stmt = select(BugRecord).where(BugRecord.project_id == project_id)
    if status:
        stmt = stmt.where(BugRecord.status == status)
    if severity:
        stmt = stmt.where(BugRecord.severity == severity)
    stmt = stmt.order_by(BugRecord.created_at.desc())
    result = await db.execute(stmt)
    bugs = result.scalars().all()
    return [
        {c.name: getattr(b, c.name) for c in b.__table__.columns} | {
            "open_date": str(b.open_date) if b.open_date else None,
            "close_date": str(b.close_date) if b.close_date else None,
            "created_at": str(b.created_at) if b.created_at else None,
            "updated_at": str(b.updated_at) if b.updated_at else None,
        }
        for b in bugs
    ]


async def get_bug_stats(db: AsyncSession, project_id: int) -> dict:
    """Bug 统计"""
    result = await db.execute(text("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high,
            SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) as medium,
            SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END) as low
        FROM bug_record WHERE project_id = :pid
    """), {"pid": project_id})
    return dict(result.one()._mapping)


async def create_bug(db: AsyncSession, project_id: int, data: dict) -> dict:
    """创建 Bug"""
    title = data.get("title", "") or data.get("bug_description", "")
    if not title:
        return {"error": "Bug标题不能为空"}

    # 获取项目编码，用于Bug ID前缀
    proj_result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj_result.scalar_one_or_none()
    project_code = project.project_code if project else f"P{project_id}"

    count_result = await db.execute(
        select(func.count()).select_from(BugRecord).where(BugRecord.project_id == project_id)
    )
    count = count_result.scalar()
    # Bug ID格式：[项目编码]-BUG-[序号]
    bug_id = f"{project_code}-BUG-{count + 1:03d}"

    bug = BugRecord(
        project_id=project_id,
        bug_id=bug_id,
        category=data.get("category", ""),
        title=title,
        description=data.get("description", "") or data.get("reproduce_steps", ""),
        severity=data.get("severity", "medium"),
        mb_info=data.get("mb_info", ""),
        bios_info=data.get("bios_info", ""),
        sys_info=data.get("sys_info", ""),
        reproduce_rate=data.get("reproduce_rate", ""),
        test_env=data.get("test_env", ""),
        open_date=data.get("open_date") or date.today(),
        owner=data.get("owner", ""),
        tester=data.get("tester", ""),
    )
    db.add(bug)
    await db.flush()
    return {"id": bug.id, "bug_id": bug_id}


async def get_bug_detail(db: AsyncSession, project_id: int, bug_id: int) -> BugRecord | None:
    """获取 Bug 详情"""
    result = await db.execute(
        select(BugRecord).where(BugRecord.id == bug_id, BugRecord.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def update_bug(db: AsyncSession, project_id: int, bug_record_id: int, data: dict) -> bool:
    """更新 Bug"""
    result = await db.execute(
        select(BugRecord).where(BugRecord.id == bug_record_id, BugRecord.project_id == project_id)
    )
    bug = result.scalar_one_or_none()
    if bug is None:
        return False

    for field in ["category", "title", "description", "severity", "mb_info", "bios_info", "sys_info",
                  "reproduce_rate", "test_env", "root_cause", "solution", "owner", "tester", "comment", "remark"]:
        if data.get(field) is not None:
            setattr(bug, field, data[field])
    await db.flush()
    return True


async def update_bug_status(db: AsyncSession, project_id: int, bug_record_id: int, status: str, close_date_val: str | None) -> bool:
    """更新 Bug 状态"""
    result = await db.execute(
        select(BugRecord).where(BugRecord.id == bug_record_id, BugRecord.project_id == project_id)
    )
    bug = result.scalar_one_or_none()
    if bug is None:
        return False

    bug.status = status
    if status == "closed":
        bug.close_date = close_date_val or str(date.today())
    elif close_date_val:
        bug.close_date = close_date_val

    await db.flush()
    return True
