"""数据库初始化与种子数据

- 创建表（由 SQLAlchemy Base.metadata.create_all 处理）
- 确保 admin 用户存在（admin / admin123）
"""
import os
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def hash_password(password: str, salt: str) -> str:
    """PBKDF2 密码哈希（与 Node.js crypto.pbkdf2Sync 兼容）"""
    return hashlib.pbkdf2_hmac(
        "sha512", password.encode(), salt.encode(), 10000, dklen=64
    ).hex()


async def ensure_admin(db: AsyncSession) -> None:
    """确保默认管理员账号存在"""
    result = await db.execute(select(User).where(User.username == "admin"))
    if result.scalar_one_or_none() is not None:
        print("Seed data already exists, skipping...")
        return

    salt = os.urandom(16).hex()
    password = hash_password("admin123", salt)
    admin = User(
        username="admin",
        password=password,
        salt=salt,
        display_name="管理员",
        role="admin",
    )
    db.add(admin)
    await db.commit()
    print("Admin user created: admin / admin123")
