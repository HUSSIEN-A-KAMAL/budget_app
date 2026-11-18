from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class BudgetUser(Base):
    """
    Standalone User & RBAC Directory Model for the Isolated Budget & Savings App
    (نموذج المستخدمين والصلاحيات المستقل لنظام الموازنة وترشيد النفقات)
    """
    __tablename__ = "users"

    emp_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="employee", index=True)  # 'admin', 'dept_gm', 'hse_officer', 'employee'
    general_dept_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    dept_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    work_location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeneralDepartmentLookup(Base):
    """
    Standalone Reference Table for General Departments
    (جدول الإدارات العامة المرجعي المستقل بعيداً عن قواعد بيانات Access)
    """
    __tablename__ = "general_departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")


class SystemLookupOption(Base):
    """
    Dynamic Admin-Controlled Lookup Table for Dropdown Options
    Categories: 'DEPARTMENT', 'WORK_LOCATION', 'JOB_TITLE'
    (جدول القوائم المنسدلة الديناميكية القابلة للإضافة والتعديل والحذف)
    """
    __tablename__ = "system_lookup_options"
    __table_args__ = (
        UniqueConstraint("category", "value", name="uq_lookup_category_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
