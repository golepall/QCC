"""产品、需求、任务、通知等管理模块数据模型"""
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Date, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.models.base import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    line_name: Mapped[str] = mapped_column(String(100), default="")
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="planning")
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Requirement(Base):
    __tablename__ = "requirement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    req_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    req_type: Mapped[str] = mapped_column(String(50), default="business")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    source: Mapped[str] = mapped_column(String(100), default="")
    module: Mapped[str] = mapped_column(String(100), default="")
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    creator_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    effort_hours: Mapped[float] = mapped_column(Float, default=0)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RequirementChange(Base):
    __tablename__ = "requirement_change"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    req_id: Mapped[int] = mapped_column(Integer, ForeignKey("requirement.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    change_reason: Mapped[str] = mapped_column(Text, default="")
    operator_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)  # 任务名称
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")  # 类别
    project_category: Mapped[str] = mapped_column(String(100), default="")  # 项目类别
    task_type: Mapped[str] = mapped_column(String(50), default="task")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(50), default="todo")
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    req_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("requirement.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    creator_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    test_engineer: Mapped[str] = mapped_column(String(100), default="")  # 测试工程师
    client: Mapped[str] = mapped_column(String(100), default="")  # 委托人
    commission_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 接收委托时间
    commission_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 委托需求完成时间
    dev_target_time: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 研发目标完成时间
    sample_time: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 拿到样品时间
    actual_complete_time: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 实际完成时间
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 进度百分比
    remark: Mapped[str] = mapped_column(Text, default="")  # 备注
    effort_hours: Mapped[float] = mapped_column(Float, default=0)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    noti_type: Mapped[str] = mapped_column(String(50), default="system")
    target_type: Mapped[str] = mapped_column(String(50), default="")
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ReportBatch(Base):
    __tablename__ = "report_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    batch_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    status: Mapped[str] = mapped_column(String(50), default="completed")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped["ReportProject"] = relationship(back_populates="report_batches")
    artifacts: Mapped[list["ReportArtifact"]] = relationship(back_populates="batch")


class ReportArtifact(Base):
    __tablename__ = "report_artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("report_batch.id"), nullable=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    batch: Mapped["ReportBatch"] = relationship(back_populates="artifacts")
    project: Mapped["ReportProject"] = relationship(back_populates="report_artifacts")
