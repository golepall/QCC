"""自动测试模块数据模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.models.base import Base


class AutoTestRun(Base):
    """自动测试执行记录"""
    __tablename__ = "autotest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    run_name: Mapped[str] = mapped_column(String(200), default="")
    run_type: Mapped[str] = mapped_column(String(50), default="full")  # full / partial / single
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending / running / completed / failed / cancelled
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual / scheduled / api
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    passed_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, default=0)
    error_items: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped["ReportProject"] = relationship(foreign_keys=[project_id])
    results: Mapped[list["AutoTestResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AutoTestResult(Base):
    """自动测试单项结果"""
    __tablename__ = "autotest_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("autotest_run.id"), nullable=False)
    item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("test_item.id"), nullable=True)
    category_name: Mapped[str] = mapped_column(String(200), default="")
    item_no: Mapped[str] = mapped_column(String(50), default="")
    test_item: Mapped[str] = mapped_column(String(500), default="")
    test_case: Mapped[str] = mapped_column(String(200), default="")
    execute_mode: Mapped[str] = mapped_column(String(50), default="manual")  # auto / manual / semi-auto
    script_id: Mapped[str] = mapped_column(String(200), default="")
    result: Mapped[str] = mapped_column(String(50), default="")  # Pass / Fail / NA / Blocked / Error / Skipped
    actual_value: Mapped[str] = mapped_column(Text, default="")
    expected_value: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    evidence_path: Mapped[str] = mapped_column(String(500), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    run: Mapped["AutoTestRun"] = relationship(back_populates="results")
