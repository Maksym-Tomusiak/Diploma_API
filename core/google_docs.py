"""
Google Docs Service - Fetches document properties from Google Docs API.
"""
import math
from typing import Annotated, Optional, Callable
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from common.app_settings import settings


@dataclass
class TextSegment:
    """A segment of text with its formatting."""
    content: str
    font_family: Optional[str]
    font_size_pt: Optional[float]
    paragraph_index: int
    char_count: int
    is_heading: bool = False  # True if this is a heading (HEADING_1, HEADING_2, etc.)
    is_on_first_page: bool = True  # True if this segment is before the first page break


@dataclass
class ParagraphLineSpacing:
    """Line spacing for a paragraph."""
    paragraph_index: int
    line_spacing: float
    is_on_first_page: bool = True

@dataclass
class ImageInfo:
    paragraph_index: int
    alignment: str  # 'CENTER', 'START', 'END', 'JUSTIFIED', 'UNKNOWN'
    is_on_first_page: bool

@dataclass
class ParagraphAlignment:
    paragraph_index: int
    alignment: str
    text: str
    is_italic: bool
    is_on_first_page: bool

@dataclass
class DocumentProperties:
    """Extracted document formatting properties."""
    title: str
    # Page setup
    page_width_pt: float  # in points (72 pt = 1 inch)
    page_height_pt: float
    margin_top_pt: float
    margin_bottom_pt: float
    margin_left_pt: float
    margin_right_pt: float
    # All text segments with their styles
    text_segments: list[TextSegment] = field(default_factory=list)
    # Line spacing values found in document (with paragraph indices)
    paragraph_line_spacings: list[ParagraphLineSpacing] = field(default_factory=list)
    # Page numbering
    has_page_numbers: bool = False
    page_number_start: int = 1
    # First page different (skip first page for numbering/headers)
    first_page_different: bool = False
    # Fallback styles from NORMAL_TEXT
    fallback_font_family: Optional[str] = None
    fallback_font_size_pt: Optional[float] = None
    # First page break tracking (paragraph index where first page break occurs)
    first_page_break_index: Optional[int] = None
    # Image and alignment info
    images: list[ImageInfo] = field(default_factory=list)
    alignments: list[ParagraphAlignment] = field(default_factory=list)
    
    @property
    def line_spacing_values(self) -> list[float]:
        """Backward compatibility: return just the spacing values."""
        return [pls.line_spacing for pls in self.paragraph_line_spacings]

    def margin_top_mm(self) -> float:
        """Convert margin from points to mm."""
        return self.margin_top_pt * 25.4 / 72

    def margin_bottom_mm(self) -> float:
        return self.margin_bottom_pt * 25.4 / 72

    def margin_left_mm(self) -> float:
        return self.margin_left_pt * 25.4 / 72

    def margin_right_mm(self) -> float:
        return self.margin_right_pt * 25.4 / 72
    
    def get_dominant_line_spacing(self) -> Optional[float]:
        """Get the most common line spacing value."""
        if not self.line_spacing_values:
            return None
        from collections import Counter
        counter = Counter(self.line_spacing_values)
        return counter.most_common(1)[0][0]


