"""依赖注入（数据库会话、当前用户）"""
from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings


@lru_cache()
def get_engine():
    """创建异步数据库引擎（单例）"""
    return create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)


def get_session_factory():
    """创建会话工厂"""
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（FastAPI Depends）"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
