from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from typing import Any
from datetime import datetime

from models.template import Template


class TemplateParams(BaseModel):
    page: dict[str, Any] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    headings: dict[str, Any] = Field(default_factory=dict)
    numbering: dict[str, Any] = Field(default_factory=dict)


class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str = Field(..., max_length=1000)
    params: TemplateParams


class TemplateDto(BaseModel):
    id: int = Field(..., gt=0)
    name: str
    description: str
    params: dict
    is_active: bool
    created_at: datetime

    @staticmethod
    def from_template(template: Template) -> 'TemplateDto':
        return TemplateDto(
            id=template.id,
            name=template.name,
            description=template.description,
            params=template.params,
            is_active=template.is_active,
            created_at=template.created_at
        )

    model_config = SettingsConfigDict(from_attributes=True)
