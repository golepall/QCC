"""认证业务逻辑"""
import os
import hashlib
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.middleware.auth import create_access_token


def _hash_password(password: str, salt: str) -> str:
    """PBKDF2 密码哈希（兼容 Node.js crypto.pbkdf2Sync sha512 10000iter 64bytes）"""
    return hashlib.pbkdf2_hmac(
        "sha512",
        password.encode(),
        salt.encode(),
        10000,
        dklen=64,
    ).hex()


def _generate_salt() -> str:
    """生成随机盐（hex 字符串，32 字节）"""
    return os.urandom(32).hex()


async def authenticate(db: AsyncSession, username: str, password: str) -> dict | None:
    """验证用户名密码，成功返回 token+user，失败返回 None"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        return None

    hashed = _hash_password(password, user.salt)
    if hashed != user.password:
        return None

    # 更新最后登录时间
    user.last_login = datetime.now()
    await db.flush()

    token = create_access_token(user.id, user.username, user.role)
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "displayName": user.display_name,
            "role": user.role,
        },
    }


async def register_user(
    db: AsyncSession,
    username: str,
    password: str,
    display_name: str = "",
) -> User:
    """注册新用户，用户名已存在则返回 None"""
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none() is not None:
        return None

    salt = _generate_salt()
    hashed = _hash_password(password, salt)

    user = User(
        username=username,
        password=hashed,
        salt=salt,
        display_name=display_name,
        role="user",
    )
    db.add(user)
    await db.flush()
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """根据 ID 获取用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_all_users(db: AsyncSession) -> list[User]:
    """获取所有用户列表"""
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def update_user_role(db: AsyncSession, user_id: int, role: str) -> User | None:
    """更新用户角色"""
    user = await get_user_by_id(db, user_id)
    if user:
        user.role = role
        await db.flush()
    return user


async def reset_user_password(db: AsyncSession, user_id: int, new_password: str) -> User | None:
    """重置用户密码"""
    user = await get_user_by_id(db, user_id)
    if user:
        salt = _generate_salt()
        user.password = _hash_password(new_password, salt)
        user.salt = salt
        await db.flush()
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """删除用户"""
    user = await get_user_by_id(db, user_id)
    if user:
        await db.delete(user)
        await db.flush()
        return True
    return False
