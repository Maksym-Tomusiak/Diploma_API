import httpx
from sqlalchemy.orm import Session
from typing import List, Annotated
import logging

from fastapi import Depends
from crud.font import FontRepositoryDependency
from schemas.font import FontDto
from common.app_settings import settings

logger = logging.getLogger(__name__)

# Standard fonts that can't be fetched from Google Fonts API
STANDARD_FONTS = [
    {"name": "Times New Roman", "family": "serif"},
    {"name": "Arial", "family": "sans-serif"},
    {"name": "Calibri", "family": "sans-serif"},
    {"name": "Verdana", "family": "sans-serif"},
    {"name": "Courier New", "family": "monospace"},
    {"name": "Georgia", "family": "serif"},
    {"name": "Trebuchet MS", "family": "sans-serif"},
    {"name": "Comic Sans MS", "family": "cursive"},  # Іноді треба :)
]


def get_all_fonts(font_repository: FontRepositoryDependency) -> List[FontDto]:
    """Get all available fonts"""
    fonts = font_repository.get_all_fonts()
    return [FontDto.from_font(font) for font in fonts]


def get_font_by_id(font_repository: FontRepositoryDependency, font_id: int) -> FontDto | None:
    """Get font by ID"""
    font = font_repository.get_font_by_id(font_id)
    return FontDto.from_font(font) if font else None


def get_font_by_family(font_repository: FontRepositoryDependency, family: str) -> FontDto | None:
    """Get font by family name"""
    font = font_repository.get_font_by_family(family)
    return FontDto.from_font(font) if font else None


def seed_standard_fonts(font_repository: FontRepositoryDependency) -> int:
    """
    Seed standard fonts that are not available in Google Fonts API
    Returns the number of fonts added
    """
    try:
        fonts_data = []
        for font in STANDARD_FONTS:
            # Check if font already exists
            existing = font_repository.get_font_by_family(font["name"])
            if not existing:
                font_data = {
                    "family": font["name"],
                    "category": font["family"],
                    "variants": "regular",
                    "subsets": "latin",
                    "version": "system",
                    "last_modified": None
                }
                fonts_data.append(font_data)
        
        if fonts_data:
            count = font_repository.bulk_create_fonts(fonts_data)
            logger.info(f"Successfully seeded {count} standard fonts")
            return count
        else:
            logger.info("Standard fonts already exist")
            return 0
            
    except Exception as e:
        logger.error(f"Error seeding standard fonts: {e}")
        raise Exception(f"Failed to seed standard fonts: {str(e)}")


def seed_fonts_from_google(font_repository: FontRepositoryDependency, api_key: str) -> int:
    """
    Seed fonts from Google Web Fonts API
    Returns the number of fonts added
    """
    try:
        # Make request to Google Fonts API
        url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={api_key}"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
        
        # Parse and prepare font data
        fonts_data = []
        for item in data.get("items", []):
            font_data = {
                "family": item.get("family"),
                "category": item.get("category"),
                "variants": ",".join(item.get("variants", [])),
                "subsets": ",".join(item.get("subsets", [])),
                "version": item.get("version"),
                "last_modified": item.get("lastModified")
            }
            fonts_data.append(font_data)
        
        # Bulk insert fonts
        count = font_repository.bulk_create_fonts(fonts_data)
        logger.info(f"Successfully seeded {count} fonts from Google Web Fonts API")
        return count
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error while fetching fonts from Google: {e}")
        raise Exception(f"Failed to fetch fonts from Google: {str(e)}")
    except Exception as e:
        logger.error(f"Error seeding fonts: {e}")
        raise Exception(f"Failed to seed fonts: {str(e)}")


def seed_fonts_from_google_with_settings(font_repository: FontRepositoryDependency) -> int:
    """
    Seed fonts from Google Web Fonts API using API key from settings
    Also seeds standard fonts first
    Returns the total number of fonts added
    """
    google_api_key = getattr(settings, "GOOGLE_FONTS_API_KEY", None)
    
    if not google_api_key:
        raise Exception("GOOGLE_FONTS_API_KEY not found in environment variables")
    
    # First seed standard fonts
    standard_count = seed_standard_fonts(font_repository)
    
    # Then seed Google fonts
    google_count = seed_fonts_from_google(font_repository, google_api_key)
    
    return standard_count + google_count


def ensure_fonts_seeded(font_repository: FontRepositoryDependency) -> bool:
    """
    Check if fonts are seeded, if not - seed them from Google Fonts API and standard fonts
    Returns True if fonts were seeded, False if they already existed
    """
    count = font_repository.count_fonts()
    
    if count > 0:
        logger.info(f"Fonts already seeded ({count} fonts found)")
        return False
    
    logger.info("No fonts found. Seeding standard fonts first...")
    
    # First seed standard fonts (always works, no API key needed)
    try:
        seed_standard_fonts(font_repository)
    except Exception as e:
        logger.error(f"Failed to seed standard fonts: {e}")
    
    # Get API key from settings for Google fonts
    google_api_key = getattr(settings, "GOOGLE_FONTS_API_KEY", None)
    
    if not google_api_key:
        logger.warning("GOOGLE_FONTS_API_KEY not found in settings. Only standard fonts were seeded.")
        return True
    
    logger.info("Seeding fonts from Google Web Fonts API...")
    try:
        seed_fonts_from_google(font_repository, google_api_key)
    except Exception as e:
        logger.error(f"Failed to seed Google fonts: {e}")
        logger.info("Standard fonts are available for use.")
    
    return True
