"""创建管理员账号脚本"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_engine, get_session_factory
from app.models.base import Base
from scripts.seed_data import ensure_admin


async def main():
    """创建管理员账号"""
    engine = get_engine()

    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建管理员
    factory = get_session_factory()
    async with factory() as session:
        await ensure_admin(session)

    print("Admin user created successfully!")


if __name__ == "__main__":
    asyncio.run(main())
