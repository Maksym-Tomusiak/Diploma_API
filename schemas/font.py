from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from models.font import Font


class FontCreate(BaseModel):
    """Schema for creating a font manually"""
    family: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = None
    variants: Optional[str] = "regular"
    subsets: Optional[str] = "latin"
    version: Optional[str] = "v1"
    last_modified: Optional[str] = None


class FontDto(BaseModel):
    """Font data transfer object"""
    id: int = Field(..., gt=0)
    family: str
    category: Optional[str] = None
    variants: Optional[str] = None
    subsets: Optional[str] = None
    version: Optional[str] = None
    last_modified: Optional[str] = None
    created_at: datetime

    @staticmethod
    def from_font(font: Font) -> 'FontDto':
        return FontDto(
            id=font.id,
            family=font.family,
            category=font.category,
            variants=font.variants,
            subsets=font.subsets,
            version=font.version,
            last_modified=font.last_modified,
            created_at=font.created_at
        )

    class Config:
        from_attributes = True


class FontListResponse(BaseModel):
    """Response with list of fonts"""
    fonts: list[FontDto]
    total: int


class FontSeedResponse(BaseModel):
    """Response after seeding fonts"""
    success: bool
    message: str
    fonts_added: int
