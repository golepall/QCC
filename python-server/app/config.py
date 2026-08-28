"""应用配置管理（pydantic-settings，支持多环境）"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，所有值可通过环境变量覆盖"""

    # 应用
    APP_NAME: str = "QCC Test Platform"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 3000

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///../server/database/qcc.db"

    # JWT
    JWT_SECRET: str = "qcc-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72

    # 文件路径
    UPLOAD_DIR: str = "../server/uploads"
    EXPORT_DIR: str = "../server/exports"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # 日志
    LOG_LEVEL: str = "INFO"

    model_config = {"env_prefix": "QCC_", "env_file": ".env"}


settings = Settings()
