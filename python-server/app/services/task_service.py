"""任务管理业务逻辑"""
from datetime import datetime, date
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management import Task, ActivityLog


def _parse_date(val):
    """将字符串转为 date 对象，无效值返回 None"""
    if not val or val == '' or val == 'null' or val == 'undefined':
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _parse_datetime(val):
    """将字符串转为 datetime 对象，无效值返回 None"""
    if not val or val == '' or val == 'null' or val == 'undefined':
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    try:
        s = str(val).replace('T', ' ')[:19]
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


async def get_tasks(
    db: AsyncSession, status: str = "", priority: str = "", project_id: int = None,
    assigned_to: int = None, keyword: str = "", page: int = 1, page_size: int = 100,
) -> dict:
    params = {}
    conditions = ["1=1"]
    if status:
        conditions.append("t.status = :status")
        params["status"] = status
    if priority:
        conditions.append("t.priority = :priority")
        params["priority"] = priority
    if project_id:
        conditions.append("t.project_id = :pid")
        params["pid"] = project_id
    if assigned_to:
        conditions.append("t.assigned_to = :uid")
        params["uid"] = assigned_to
    if keyword:
        conditions.append("(t.title LIKE :kw OR t.task_code LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    where = " AND ".join(conditions)

    count_result = await db.execute(text(f"SELECT COUNT(*) FROM task t WHERE {where}"), params)
    total = count_result.scalar()
    offset = (page - 1) * page_size

    list_sql = f"""
        SELECT t.*, u1.display_name as creator_name, u2.display_name as assignee_name,
               p.project_code, p.product_model, r.req_code
        FROM task t
        LEFT JOIN user u1 ON t.creator_id = u1.id
        LEFT JOIN user u2 ON t.assigned_to = u2.id
        LEFT JOIN report_project p ON t.project_id = p.id
        LEFT JOIN requirement r ON t.req_id = r.id
        WHERE {where}
        ORDER BY t.sort_order ASC, t.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    result = await db.execute(text(list_sql), params)
    list_data = [dict(r._mapping) for r in result.all()]
    for item in list_data:
        for key in ("deadline", "started_at", "completed_at", "created_at", "updated_at"):
            if item.get(key):
                item[key] = str(item[key])

    return {"list": list_data, "total": total, "page": page, "pageSize": page_size}


async def get_task_board(db: AsyncSession, project_id: int = None, assigned_to: int = None) -> dict:
    params = {}
    conditions = ["1=1"]
    if project_id:
        conditions.append("t.project_id = :pid")
        params["pid"] = project_id
    if assigned_to:
        conditions.append("t.assigned_to = :uid")
        params["uid"] = assigned_to
    where = " AND ".join(conditions)

    result = await db.execute(text(f"""
        SELECT t.*, u1.display_name as creator_name, u2.display_name as assignee_name,
               p.project_code, p.product_model
        FROM task t
        LEFT JOIN user u1 ON t.creator_id = u1.id
        LEFT JOIN user u2 ON t.assigned_to = u2.id
        LEFT JOIN report_project p ON t.project_id = p.id
        WHERE {where}
        ORDER BY t.sort_order ASC, t.created_at DESC
    """), params)
    all_tasks = [dict(r._mapping) for r in result.all()]

    return {
        "todo": [t for t in all_tasks if t.get("status") == "todo"],
        "doing": [t for t in all_tasks if t.get("status") == "doing"],
        "done": [t for t in all_tasks if t.get("status") == "done"],
        "closed": [t for t in all_tasks if t.get("status") == "closed"],
    }


async def get_task_stats(db: AsyncSession, assigned_to: int = None) -> dict:
    result = await db.execute(text("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END) as todo,
            SUM(CASE WHEN status = 'doing' THEN 1 ELSE 0 END) as doing,
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN priority = 'urgent' THEN 1 ELSE 0 END) as urgent,
            SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) as high
        FROM task WHERE (:uid IS NULL OR assigned_to = :uid)
    """), {"uid": assigned_to})
    return dict(result.one()._mapping)


