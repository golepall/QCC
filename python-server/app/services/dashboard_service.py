"""仪表盘与工作区业务逻辑"""
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ReportProject, BugRecord
from app.models.template import ReportTemplate
from app.models.management import Product, Task, Requirement, ActivityLog, Notification
from app.models.user import User


async def get_dashboard_data(db: AsyncSession) -> dict:
    """全局仪表盘数据"""
    total_projects = (await db.execute(select(func.count()).select_from(ReportProject))).scalar()
    active_projects = (await db.execute(
        select(func.count()).select_from(ReportProject)
        .where(ReportProject.status.in_(("draft", "testing")))
    )).scalar()
    total_templates = (await db.execute(select(func.count()).select_from(ReportTemplate))).scalar()
    total_products = (await db.execute(select(func.count()).select_from(Product))).scalar()
    total_bugs = (await db.execute(select(func.count()).select_from(BugRecord))).scalar()
    open_bugs = (await db.execute(
        select(func.count()).select_from(BugRecord).where(BugRecord.status == "open")
    )).scalar()

    total_reqs = total_tasks = active_reqs = completed_reqs = doing_tasks = overdue_tasks = 0
    try:
        total_reqs = (await db.execute(select(func.count()).select_from(Requirement))).scalar()
        active_reqs = (await db.execute(
            select(func.count()).select_from(Requirement)
            .where(Requirement.status.in_(("active", "developing", "testing")))
        )).scalar()
        completed_reqs = (await db.execute(
            select(func.count()).select_from(Requirement).where(Requirement.status == "completed")
        )).scalar()
    except Exception:
        pass

    try:
        total_tasks = (await db.execute(select(func.count()).select_from(Task))).scalar()
        doing_tasks = (await db.execute(
            select(func.count()).select_from(Task).where(Task.status == "doing")
        )).scalar()
        overdue_tasks = (await db.execute(
            select(func.count()).select_from(Task)
            .where(text("deadline < date('now') AND status NOT IN ('done','closed')"))
        )).scalar()
    except Exception:
        pass

    recent_projects_result = await db.execute(
        select(ReportProject).order_by(ReportProject.created_at.desc()).limit(10)
    )
    recent_projects = []
    for p in recent_projects_result.scalars().all():
        tpl = await db.execute(select(ReportTemplate).where(ReportTemplate.id == p.template_id))
        template = tpl.scalar_one_or_none()
        recent_projects.append({
            "id": p.id, "project_code": p.project_code, "product_model": p.product_model,
            "product_name": p.product_name, "tester": p.tester, "status": p.status,
            "created_at": str(p.created_at) if p.created_at else None,
            "template_name": template.name if template else "",
        })

    activities_result = await db.execute(
        select(ActivityLog, User.display_name)
        .outerjoin(User, ActivityLog.user_id == User.id)
        .order_by(ActivityLog.created_at.desc()).limit(10)
    )

    return {
        "totalProjects": total_projects, "activeProjects": active_projects,
        "totalTemplates": total_templates, "totalProducts": total_products,
        "totalBugs": total_bugs, "openBugs": open_bugs,
        "totalReqs": total_reqs, "activeReqs": active_reqs, "completedReqs": completed_reqs,
        "totalTasks": total_tasks, "doingTasks": doing_tasks, "overdueTasks": overdue_tasks,
        "recentProjects": recent_projects,
        "recentActivities": [
            {"id": al.id, "action": al.action, "detail": al.detail,
             "user_name": un, "created_at": str(al.created_at) if al.created_at else None}
            for al, un in activities_result.all()
        ],
    }


async def get_workspace_data(db: AsyncSession, user_id: int) -> dict:
    """个人工作台数据"""
    my_tasks = await db.execute(
        select(Task).where(Task.assigned_to == user_id)
        .order_by(
            text("CASE status WHEN 'doing' THEN 1 WHEN 'todo' THEN 2 WHEN 'done' THEN 3 ELSE 4 END"),
            Task.deadline.asc().nullslast(), Task.updated_at.desc()
        ).limit(20)
    )
    task_list = [_task_row(t) for t in my_tasks.scalars().all()]

    my_reqs = await db.execute(
        select(Requirement).where(Requirement.assigned_to == user_id)
        .order_by(Requirement.updated_at.desc()).limit(20)
    )
    req_list = [_req_row(r) for r in my_reqs.scalars().all()]

    task_stats = {"todo": 0, "doing": 0, "done": 0}
    ts_result = await db.execute(
        select(Task.status, func.count()).where(Task.assigned_to == user_id).group_by(Task.status)
    )
    for status, cnt in ts_result.all():
        task_stats[status] = cnt

    req_stats = {"active": 0}
    rs_result = await db.execute(
        select(func.count()).select_from(Requirement)
        .where(and_(Requirement.assigned_to == user_id, Requirement.status.in_(("active", "developing", "testing"))))
    )
    req_stats["active"] = rs_result.scalar()

    noti_result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc()).limit(10)
    )

    return {
        "myTasks": task_list, "myReqs": req_list,
        "taskStats": task_stats, "reqStats": req_stats,
        "notifications": [
            {c.name: getattr(n, c.name) for c in n.__table__.columns} |
            {"created_at": str(n.created_at) if n.created_at else None}
            for n in noti_result.scalars().all()
        ],
        "activities": [],
    }


def _task_row(t):
    return {c.name: getattr(t, c.name) for c in t.__table__.columns} | {
        "deadline": str(t.deadline) if t.deadline else None,
        "started_at": str(t.started_at) if t.started_at else None,
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


def _req_row(r):
    return {c.name: getattr(r, c.name) for c in r.__table__.columns} | {
        "deadline": str(r.deadline) if r.deadline else None,
        "created_at": str(r.created_at) if r.created_at else None,
        "updated_at": str(r.updated_at) if r.updated_at else None,
    }
