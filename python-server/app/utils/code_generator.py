"""编号生成工具（兼容 Node.js 的编号规则）"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management import Product, Requirement, Task
from app.models.project import ReportProject, BugRecord


async def generate_product_code(db: AsyncSession) -> str:
    """生成产品编号 PRD-NNNN"""
    result = await db.execute(select(func.count()).select_from(Product))
    count = result.scalar() + 1
    return f"PRD-{count:04d}"


async def generate_project_code(db: AsyncSession) -> str:
    """生成项目编号 RPT-YYYYMMDD-NNN"""
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    result = await db.execute(
        select(func.count()).select_from(ReportProject).where(ReportProject.project_code.like(f"RPT-{today}-%"))
    )
    count = result.scalar()
    return f"RPT-{today}-{count + 1:03d}"


def generate_bug_code(count: int) -> str:
    """生成 Bug 编号 BUG-NNN"""
    return f"BUG-{count + 1:03d}"


def generate_requirement_code(req_type: str, count: int) -> str:
    """生成需求编号 BR-/UR-/DR-NNNN"""
    prefix_map = {"business": "BR", "user": "UR", "develop": "DR"}
    prefix = prefix_map.get(req_type, "REQ")
    return f"{prefix}-{count + 1:04d}"


def generate_task_code(count: int) -> str:
    """生成任务编号 T-NNNN"""
    return f"T-{count:04d}"
