from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON

from models.base import Base


class Template(Base):
    __tablename__ = 'templates'

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)  # Formatting rules
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)

    # Example params structure:
    # {
    #   "page": {"format": "A4", "margins": {"left": 20, "right": 10, "top": 20, "bottom": 20}},
    #   "typography": {"font_family": "Times New Roman", "font_size": 14, "line_spacing": 1.5},
    #   "headings": {"section": "UPPERCASE_CENTER", "subsection": "titlecase_indent"},
    #   "numbering": {"pages": "top_right_from_intro", "figures": "Рис.", "tables": "Таблиця"}
    # }
