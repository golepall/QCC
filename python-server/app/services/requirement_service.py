"""需求管理业务逻辑"""
from datetime import date
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management import Requirement, RequirementChange, ActivityLog
from app.models.user import User


def _req_row(r: Requirement) -> dict:
    return {c.name: getattr(r, c.name) for c in r.__table__.columns} | {
        "deadline": str(r.deadline) if r.deadline else None,
        "created_at": str(r.created_at) if r.created_at else None,
        "updated_at": str(r.updated_at) if r.updated_at else None,
    }


async def get_requirements(
    db: AsyncSession, status: str = "", req_type: str = "", priority: str = "",
    keyword: str = "", project_id: int = None, assigned_to: int = None,
    page: int = 1, page_size: int = 50,
) -> dict:
    params = {}
    conditions = ["1=1"]
    if status:
        conditions.append("r.status = :status")
        params["status"] = status
    if req_type:
        conditions.append("r.req_type = :type")
        params["type"] = req_type
    if priority:
        conditions.append("r.priority = :priority")
        params["priority"] = priority
    if project_id:
        conditions.append("r.project_id = :pid")
        params["pid"] = project_id
    if assigned_to:
        conditions.append("r.assigned_to = :uid")
        params["uid"] = assigned_to
    if keyword:
        conditions.append("(r.title LIKE :kw OR r.req_code LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    where = " AND ".join(conditions)

    count_result = await db.execute(text(f"SELECT COUNT(*) FROM requirement r WHERE {where}"), params)
    total = count_result.scalar()

    offset = (page - 1) * page_size
    list_sql = f"""
        SELECT r.*, u1.display_name as creator_name, u2.display_name as assignee_name,
                p.project_code, p.product_model
        FROM requirement r
        LEFT JOIN user u1 ON r.creator_id = u1.id
        LEFT JOIN user u2 ON r.assigned_to = u2.id
        LEFT JOIN report_project p ON r.project_id = p.id
        WHERE {where}
        ORDER BY r.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    result = await db.execute(text(list_sql), params)
    list_data = [dict(r._mapping) for r in result.all()]
    for item in list_data:
        for key in ("deadline", "created_at", "updated_at"):
            if item.get(key):
                item[key] = str(item[key])

    return {"list": list_data, "total": total, "page": page, "pageSize": page_size}


async def get_req_stats(db: AsyncSession, assigned_to: int = None) -> dict:
    result = await db.execute(text("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) as draft,
            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN status = 'developing' THEN 1 ELSE 0 END) as developing,
            SUM(CASE WHEN status = 'testing' THEN 1 ELSE 0 END) as testing,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN req_type = 'business' THEN 1 ELSE 0 END) as business,
            SUM(CASE WHEN req_type = 'user' THEN 1 ELSE 0 END) as user_req,
            SUM(CASE WHEN req_type = 'develop' THEN 1 ELSE 0 END) as develop
        FROM requirement WHERE (:uid IS NULL OR assigned_to = :uid)
    """), {"uid": assigned_to})
    return dict(result.one()._mapping)


async def get_assignable_users(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(User.id, User.username, User.display_name).order_by(User.display_name))
    return [{"id": r.id, "username": r.username, "display_name": r.display_name} for r in result.all()]


async def get_requirement_detail(db: AsyncSession, req_id: int) -> dict | None:
    result = await db.execute(text("""
        SELECT r.*, u1.display_name as creator_name, u2.display_name as assignee_name,
                p.project_code, p.product_model
        FROM requirement r
        LEFT JOIN user u1 ON r.creator_id = u1.id
        LEFT JOIN user u2 ON r.assigned_to = u2.id
        LEFT JOIN report_project p ON r.project_id = p.id
        WHERE r.id = :rid
    """), {"rid": req_id})
    row = result.one_or_none()
    if row is None:
        return None
    data = dict(row._mapping)
    for key in ("deadline", "created_at", "updated_at"):
        if data.get(key):
            data[key] = str(data[key])

    # 变更历史
    changes_result = await db.execute(
        select(RequirementChange).where(RequirementChange.req_id == req_id).order_by(RequirementChange.created_at.desc())
    )
    data["changes"] = [
        {"field_name": c.field_name, "old_value": c.old_value, "new_value": c.new_value,
         "created_at": str(c.created_at) if c.created_at else None}
        for c in changes_result.scalars().all()
    ]
    return data


async def create_requirement(db: AsyncSession, data: dict, user_id: int) -> dict:
    title = data.get("title", "")
    if not title:
        return {"error": "需求标题不能为空"}

    req_type = data.get("req_type", "business")
    prefix = {"business": "BR", "user": "UR", "develop": "DR"}.get(req_type, "REQ")
    count_result = await db.execute(
        select(func.count()).select_from(Requirement).where(Requirement.req_code.like(f"{prefix}-%"))
    )
    count = count_result.scalar()
    req_code = f"{prefix}-{count + 1:04d}"

    req = Requirement(
        req_code=req_code, req_type=req_type, title=title,
        description=data.get("description", ""), acceptance=data.get("acceptance", ""),
        priority=data.get("priority", "medium"), status=data.get("status", "draft"),
        project_id=data.get("project_id"), parent_id=data.get("parent_id"),
        creator_id=user_id, assigned_to=data.get("assigned_to"),
        effort_hours=data.get("effort_hours", 0), deadline=data.get("deadline"),
    )
    db.add(req)
    await db.flush()
    db.add(ActivityLog(user_id=user_id, action="create", target_type="requirement", target_id=req.id, detail=f"创建需求 {req_code}"))
    return {"id": req.id, "req_code": req_code}


async def update_requirement(db: AsyncSession, req_id: int, data: dict, user_id: int) -> bool:
    result = await db.execute(select(Requirement).where(Requirement.id == req_id))
    req = result.scalar_one_or_none()
    if req is None:
        return False

    fields = ["title", "description", "acceptance", "priority", "status", "project_id",
              "assigned_to", "effort_hours", "deadline", "req_type"]
    for field in fields:
        if data.get(field) is not None:
            old_val = getattr(req, field)
            setattr(req, field, data[field])
            if str(old_val) != str(data[field]):
                db.add(RequirementChange(req_id=req_id, field_name=field,
                                         old_value=str(old_val), new_value=str(data[field]),
                                         operator_id=user_id))
    await db.flush()
    return True


async def delete_requirement(db: AsyncSession, req_id: int) -> bool:
    result = await db.execute(select(Requirement).where(Requirement.id == req_id))
    req = result.scalar_one_or_none()
    if req is None:
        return False
    await db.execute(text("DELETE FROM requirement_change WHERE req_id = :rid"), {"rid": req_id})
    await db.delete(req)
    await db.flush()
    return True
