"""产品管理路由（/api/products）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services import product_service

router = APIRouter(prefix="/api/products", tags=["产品管理"])


@router.get("")
async def list_products(
    keyword: str = Query(""),
    line_name: str = Query(""),
    status: str = Query(""),
    owner_id: str = Query(""),
    page: int = Query(1),
    pageSize: int = Query(50),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await product_service.get_products(db, keyword, line_name, status, owner_id, page, pageSize)
    return {"code": 200, "message": "success", "data": data}


@router.get("/stats")
async def product_stats(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await product_service.get_product_stats(db)
    return {"code": 200, "message": "success", "data": data}


@router.get("/owners")
async def product_owners(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await product_service.get_product_owners(db)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{product_id}")
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    data = await product_service.get_product_detail(db, product_id)
    if data is None:
        return {"code": 404, "message": "产品不存在", "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.post("")
async def create_product(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    name = req.get("name", "")
    if not name:
        return {"code": 400, "message": "产品名称不能为空", "data": None}
    data = await product_service.create_product(
        db, name, req.get("line_name"), req.get("owner_id"),
        req.get("status"), req.get("description"), user.id,
    )
    return {"code": 200, "message": "创建成功", "data": data}


@router.put("/{product_id}")
async def update_product(product_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok = await product_service.update_product(
        db, product_id, req.get("name"), req.get("line_name"),
        req.get("owner_id"), req.get("status"), req.get("description"), user.id,
    )
    if not ok:
        return {"code": 404, "message": "产品不存在", "data": None}
    return {"code": 200, "message": "更新成功", "data": None}


@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    ok, err = await product_service.delete_product(db, product_id, user.id)
    if not ok:
        return {"code": 404 if err == "产品不存在" else 400, "message": err, "data": None}
    return {"code": 200, "message": "删除成功", "data": None}
