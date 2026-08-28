"""项目相关数据模型"""
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Date, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.models.base import Base


class ReportProject(Base):
    __tablename__ = "report_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_template.id"), nullable=False)
    product_model: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tester: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), default="")
    approver: Mapped[str] = mapped_column(String(100), default="")
    test_type: Mapped[str] = mapped_column(String(50), default="new")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    conclusion: Mapped[str] = mapped_column(Text, default="")
    config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("device_config.id"), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("product.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=True)
    project_type: Mapped[str] = mapped_column(String(50), default="project")
    view_mode: Mapped[str] = mapped_column(String(20), default="list")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    template: Mapped["ReportTemplate"] = relationship(back_populates="projects")
    config: Mapped[Optional["DeviceConfig"]] = relationship(back_populates="projects")
    records: Mapped[list["TestRecord"]] = relationship(back_populates="project")
    bugs: Mapped[list["BugRecord"]] = relationship(back_populates="project")
    performance_data: Mapped[list["PerformanceData"]] = relationship(back_populates="project")
    product_images: Mapped[list["ProductImage"]] = relationship(back_populates="project")
    heat_test_data: Mapped[list["HeatTestData"]] = relationship(back_populates="project")
    report_batches: Mapped[list["ReportBatch"]] = relationship(back_populates="project")
    report_artifacts: Mapped[list["ReportArtifact"]] = relationship(back_populates="project")


class TestRecord(Base):
    __tablename__ = "test_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("test_item.id"), nullable=False)
    result: Mapped[str] = mapped_column(String(50), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    tester: Mapped[str] = mapped_column(String(100), default="")
    test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped["ReportProject"] = relationship(back_populates="records")
    item: Mapped["TestItem"] = relationship(back_populates="records")


class BugRecord(Base):
    __tablename__ = "bug_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    bug_id: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)  # Bug Description
    description: Mapped[str] = mapped_column(Text, default="")  # Reproduce Steps
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # High/Medium/Low
    mb_info: Mapped[str] = mapped_column(String(200), default="")  # MB主板信息
    bios_info: Mapped[str] = mapped_column(String(200), default="")  # BIOS版本
    sys_info: Mapped[str] = mapped_column(String(200), default="")  # SYS系统信息
    reproduce_rate: Mapped[str] = mapped_column(String(50), default="")  # Abnormal probability
    test_env: Mapped[str] = mapped_column(Text, default="")
    open_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    owner: Mapped[str] = mapped_column(String(100), default="")  # Owner责任人
    root_cause: Mapped[str] = mapped_column(Text, default="")
    solution: Mapped[str] = mapped_column(Text, default="")
    tester: Mapped[str] = mapped_column(String(100), default="")  # Testing personnel
    status: Mapped[str] = mapped_column(String(50), default="open")
    close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")  # Comment
    remark: Mapped[str] = mapped_column(Text, default="")  # Remark备注
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped["ReportProject"] = relationship(back_populates="bugs")


class PerformanceData(Base):
    __tablename__ = "performance_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    test_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sku_name: Mapped[str] = mapped_column(String(200), default="")
    metric_name: Mapped[str] = mapped_column(String(200), nullable=False)
    metric_value: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), default="")
    test_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    raw_output: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped["ReportProject"] = relationship(back_populates="performance_data")


class ProductImage(Base):
    __tablename__ = "product_image"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    image_type: Mapped[str] = mapped_column(String(50), nullable=False)
    image_label: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped["ReportProject"] = relationship(back_populates="product_images")


class HeatTestData(Base):
    __tablename__ = "heat_test_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_project.id"), nullable=False)
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_note: Mapped[str] = mapped_column(Text, default="")
    spec_value: Mapped[str] = mapped_column(String(200), default="")
    test_result: Mapped[str] = mapped_column(String(200), default="")
    comment: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["ReportProject"] = relationship(back_populates="heat_test_data")
