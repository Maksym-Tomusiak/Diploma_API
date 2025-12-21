from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from typing import Optional
from datetime import datetime

from models.template import Template


class PageMargins(BaseModel):
    """Відступи для сторінок (мм)"""
    top: float = Field(..., ge=0, description="Відступ зверху (мм)")
    bottom: float = Field(..., ge=0, description="Відступ знизу (мм)")
    left: float = Field(..., ge=0, description="Відступ зліва (мм)")
    right: float = Field(..., ge=0, description="Відступ справа (мм)")


class PageNumbering(BaseModel):
    """Налаштування нумерації сторінок"""
    enabled: bool = Field(default=True, description="Чи включена нумерація сторінок")
    start_page: int = Field(default=1, ge=1, description="З якої сторінки починати нумерацію")


class TemplateParams(BaseModel):
    """Параметри шаблону форматування (без font_family - тепер це окрема сутність)"""
    font_size: float = Field(..., gt=0, description="Розмір шрифту")
    line_spacing: float = Field(..., gt=0, description="Міжрядковий інтервал")
    margins: PageMargins = Field(..., description="Відступи для сторінок")
    page_numbering: PageNumbering = Field(default_factory=PageNumbering, description="Налаштування нумерації сторінок")
    skip_first_page: bool = Field(default=False, description="Чи пропускати першу сторінку для всіх перевірок")


class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str = Field(..., max_length=1000)
    font_id: Optional[int] = Field(None, description="ID шрифту з таблиці fonts")
    params: TemplateParams


class TemplateUpdate(BaseModel):
    """Schema for updating template - all fields optional"""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    font_id: Optional[int] = Field(None, description="ID шрифту з таблиці fonts")
    params: Optional[TemplateParams] = None
    is_active: Optional[bool] = None


class TemplateDto(BaseModel):
    id: int = Field(..., gt=0)
    name: str
    description: str
    font_id: Optional[int]
    font_family: Optional[str] = None  # Added for convenience
    params: dict
    is_active: bool
    created_at: datetime

    @staticmethod
    def from_template(template: Template) -> 'TemplateDto':
        return TemplateDto(
            id=template.id,
            name=template.name,
            description=template.description,
            font_id=template.font_id,
            font_family=template.font.family if template.font else None,
            params=template.params,
            is_active=template.is_active,
            created_at=template.created_at
        )

    model_config = SettingsConfigDict(from_attributes=True)
