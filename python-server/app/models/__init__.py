"""数据模型索引 - 确保所有模型被 SQLAlchemy 发现"""
from app.models.base import Base
from app.models.user import User
from app.models.template import ReportTemplate, TestCategory, TestItem
from app.models.config import DeviceConfig
from app.models.project import (
    ReportProject,
    TestRecord,
    BugRecord,
    PerformanceData,
    ProductImage,
    HeatTestData,
)
from app.models.management import (
    Product,
    Requirement,
    RequirementChange,
    Task,
    ActivityLog,
    Notification,
    ReportBatch,
    ReportArtifact,
)

__all__ = [
    "Base",
    "User",
    "ReportTemplate",
    "TestCategory",
    "TestItem",
    "DeviceConfig",
    "ReportProject",
    "TestRecord",
    "BugRecord",
    "PerformanceData",
    "ProductImage",
    "HeatTestData",
    "Product",
    "Requirement",
    "RequirementChange",
    "Task",
    "ActivityLog",
    "Notification",
    "ReportBatch",
    "ReportArtifact",
]
