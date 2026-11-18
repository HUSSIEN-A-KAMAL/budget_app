from typing import Optional, List
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, ForeignKey, Text, DateTime, Date, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base


class DepartmentBudget(Base):
    """
    Departmental Quarterly & Annual Budget Allocation Model
    (نموذج موازنة الإدارات الربعية والسنوية)
    """
    __tablename__ = "department_budgets"
    __table_args__ = (
        UniqueConstraint("general_dept_name", "fiscal_year", "quarter", name="uq_dept_budget_year_quarter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    general_dept_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, default=2026, server_default="2026", index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3", index=True)  # 1 to 4
    allocated_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line_items: Mapped[List["BudgetLineItem"]] = relationship(
        "BudgetLineItem",
        back_populates="budget",
        cascade="all, delete-orphan"
    )


class BudgetLineItem(Base):
    """
    Quarterly Budget Line Item & Rationalization/Savings Narrative Model
    (بنود الموازنة الربعية وتفاصيل ترشيد النفقات والتوفير)
    """
    __tablename__ = "budget_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[int] = mapped_column(Integer, ForeignKey("department_budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    allocated_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    spent_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    savings_narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Governance: GM gate, HSE gate, workflow lifecycle, cost avoidance ---
    created_by_emp_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    gm_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    gm_approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gm_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hse_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    hse_approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hse_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NEW", server_default="NEW")
    cost_avoidance_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")

    # --- Variance analysis & corrective action ---
    variance_root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrective_owner: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    corrective_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    budget: Mapped["DepartmentBudget"] = relationship("DepartmentBudget", back_populates="line_items")

    @property
    def savings_amount(self) -> float:
        return round(float(self.allocated_amount or 0.0) - float(self.spent_amount or 0.0), 2)

    @property
    def savings_pct(self) -> float:
        alloc = float(self.allocated_amount or 0.0)
        if alloc <= 0:
            return 0.0
        return round(((alloc - float(self.spent_amount or 0.0)) / alloc) * 100.0, 1)


class BudgetGovernanceConfig(Base):
    """
    System-wide Budget Governance Roles & Settings
    (تعيينات مسؤول السلامة HSE ومديري العموم GMs وإعدادات عرض لوحة الترتيب)
    """
    __tablename__ = "budget_governance_configs"
    __table_args__ = (
        UniqueConstraint("config_type", "scope_key", name="uq_budget_gov_config_type_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # 'HSE_OFFICER', 'DEPT_GM', 'LEADERBOARD_VISIBILITY'
    scope_key: Mapped[str] = mapped_column(String(150), nullable=False, default="GLOBAL", index=True)  # 'GLOBAL' or general_dept_name
    assigned_emp_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    assigned_emp_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
