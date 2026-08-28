import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import settings
from app.dependencies import get_engine
from app.middleware.error_handler import (
    AppException,
    app_exception_handler,
    global_exception_handler,
)
from app.models.base import Base
from app.routers import auth, templates, products, projects, records, bugs, configs, dashboard, requirements, tasks, notifications, export, remote, agent, report_center, pages, excel_templates, autotest
from app.dependencies import get_session_factory
from scripts.seed_data import ensure_admin

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


def create_app() -> FastAPI:
    """FastAPI 应用工厂"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Jinja2 模板引擎
    app.state.templates = Jinja2Templates(directory=TEMPLATE_DIR)

    # 静态文件
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # 注册异常处理器
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # 注册路由
    app.include_router(auth.router)
    app.include_router(templates.router)
    app.include_router(products.router)
    app.include_router(projects.router)
    app.include_router(records.router)
    app.include_router(bugs.router)
    app.include_router(configs.router)
    app.include_router(dashboard.router)
    app.include_router(requirements.router)
    app.include_router(tasks.router)
    app.include_router(notifications.router)
    app.include_router(export.router)
    app.include_router(remote.router)
    app.include_router(agent.router)
    app.include_router(report_center.router)
    app.include_router(excel_templates.router)
    app.include_router(autotest.router)
    app.include_router(pages.router)

    # 启动事件：创建表 + 种子数据
    @app.on_event("startup")
    async def on_startup():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 迁移：为bug_record表添加新字段
        async with engine.begin() as conn:
            columns_to_add = [
                ("mb_info", "VARCHAR(200) DEFAULT ''"),
                ("bios_info", "VARCHAR(200) DEFAULT ''"),
                ("sys_info", "VARCHAR(200) DEFAULT ''"),
                ("owner", "VARCHAR(100) DEFAULT ''"),
                ("remark", "TEXT DEFAULT ''"),
            ]
            for col_name, col_type in columns_to_add:
                try:
                    await conn.execute(text(f"ALTER TABLE bug_record ADD COLUMN {col_name} {col_type}"))
                except Exception:
                    pass

        # 迁移：为task表添加新字段
        async with engine.begin() as conn:
            task_columns = [
                ("category", "VARCHAR(100) DEFAULT ''"),
                ("project_category", "VARCHAR(100) DEFAULT ''"),
                ("test_engineer", "VARCHAR(100) DEFAULT ''"),
                ("client", "VARCHAR(100) DEFAULT ''"),
                ("commission_time", "DATETIME"),
                ("commission_deadline", "DATE"),
                ("dev_target_time", "DATE"),
                ("sample_time", "DATE"),
                ("actual_complete_time", "DATE"),
                ("progress", "INTEGER DEFAULT 0"),
                ("remark", "TEXT DEFAULT ''"),
            ]
            for col_name, col_type in task_columns:
                try:
                    await conn.execute(text(f"ALTER TABLE task ADD COLUMN {col_name} {col_type}"))
                except Exception:
                    pass

        factory = get_session_factory()
        async with factory() as session:
            await ensure_admin(session)

    return app


# 全局模板对象（页面路由通过 app.main.jinja_env 访问）
jinja_env = Jinja2Templates(directory=TEMPLATE_DIR)
app = create_app()
