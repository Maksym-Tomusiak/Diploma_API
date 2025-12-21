from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional

from models.font import Font


def create_font(db: Session, family: str, category: Optional[str] = None,
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
    db.add(font)
    db.commit()
    db.refresh(font)
    return font


def get_all_fonts(db: Session, skip: int = 0, limit: int = 1000, search: Optional[str] = None) -> List[Font]:
    """Get all fonts with pagination and search"""
    query = select(Font)
    
    # Add search filter if provided
    if search:
        query = query.where(Font.family.ilike(f"%{search}%"))
    
    query = query.order_by(Font.family).offset(skip).limit(limit)
    result = db.execute(query)
    return list(result.scalars().all())


def get_font_by_id(db: Session, font_id: int) -> Optional[Font]:
    """Get font by ID"""
    result = db.execute(select(Font).where(Font.id == font_id))
    return result.scalar_one_or_none()


def get_font_by_family(db: Session, family: str) -> Optional[Font]:
    """Get font by family name"""
    result = db.execute(select(Font).where(Font.family == family))
    return result.scalar_one_or_none()


def count_fonts(db: Session, search: Optional[str] = None) -> int:
    """Count total number of fonts with optional search filter"""
    query = select(Font)
    
    # Add search filter if provided
    if search:
        query = query.where(Font.family.ilike(f"%{search}%"))
    
    result = db.execute(query)
    return len(list(result.scalars().all()))


def delete_all_fonts(db: Session) -> None:
    """Delete all fonts (for re-seeding)"""
    result = db.execute(select(Font))
    fonts = result.scalars().all()
    for font in fonts:
        db.delete(font)
    db.commit()


def bulk_create_fonts(db: Session, fonts_data: List[dict]) -> int:
    """Bulk create fonts from list of dicts"""
    fonts = [Font(**font_data) for font_data in fonts_data]
    db.add_all(fonts)
    db.commit()
    return len(fonts)
