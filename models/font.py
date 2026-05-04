from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, Text

from models.base import Base


class Font(Base):
    __tablename__ = 'fonts'

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    family: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=True)  # serif, sans-serif, display, etc.
    variants: Mapped[str] = mapped_column(Text, nullable=True)  # Comma-separated list of variants
    subsets: Mapped[str] = mapped_column(Text, nullable=True)  # Comma-separated list of subsets
    version: Mapped[str] = mapped_column(String(50), nullable=True)
    last_modified: Mapped[str] = mapped_column(String(50), nullable=True)  # Date from Google Fonts API
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Font(id={self.id}, family={self.family})>"
