from typing import Optional, Any
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, Session
from models.base import Base


class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, default="BudgetModule", index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_values: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    @property
    def entity(self) -> str:
        return self.module or self.target_id or "BudgetModule"

    @property
    def details(self) -> str:
        return self.reason or (f"Target: {self.target_id}" if self.target_id else "")


def log_system_action(
    db: Session,
    user_id: Optional[str] = "7071",
    action: str = "UPDATE",
    entity: str = "BudgetModule",
    details: Optional[str] = None
) -> SystemAuditLog:
    """
    Helper utility to write append-only audit trail records in SQLite.
    """
    log_entry = SystemAuditLog(
        user_id=str(user_id) if user_id is not None else "SYSTEM",
        user_name="مدير النظام",
        action=action,
        module=entity,
        target_id=entity,
        reason=details
    )
    db.add(log_entry)
    db.flush()
    return log_entry
