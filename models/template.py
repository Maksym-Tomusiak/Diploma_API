from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, JSON, ForeignKey
from typing import Optional

from models.base import Base


class Template(Base):
    __tablename__ = 'templates'

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    font_id: Mapped[Optional[int]] = mapped_column(ForeignKey('fonts.id'), nullable=True, index=True)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)  # Formatting rules (without font_family)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)

    # Relationship
    font: Mapped[Optional["Font"]] = relationship("Font", lazy="joined")

    # Required params structure (font_family moved to font_id FK):
    # {
    #   "font_size": 14,  # Розмір шрифту
    #   "line_spacing": 1.5,  # Міжрядковий інтервал
    #   "margins": {
    #     "top": 20,  # Відступ зверху (мм)
    #     "bottom": 20,  # Відступ знизу (мм)
    #     "left": 30,  # Відступ зліва (мм)
    #     "right": 10  # Відступ справа (мм)
    #   },
    #   "check_numbering": true,  # Чи перевіряти нумерацію сторінок
    #   "start_from_number": 1,  # З якого номера починати нумерацію (номер на першій нумерованій сторінці)
    #   "skip_first_page": false  # Чи пропускати першу сторінку (перша сторінка без номера)
    # }