async def get_task_detail(db: AsyncSession, task_id: int) -> dict | None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return None
    return {c.name: getattr(task, c.name) for c in task.__table__.columns} | {
        "deadline": str(task.deadline) if task.deadline else None,
        "commission_time": str(task.commission_time) if task.commission_time else None,
        "commission_deadline": str(task.commission_deadline) if task.commission_deadline else None,
        "dev_target_time": str(task.dev_target_time) if task.dev_target_time else None,
        "sample_time": str(task.sample_time) if task.sample_time else None,
        "actual_complete_time": str(task.actual_complete_time) if task.actual_complete_time else None,
        "started_at": str(task.started_at) if task.started_at else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "created_at": str(task.created_at) if task.created_at else None,
        "updated_at": str(task.updated_at) if task.updated_at else None,
    }


async def create_task(db: AsyncSession, data: dict, user_id: int) -> dict:
    title = data.get("title", "")
    if not title:
        return {"error": "任务标题不能为空"}

    count_result = await db.execute(select(func.count()).select_from(Task))
    count = count_result.scalar()
    task_code = f"T-{count + 1:04d}"

    task = Task(
        task_code=task_code, title=title, description=data.get("description", ""),
        category=data.get("category", ""), project_category=data.get("project_category", ""),
        task_type=data.get("task_type", "task"), priority=data.get("priority", "medium"),
        status=data.get("status", "todo"), project_id=data.get("project_id"),
        req_id=data.get("req_id"), parent_id=data.get("parent_id"),
        creator_id=user_id, assigned_to=data.get("assigned_to"),
        test_engineer=data.get("test_engineer", ""), client=data.get("client", ""),
        commission_time=_parse_datetime(data.get("commission_time")),
        commission_deadline=_parse_date(data.get("commission_deadline")),
        dev_target_time=_parse_date(data.get("dev_target_time")),
        sample_time=_parse_date(data.get("sample_time")),
        actual_complete_time=_parse_date(data.get("actual_complete_time")),
        progress=int(data.get("progress", 0) or 0), remark=data.get("remark", ""),
        effort_hours=float(data.get("effort_hours", 0) or 0),
        deadline=_parse_date(data.get("deadline")),
        sort_order=int(data.get("sort_order", 0) or 0),
    )
    db.add(task)
    await db.flush()
    db.add(ActivityLog(user_id=user_id, action="create", target_type="task", target_id=task.id, detail=f"创建任务 {task_code}"))
    return {"id": task.id, "task_code": task_code}


async def update_task(db: AsyncSession, task_id: int, data: dict, user_id: int) -> bool:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return False

    # 普通字段直接赋值
    simple_fields = ["title", "description", "category", "project_category", "task_type", "priority",
                     "project_id", "req_id", "assigned_to", "test_engineer", "client",
                     "progress", "remark", "effort_hours", "sort_order"]
    for field in simple_fields:
        if data.get(field) is not None:
            setattr(task, field, data[field])

    # 日期字段需要转换
    date_fields = ["commission_deadline", "dev_target_time", "sample_time", "actual_complete_time", "deadline"]
    for field in date_fields:
        if data.get(field) is not None:
            setattr(task, field, _parse_date(data[field]))
    if data.get("commission_time") is not None:
        task.commission_time = _parse_datetime(data["commission_time"])

    # 自动设置时间戳
    if data.get("status") == "doing" and not task.started_at:
        task.started_at = datetime.now()
    if data.get("status") in ("done", "closed") and not task.completed_at:
        task.completed_at = datetime.now()

    if data.get("status") is not None:
        task.status = data["status"]

    await db.flush()
    return True


async def update_task_status(db: AsyncSession, task_id: int, status: str) -> bool:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return False
    task.status = status
    if status == "doing" and not task.started_at:
        task.started_at = datetime.now()
    if status in ("done", "closed") and not task.completed_at:
        task.completed_at = datetime.now()
    await db.flush()
    return True


async def delete_task(db: AsyncSession, task_id: int) -> bool:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return False
    await db.delete(task)
    await db.flush()
    return True
