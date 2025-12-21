from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from db import get_db
from schemas.font import FontDto, FontListResponse, FontSeedResponse
from crud import font as font_crud


router = APIRouter(prefix="/fonts", tags=["fonts"])


@router.get("/", summary="Get all fonts")
def list_fonts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=1000, description="Number of records to return"),
    search: Optional[str] = Query(None, description="Search by font family name"),
    db: Session = Depends(get_db)
) -> dict:
    """Get paginated list of all fonts with optional search"""
    fonts = font_crud.get_all_fonts(db, skip=skip, limit=limit, search=search)
    total = font_crud.count_fonts(db, search=search)
    
    return {
        "fonts": [FontDto.model_validate(font) for font in fonts],
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/{font_id}", response_model=FontDto)
def get_font(
    font_id: int,
    db: Session = Depends(get_db)
):
    """Get font by ID"""
    font = font_crud.get_font_by_id(db, font_id)
    if not font:
        raise HTTPException(status_code=404, detail="Font not found")
    return font


@router.get("/by-family/{family}", response_model=FontDto)
def get_font_by_family(
    family: str,
    db: Session = Depends(get_db)
):
    """Get font by family name"""
    font = font_crud.get_font_by_family(db, family)
    if not font:
        raise HTTPException(status_code=404, detail="Font not found")
    return font


@router.post("/seed", response_model=FontSeedResponse)
def seed_fonts(
    db: Session = Depends(get_db)
):
    """
    Manually seed fonts from Google Web Fonts API
    Uses Google Fonts API key from environment variables
    """
    from core import font as font_core
    try:
        count = font_core.seed_fonts_from_google_with_settings(db)
        return FontSeedResponse(
            success=True,
            message=f"Successfully seeded {count} fonts",
            fonts_added=count
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
