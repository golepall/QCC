"""模板管理业务逻辑"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.template import ReportTemplate, TestCategory, TestItem


async def get_templates(
    db: AsyncSession, category: str = "", product_type: str = ""
) -> list[ReportTemplate]:
    """获取模板列表，支持按分类和产品类型筛选"""
    stmt = select(ReportTemplate).order_by(ReportTemplate.template_code)
    if category:
        stmt = stmt.where(ReportTemplate.category == category)
    if product_type:
        stmt = stmt.where(ReportTemplate.product_type == product_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_template_detail(db: AsyncSession, template_id: int) -> dict | None:
    """获取模板详情（含分类和测试项）"""
    result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        return None

    # 获取分类
    cat_result = await db.execute(
        select(TestCategory)
        .where(TestCategory.template_id == template_id)
        .order_by(TestCategory.sort_order)
    )
    categories = list(cat_result.scalars().all())

    # 为每个分类获取测试项
    data = {
        "id": template.id,
        "template_code": template.template_code,
        "name": template.name,
        "doc_code": template.doc_code,
        "version": template.version,
        "category": template.category,
        "product_type": template.product_type,
        "sheet_config": template.sheet_config,
        "test_items": template.test_items,
        "created_at": str(template.created_at) if template.created_at else None,
        "updated_at": str(template.updated_at) if template.updated_at else None,
        "categories": [],
    }

    for cat in categories:
        item_result = await db.execute(
            select(TestItem)
            .where(TestItem.category_id == cat.id)
            .order_by(TestItem.sort_order)
        )
        items = [
            {
                "id": item.id,
                "item_no": item.item_no,
                "test_item": item.test_item,
                "test_case": item.test_case,
                "condition_desc": item.condition_desc,
                "criteria": item.criteria,
                "is_header": item.is_header,
                "sort_order": item.sort_order,
            }
            for item in item_result.scalars().all()
        ]
        data["categories"].append(
            {
                "id": cat.id,
                "category_code": cat.category_code,
                "category_name": cat.category_name,
                "sheet_name": cat.sheet_name,
                "sort_order": cat.sort_order,
                "items": items,
            }
        )

    return data
