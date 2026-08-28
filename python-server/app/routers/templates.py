"""模板管理路由（/api/templates）"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.services import template_service

router = APIRouter(prefix="/api/templates", tags=["模板管理"])


@router.get("")
async def list_templates(
    category: str = Query("", description="分类筛选"),
    product_type: str = Query("", description="产品类型筛选"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取模板列表"""
    templates = await template_service.get_templates(
        db, category=category, product_type=product_type
    )
    data = [
        {
            "id": t.id,
            "template_code": t.template_code,
            "name": t.name,
            "doc_code": t.doc_code,
            "version": t.version,
            "category": t.category,
            "product_type": t.product_type,
            "sheet_config": t.sheet_config,
            "test_items": t.test_items,
            "created_at": str(t.created_at) if t.created_at else None,
            "updated_at": str(t.updated_at) if t.updated_at else None,
        }
        for t in templates
    ]
    return {"code": 200, "message": "success", "data": data}


@router.get("/{template_id}")
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取模板详情（含分类和测试项）"""
    result = await template_service.get_template_detail(db, template_id)
    if result is None:
        return {"code": 404, "message": "模板不存在", "data": None}
    return {"code": 200, "message": "success", "data": result}
