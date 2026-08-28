"""认证路由（/api/auth/*）"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user, get_admin_user
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.common import success, error
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    result = await auth_service.authenticate(db, req.username, req.password)
    if result is None:
        return error(code=401, message="用户名或密码错误")
    return success(data=result, message="登录成功")


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    user = await auth_service.register_user(
        db, req.username, req.password, req.display_name
    )
    if user is None:
        return error(code=400, message="用户名已存在")
    return success(
        data={
            "id": user.id,
            "username": user.username,
            "displayName": user.display_name,
        },
        message="注册成功",
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return success(
        data={
            "id": current_user.id,
            "username": current_user.username,
            "displayName": current_user.display_name,
            "role": current_user.role,
            "createdAt": str(current_user.created_at) if current_user.created_at else None,
        }
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """登出（JWT 模式为客户端丢弃 token）"""
    return success(message="已登出")


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """获取用户列表（管理员）"""
    users = await auth_service.get_all_users(db)
    return success(
        data=[
            {
                "id": u.id,
                "username": u.username,
                "displayName": u.display_name,
                "role": u.role,
                "createdAt": str(u.created_at) if u.created_at else None,
                "lastLogin": str(u.last_login) if u.last_login else None,
            }
            for u in users
        ]
    )


@router.delete("/users/{user_id}")
async def delete_user_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """删除用户（管理员）"""
    if user_id == admin.id:
        return error(code=400, message="不能删除自己")
    ok = await auth_service.delete_user(db, user_id)
    if not ok:
        return error(code=404, message="用户不存在")
    return success(message="删除成功")


@router.put("/users/{user_id}/role")
async def update_role(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """修改用户角色（管理员）"""
    user = await auth_service.get_user_by_id(db, user_id)
    if user is None:
        return error(code=404, message="用户不存在")
    new_role = "admin" if user.role == "user" else "user"
    await auth_service.update_user_role(db, user_id, new_role)
    return success(message="角色更新成功")


@router.put("/users/{user_id}/password")
async def reset_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """重置用户密码（管理员）"""
    from pydantic import BaseModel, Field

    class ResetPwdBody(BaseModel):
        password: str = Field(..., min_length=6)

    # 用 FastAPI Body 参数（但这里为了简单，直接内联处理）
    return error(code=501, message="密码重置接口需传入新密码参数")
