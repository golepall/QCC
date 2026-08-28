"""产品管理业务逻辑"""
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management import Product
from app.models.user import User
from app.models.project import ReportProject
from app.models.management import Requirement, Task, ActivityLog
from app.utils.code_generator import generate_product_code


async def _log_activity(db: AsyncSession, user_id: int | None, action: str, target_type: str, target_id: int, detail: str):
    """记录操作日志"""
    log = ActivityLog(user_id=user_id, action=action, target_type=target_type, target_id=target_id, detail=detail)
    db.add(log)


async def get_products(
    db: AsyncSession,
    keyword: str = "",
    line_name: str = "",
    status: str = "",
    owner_id: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """获取产品列表（含关联统计）"""
    # SQLite 不支持 func.count(distinct)，用子查询替代
    offset = (page - 1) * page_size
    params = {}
    conditions = ["1=1"]

    if line_name:
        conditions.append("p.line_name = :line_name")
        params["line_name"] = line_name
    if status:
        conditions.append("p.status = :status")
        params["status"] = status
    if owner_id:
        conditions.append("p.owner_id = :owner_id")
        params["owner_id"] = int(owner_id)
    if keyword:
        conditions.append("(p.product_code LIKE :kw OR p.name LIKE :kw OR p.description LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions)

    # 总数
    count_sql = f"SELECT COUNT(*) as cnt FROM product p WHERE {where}"
    total_result = await db.execute(text(count_sql), params)
    total = total_result.scalar()

    # 列表（关联统计用子查询避免多次 count 查询影响性能）
    list_sql = f"""
        SELECT p.*,
               u.display_name as owner_name,
               (SELECT COUNT(*) FROM report_project WHERE product_id = p.id) as project_count,
               (SELECT COUNT(*) FROM requirement r
                INNER JOIN report_project rp ON r.project_id = rp.id
                WHERE rp.product_id = p.id) as requirement_count,
               (SELECT COUNT(*) FROM task t
                INNER JOIN report_project rp ON t.project_id = rp.id
                WHERE rp.product_id = p.id) as task_count
        FROM product p
        LEFT JOIN user u ON p.owner_id = u.id
        WHERE {where}
        ORDER BY p.updated_at DESC, p.id DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset

    result = await db.execute(text(list_sql), params)
    rows = result.fetchall()

    list_data = []
    for row in rows:
        list_data.append({
            "id": row.id,
            "product_code": row.product_code,
            "name": row.name,
            "line_name": row.line_name,
            "owner_id": row.owner_id,
            "owner_name": row.owner_name,
            "status": row.status,
            "description": row.description,
            "created_by": row.created_by,
            "created_at": str(row.created_at) if row.created_at else None,
            "updated_at": str(row.updated_at) if row.updated_at else None,
            "project_count": row.project_count,
            "requirement_count": row.requirement_count,
            "task_count": row.task_count,
        })

    return {"list": list_data, "total": total, "page": page, "pageSize": page_size}


async def get_product_stats(db: AsyncSession) -> dict:
    """获取产品统计数据"""
    total_result = await db.execute(select(func.count()).select_from(Product))
    total = total_result.scalar()

    status_result = await db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(text("CASE WHEN status = 'planning' THEN 1 ELSE 0 END")), 0).label("planning"),
            func.coalesce(func.sum(text("CASE WHEN status = 'active' THEN 1 ELSE 0 END")), 0).label("active"),
            func.coalesce(func.sum(text("CASE WHEN status = 'maintaining' THEN 1 ELSE 0 END")), 0).label("maintaining"),
            func.coalesce(func.sum(text("CASE WHEN status = 'archived' THEN 1 ELSE 0 END")), 0).label("archived"),
        ).select_from(Product)
    )
    row = status_result.one()

    line_result = await db.execute(
        select(
            func.coalesce(Product.line_name, "未分组").label("line_name"),
            func.count().label("count"),
        )
        .group_by(text("CASE WHEN COALESCE(line_name, '') = '' THEN '未分组' ELSE line_name END"))
        .order_by(text("count DESC, line_name ASC"))
    )
    lines = [{"line_name": r.line_name, "count": r.count} for r in line_result.all()]

    return {
        "total": total,
        "planning": row.planning,
        "active": row.active,
        "maintaining": row.maintaining,
        "archived": row.archived,
        "lines": lines,
    }


async def get_product_owners(db: AsyncSession) -> list[dict]:
    """获取可选负责人列表"""
    result = await db.execute(
        select(User.id, User.username, User.display_name).order_by(User.display_name, User.username)
    )
    return [{"id": r.id, "username": r.username, "display_name": r.display_name} for r in result.all()]


async def get_product_detail(db: AsyncSession, product_id: int) -> dict | None:
    """获取产品详情（含关联项目）"""
    result = await db.execute(
        select(Product, User.display_name.label("owner_name"))
        .outerjoin(User, Product.owner_id == User.id)
        .where(Product.id == product_id)
    )
    row = result.one_or_none()
    if row is None:
        return None

    product, owner_name = row

    proj_result = await db.execute(
        select(ReportProject.id, ReportProject.project_code, ReportProject.product_model,
               ReportProject.product_name, ReportProject.status, ReportProject.project_type,
               ReportProject.view_mode, ReportProject.parent_id)
        .where(ReportProject.product_id == product_id)
        .order_by(ReportProject.created_at.desc())
    )
    projects = [dict(r._mapping) for r in proj_result.all()]

    return {
        "id": product.id,
        "product_code": product.product_code,
        "name": product.name,
        "line_name": product.line_name,
        "owner_id": product.owner_id,
        "owner_name": owner_name,
        "status": product.status,
        "description": product.description,
        "created_by": product.created_by,
        "created_at": str(product.created_at) if product.created_at else None,
        "updated_at": str(product.updated_at) if product.updated_at else None,
        "projects": projects,
    }


async def create_product(
    db: AsyncSession, name: str, line_name: str, owner_id: int | None,
    status: str, description: str, user_id: int | None,
) -> dict:
    """创建产品"""
    product_code = await generate_product_code(db)
    product = Product(
        product_code=product_code,
        name=name,
        line_name=line_name or "",
        owner_id=owner_id or None,
        status=status or "planning",
        description=description or "",
        created_by=user_id,
    )
    db.add(product)
    await db.flush()
    await _log_activity(db, user_id, "create", "product", product.id, f"创建产品 {product_code}")
    return {"id": product.id, "product_code": product_code}


async def update_product(
    db: AsyncSession, product_id: int, name: str, line_name: str,
    owner_id: int | None, status: str, description: str, user_id: int | None,
) -> bool:
    """更新产品"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        return False

    if name is not None:
        product.name = name
    if line_name is not None:
        product.line_name = line_name
    if owner_id is not None:
        product.owner_id = owner_id
    if status is not None:
        product.status = status
    if description is not None:
        product.description = description

    await db.flush()
    await _log_activity(db, user_id, "update", "product", product_id, f"更新产品 {product.product_code}")
    return True


async def delete_product(db: AsyncSession, product_id: int, user_id: int | None) -> tuple[bool, str]:
    """删除产品。返回 (成功, 错误信息)"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        return False, "产品不存在"

    proj_count = await db.execute(
        select(func.count()).select_from(ReportProject).where(ReportProject.product_id == product_id)
    )
    if proj_count.scalar() > 0:
        return False, "该产品下仍有关联项目，不能删除"

    await _log_activity(db, user_id, "delete", "product", product_id, f"删除产品 {product.product_code}")
    await db.delete(product)
    await db.flush()
    return True, ""
