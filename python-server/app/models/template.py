"""模板系统数据模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReportTemplate(Base):
    __tablename__ = "report_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_code: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sheet_config: Mapped[str] = mapped_column(Text, default="{}")
    test_items: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    categories: Mapped[list["TestCategory"]] = relationship(back_populates="template")
    projects: Mapped[list["ReportProject"]] = relationship(back_populates="template")


class TestCategory(Base):
    __tablename__ = "test_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_template.id"), nullable=False)
    category_code: Mapped[str] = mapped_column(String(50), nullable=False)
    category_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped["ReportTemplate"] = relationship(back_populates="categories")
    items: Mapped[list["TestItem"]] = relationship(back_populates="category")


class TestItem(Base):
    __tablename__ = "test_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("test_category.id"), nullable=False)
    item_no: Mapped[str] = mapped_column(String(50), nullable=False)
    test_item: Mapped[str] = mapped_column(Text, nullable=False)
    test_case: Mapped[str] = mapped_column(Text, default="")
    condition_desc: Mapped[str] = mapped_column(Text, default="")
    criteria: Mapped[str] = mapped_column(Text, default="")
    is_header: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped["TestCategory"] = relationship(back_populates="items")
    records: Mapped[list["TestRecord"]] = relationship(back_populates="item")
