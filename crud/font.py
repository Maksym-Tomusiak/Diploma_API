from typing import Annotated, List, Optional

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from db import SessionDep
from models.font import Font


class FontRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def create_font(self, family: str, category: Optional[str] = None,
                    variants: Optional[str] = None, subsets: Optional[str] = None,
                    version: Optional[str] = None, last_modified: Optional[str] = None) -> Font:
        """Create a new font"""
        font = Font(
            family=family,
            category=category,
            variants=variants,
            subsets=subsets,
            version=version,
            last_modified=last_modified
        )
        self.session.add(font)
        self.session.commit()
        self.session.refresh(font)
        return font

    def get_all_fonts(self, skip: int = 0, limit: int = 1000, search: Optional[str] = None) -> List[Font]:
        """Get all fonts with pagination and search"""
        query = select(Font)
        
        # Add search filter if provided
        if search:
            query = query.where(Font.family.ilike(f"%{search}%"))
        
        query = query.order_by(Font.family).offset(skip).limit(limit)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_font_by_id(self, font_id: int) -> Optional[Font]:
        """Get font by ID"""
        result = self.session.execute(select(Font).where(Font.id == font_id))
        return result.scalar_one_or_none()

    def get_font_by_family(self, family: str) -> Optional[Font]:
        """Get font by family name"""
        result = self.session.execute(select(Font).where(Font.family == family))
        return result.scalar_one_or_none()

    def count_fonts(self, search: Optional[str] = None) -> int:
        """Count total number of fonts with optional search filter"""
        query = select(Font)
        
        # Add search filter if provided
        if search:
            query = query.where(Font.family.ilike(f"%{search}%"))
        
        result = self.session.execute(query)
        return len(list(result.scalars().all()))

    def delete_all_fonts(self) -> None:
        """Delete all fonts (for re-seeding)"""
        result = self.session.execute(select(Font))
        fonts = result.scalars().all()
        for font in fonts:
            self.session.delete(font)
        self.session.commit()

    def bulk_create_fonts(self, fonts_data: List[dict]) -> int:
        """Bulk create fonts from list of dicts"""
        fonts = [Font(**font_data) for font_data in fonts_data]
        self.session.add_all(fonts)
        self.session.commit()
        return len(fonts)


FontRepositoryDependency = Annotated[FontRepository, Depends(FontRepository)]
