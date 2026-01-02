from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime, Boolean, JSON, Float

from models.base import Base


class CheckResult(Base):
    __tablename__ = 'check_results'

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    # template_id is nullable when using custom params
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey('templates.id'), nullable=True, index=True)
    # custom_params stores user-provided formatting rules when not using a template
    custom_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # font_family for custom mode (template has its own font_id)
    custom_font_family: Mapped[Optional[str]] = mapped_column(nullable=True)
    passed: Mapped[bool] = mapped_column(nullable=False)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0-1.0
    issues_count: Mapped[int] = mapped_column(default=0)
    issues: Mapped[List[dict]] = mapped_column(JSON, nullable=False,
                                               default=list)  # [{"type": "font_mismatch", "severity": "high", "details": "..."}]
    processing_time_ms: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="check_results")