class GoogleDocsService:
    """Service for interacting with Google Docs API."""

    def _get_credentials(
        self, 
        google_token: str, 
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str], None]] = None
    ) -> Credentials:
        """
        Create Google credentials, refreshing if needed.
        
        Args:
            google_token: Current access token
            refresh_token: Refresh token for getting new access tokens
            on_token_refresh: Callback to save new token when refreshed
        """
        credentials = Credentials(
            token=google_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        
        # Try to refresh if token is expired and we have a refresh token
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                if on_token_refresh and credentials.token:
                    on_token_refresh(credentials.token)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Failed to refresh Google token. Please log in again. Error: {str(e)}"
                )
        
        return credentials

    def get_document_properties(
        self, 
        google_token: str, 
        doc_id: str,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str], None]] = None
    ) -> DocumentProperties:
        """
        Fetch document properties from Google Docs.
        
        Args:
            google_token: User's Google OAuth access token
            doc_id: Google Document ID
            refresh_token: User's Google refresh token (optional, for auto-refresh)
            on_token_refresh: Callback when token is refreshed (to save new token)
            
        Returns:
            DocumentProperties with extracted formatting info
        """
        try:
            credentials = self._get_credentials(google_token, refresh_token, on_token_refresh)
            service = build("docs", "v1", credentials=credentials)
            
            # Get the full document
            document = service.documents().get(documentId=doc_id).execute()
            
            return self._extract_properties(document)
            
        except HttpError as e:
            if e.resp.status == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Google Document not found: {doc_id}"
                )
            elif e.resp.status == 403:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this Google Document. Please ensure you have read permission."
                )
            elif e.resp.status == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google authentication expired. Please log in again."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Error communicating with Google Docs API: {str(e)}"
                )

    def _extract_properties(self, document: dict) -> DocumentProperties:
        """Extract formatting properties from a Google Docs document."""
        title = document.get("title", "Untitled")
        
        # Get document style (page setup)
        doc_style = document.get("documentStyle", {})
        page_size = doc_style.get("pageSize", {})
        
        # Page dimensions (in points)
        page_width_pt = page_size.get("width", {}).get("magnitude", 612)  # Default letter width
        page_height_pt = page_size.get("height", {}).get("magnitude", 792)  # Default letter height
        
        # Margins (in points)
        margin_top = doc_style.get("marginTop", {}).get("magnitude", 72)  # Default 1 inch
        margin_bottom = doc_style.get("marginBottom", {}).get("magnitude", 72)
        margin_left = doc_style.get("marginLeft", {}).get("magnitude", 72)
        margin_right = doc_style.get("marginRight", {}).get("magnitude", 72)
        
        # Calculate usable content width for line-wrap estimation
        content_width_pt = page_width_pt - margin_left - margin_right
        
        # First page header/footer different
        first_page_different = doc_style.get("useFirstPageHeaderFooter", False)
        
        # Build a map of all named styles (NORMAL_TEXT, HEADING_1, etc.)
        named_styles_map: dict[str, dict] = {}
        named_styles = document.get("namedStyles", {}).get("styles", [])
        for style in named_styles:
            style_type = style.get("namedStyleType")
            if style_type:
                text_style = style.get("textStyle", {})
                named_styles_map[style_type] = {
                    "font_family": text_style.get("weightedFontFamily", {}).get("fontFamily"),
                    "font_size": text_style.get("fontSize", {}).get("magnitude"),
                }
        
        # Get NORMAL_TEXT as the ultimate fallback
        fallback_font = named_styles_map.get("NORMAL_TEXT", {}).get("font_family")
        fallback_size = named_styles_map.get("NORMAL_TEXT", {}).get("font_size")
        
        # Collect ALL text segments with their individual styles
        text_segments: list[TextSegment] = []
        paragraph_line_spacings: list[ParagraphLineSpacing] = []
        images: list[ImageInfo] = []
        alignments: list[ParagraphAlignment] = []
        
        # Track first page break for skip_first_page functionality
        first_page_break_index: Optional[int] = None
        
        # Scan body content first to find manual page break
        body = document.get("body", {})
        content = body.get("content", [])
        
        # First pass: find manual page break
        temp_para_index = 0
        for element in content:
            if "pageBreak" in element and first_page_break_index is None:
                first_page_break_index = temp_para_index
            if "paragraph" in element:
                temp_para_index += 1
        
        # If no manual page break found, estimate first page end based on content height
        estimated_first_page_end: Optional[int] = None
        if first_page_break_index is None:
            # Calculate available height on first page (page height minus margins)
            # Reduce by 12% as safety margin for headers, footers, and spacing variations
            available_height_pt = (page_height_pt - margin_top - margin_bottom) * 0.87
            
            # Estimate paragraph heights and accumulate until we exceed first page
            cumulative_height_pt = 0.0
            temp_para_index = 0
            
            for element in content:
                if "paragraph" in element:
                    paragraph = element["paragraph"]
                    para_style = paragraph.get("paragraphStyle", {})
                    
                    # Get line spacing (default 1.15)
                    line_spacing = para_style.get("lineSpacing", 115) / 100
                    
                    # Get spacing before and after paragraph (in points)
                    spacing_before = para_style.get("spacingBefore", {}).get("magnitude", 0)
                    spacing_after = para_style.get("spacingAfter", {}).get("magnitude", 0)
                    
                    # Get paragraph's named style to estimate font size
                    para_named_style_type = para_style.get("namedStyleType", "NORMAL_TEXT")
                    para_style_defaults = named_styles_map.get(para_named_style_type, {})
                    is_heading = para_named_style_type.startswith("HEADING_")
                    
                    # Estimate font size for this paragraph
                    estimated_font_size = para_style_defaults.get("font_size") or fallback_size or 11
                    
                    # Count lines in paragraph (rough estimate based on content)
                    para_text_length = 0
                    for elem in paragraph.get("elements", []):
                        if "textRun" in elem:
                            content_text = elem["textRun"].get("content", "")
                            para_text_length += len(content_text)
                    
                    # --- IMPROVED ESTIMATION LOGIC ---
                    
                    # Calculate avg char width (0.6 is a standard ratio for variable width fonts)
                    avg_char_width_pt = estimated_font_size * 0.62
                    
                    # Calculate how many chars fit on one line dynamically
                    chars_per_line = max(1, content_width_pt / avg_char_width_pt)
                    
                    # Use ceil to account for wrapping (e.g. 61 chars in 60 limit = 2 lines)
                    if para_text_length > 0:
                        estimated_lines = math.ceil(para_text_length / chars_per_line)
                    else:
                        estimated_lines = 1  # Empty line still has height
                    
                    # ---------------------------------
                    font_vertical_metrics = 1.2
                    # Calculate paragraph height: 
                    # - Base line height = font_size * line_spacing * number_of_lines
                    # - Add spacing before and after from paragraph style
                    # - Add extra spacing for headings (they typically have more space)
                    # - Add a buffer per paragraph (3pt) to account for rendering variations
                    base_line_height = (estimated_font_size * font_vertical_metrics) * line_spacing * estimated_lines
                    heading_extra_space = estimated_font_size if is_heading else 0
                    
                    para_height = base_line_height + spacing_before + spacing_after + heading_extra_space + 3
                    
                    cumulative_height_pt += para_height
                    
                    # If we've exceeded the first page height, mark this as the boundary
                    if cumulative_height_pt > available_height_pt:
                        estimated_first_page_end = temp_para_index
                        break
                    
                    temp_para_index += 1
        
        # Determine which method to use for first page detection
        first_page_end_index = first_page_break_index if first_page_break_index is not None else estimated_first_page_end
        
        # Scan body content again to extract properties
        paragraph_index = 0
        for element in content:
            if "paragraph" in element:
                paragraph = element["paragraph"]
                para_style = paragraph.get("paragraphStyle", {})
                
                # Get the paragraph's named style type (e.g., HEADING_1, NORMAL_TEXT)
                para_named_style_type = para_style.get("namedStyleType", "NORMAL_TEXT")
                is_heading = para_named_style_type.startswith("HEADING_")
                
                # Get the paragraph's named style defaults
                para_style_defaults = named_styles_map.get(para_named_style_type, {})
                para_default_font = para_style_defaults.get("font_family") or fallback_font
                para_default_size = para_style_defaults.get("font_size") or fallback_size
                
                # Get line spacing from paragraph (default to 1.15 if not specified, which is Google Docs default)
                line_spacing = para_style.get("lineSpacing", 115) / 100
                # Mark as first page if this paragraph is before the first page end (manual break or estimated)
                is_on_first_page = first_page_end_index is not None and paragraph_index < first_page_end_index
                paragraph_line_spacings.append(ParagraphLineSpacing(
                    paragraph_index=paragraph_index,
                    line_spacing=line_spacing,
                    is_on_first_page=is_on_first_page,
                ))

                # --- NEW: Image Detection and Alignment ---
                has_image = False
                for elem in paragraph.get("elements", []):
                    if "inlineObjectElement" in elem:
                        has_image = True
                        break
                
                # Resolve alignment
                alignment = para_style.get("alignment", "START")
                
                if has_image:
                    images.append(ImageInfo(
                        paragraph_index=paragraph_index,
                        alignment=alignment,
                        is_on_first_page=is_on_first_page
                    ))
                
                # Store alignment info for captions/sources
                full_text = ""
                is_italic = False
                for elem in paragraph.get("elements", []):
                    if "textRun" in elem:
                        text_run = elem["textRun"]
                        full_text += text_run.get("content", "")
                        if text_run.get("textStyle", {}).get("italic"):
                            is_italic = True
                
                alignments.append(ParagraphAlignment(
                    paragraph_index=paragraph_index,
                    alignment=alignment,
                    text=full_text.strip(),
                    is_italic=is_italic,
                    is_on_first_page=is_on_first_page
                ))

                if is_on_first_page:
                    # Debug print with safety checks
                    elements = paragraph.get("elements", [])
                    if elements and len(elements) > 0:
                        first_elem = elements[0]
                        text_run = first_elem.get("textRun")
                        if text_run:
                            content = text_run.get("content", "")
                            print(f'Paragraph {content}\nline spacing: {line_spacing:.2f}\n')
                
                # Scan text runs in paragraph
                for elem in paragraph.get("elements", []):
                    if "textRun" in elem:
                        text_run = elem["textRun"]
                        text_content = text_run.get("content", "").strip()
                        
                        # Skip empty text runs and whitespace-only
                        if not text_content or text_content == "\n":
                            continue
                        
                        text_style = text_run.get("textStyle", {})
                        char_count = len(text_content)
                        
                        # Get font family (use paragraph's named style default if not specified inline)
                        font_family = para_default_font
                        if "weightedFontFamily" in text_style:
                            font_family = text_style["weightedFontFamily"].get("fontFamily", para_default_font)
                        
                        # Get font size (use paragraph's named style default if not specified inline)
                        font_size = para_default_size
                        if "fontSize" in text_style:
                            font_size = text_style["fontSize"].get("magnitude", para_default_size)
                        
                        # Determine if this segment is on the first page (using manual break or estimation)
                        is_on_first_page = first_page_end_index is not None and paragraph_index < first_page_end_index
                        
                        # Create a TextSegment for this run
                        text_segments.append(TextSegment(
                            content=text_content,
                            font_family=font_family,
                            font_size_pt=font_size,
                            paragraph_index=paragraph_index,
                            char_count=char_count,
                            is_heading=is_heading,
                            is_on_first_page=is_on_first_page,
                        ))
                
                paragraph_index += 1
        
        # Check for page numbers in headers/footers
        has_page_numbers = False
        page_number_start = 1
        
        headers = document.get("headers", {})
        footers = document.get("footers", {})
        
        # Check headers
        for header_id, header in headers.items():
            if self._contains_page_number(header.get("content", [])):
                has_page_numbers = True
                break
        
        # Check footers if not found in headers
        if not has_page_numbers:
            for footer_id, footer in footers.items():
                if self._contains_page_number(footer.get("content", [])):
                    has_page_numbers = True
                    break
        
        # Get page number start from document style
        page_number_start = doc_style.get("pageNumberStart", 1)
        
        # When "different first page" is enabled, Google Docs reports the pageNumberStart value
        # which is exactly what appears on page 2 (the first numbered page).
        # So if pageNumberStart = 3 and first_page_different = true:
        #   - Page 1: no number
        #   - Page 2: shows "3"
        #   - Page 3: shows "4"
        # No adjustment needed - the value from API is correct.
        
        return DocumentProperties(
            title=title,
            page_width_pt=page_width_pt,
            page_height_pt=page_height_pt,
            margin_top_pt=margin_top,
            margin_bottom_pt=margin_bottom,
            margin_left_pt=margin_left,
            margin_right_pt=margin_right,
            has_page_numbers=has_page_numbers,
            page_number_start=page_number_start,
            first_page_different=first_page_different,
            text_segments=text_segments,
            paragraph_line_spacings=paragraph_line_spacings,
            fallback_font_family=fallback_font,
            fallback_font_size_pt=fallback_size,
            first_page_break_index=first_page_break_index,
            images=images,
            alignments=alignments,
        )

    def _contains_page_number(self, content: list) -> bool:
        """Check if content contains page number element."""
        for element in content:
            if "paragraph" in element:
                for elem in element["paragraph"].get("elements", []):
                    if "pageBreak" in elem:
                        continue
                    if "autoText" in elem:
                        auto_text = elem["autoText"]
                        if auto_text.get("type") == "PAGE_NUMBER":
                            return True
        return False


def get_google_docs_service() -> GoogleDocsService:
    """Dependency injection for GoogleDocsService."""
    return GoogleDocsService()


GoogleDocsServiceDependency = Annotated[GoogleDocsService, Depends(get_google_docs_service)]
