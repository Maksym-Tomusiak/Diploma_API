"""
Google Docs Service - Fetches document properties from Google Docs API.
"""
import math
import logging
from typing import Annotated, Optional, Callable
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from common.app_settings import settings

logger = logging.getLogger(__name__)


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
    numbering_start_page: int = 1
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
            
            # Try to get PDF twin bytes for perfect page estimation
            pdf_bytes = None
            try:
                drive_service = build("drive", "v3", credentials=credentials)
                pdf_bytes = drive_service.files().export(fileId=doc_id, mimeType="application/pdf").execute()
            except Exception as e:
                logger.warning(f"Failed to export Google Doc to PDF twin: {e}")
                
            return self._extract_properties(document, pdf_bytes)
            
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

    def _extract_properties(self, document: dict, pdf_bytes: Optional[bytes] = None) -> DocumentProperties:
        """Extract formatting properties from a Google Docs document using optional PDF twin mapping."""
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
            if "paragraph" in element:
                if first_page_break_index is None:
                    for elem in element["paragraph"].get("elements", []):
                        if "pageBreak" in elem:
                            first_page_break_index = temp_para_index
                            break
                temp_para_index += 1
                
        # Extract clean paragraph texts and style names for PDF twin matching
        paragraphs_text_list = []
        styles_list = []
        for element in content:
            if "paragraph" in element:
                paragraph = element["paragraph"]
                para_text = "".join(elem.get("textRun", {}).get("content", "") for elem in paragraph.get("elements", []) if "textRun" in elem)
                paragraphs_text_list.append(para_text)
                
                para_style = paragraph.get("paragraphStyle", {})
                para_named_style_type = para_style.get("namedStyleType", "NORMAL_TEXT")
                styles_list.append(para_named_style_type)
        
        # Run PDF twin page mapping if pdf_bytes is available
        pdf_para_pages = {}
        pdf_first_page_end = None
        pdf_doc = None
        if pdf_bytes is not None:
            try:
                import fitz
                import re
                
                pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                logger.info(f"PDF twin loaded successfully. Total pages: {len(pdf_doc)}")
                
                last_found_para_idx = 0
                for page_idx in range(len(pdf_doc)):
                    page_text = pdf_doc[page_idx].get_text("text").strip()
                    if not page_text:
                        continue
                    
                    normalized_target = re.sub(r'\s+', ' ', page_text).strip()
                    # Alphanumeric matching to bypass bullet points, leading numbers, punctuation
                    cleaned_target = re.sub(r'^[\s\d\.\,\-\_●•○■□*+]+', '', normalized_target).strip()
                    target_words = cleaned_target.split()
                    search_snippet = " ".join(target_words[:6]) if len(target_words) > 6 else cleaned_target
                    alphanumeric_snippet = "".join(re.findall(r'\w', search_snippet)).lower()
                    
                    if len(alphanumeric_snippet) < 8:
                        continue
                    
                    for i in range(last_found_para_idx, len(paragraphs_text_list)):
                        p_text = paragraphs_text_list[i]
                        if not p_text.strip():
                            continue
                        
                        # Skip TOC entries to prevent incorrect page mapping
                        if any(x in styles_list[i].lower() for x in ["toc", "table of contents", "зміст", "список"]):
                            continue
                        if p_text.count('.') > 5 or p_text.count('_') > 5 or p_text.count('·') > 5:
                            continue
                        
                        normalized_p = re.sub(r'\s+', ' ', p_text).strip()
                        alphanumeric_p = "".join(re.findall(r'\w', normalized_p)).lower()
                        
                        if len(alphanumeric_p) > 10:
                            if alphanumeric_snippet in alphanumeric_p or alphanumeric_p in alphanumeric_snippet:
                                # Found the paragraph starting this page!
                                for j in range(last_found_para_idx, i):
                                    if j not in pdf_para_pages:
                                        pdf_para_pages[j] = max(1, page_idx)
                                
                                pdf_para_pages[i] = page_idx + 1
                                last_found_para_idx = i
                                break
                
                # Fill in any remaining paragraphs sequentially
                current_p = 1
                for j in range(len(paragraphs_text_list)):
                    if j in pdf_para_pages:
                        current_p = pdf_para_pages[j]
                    else:
                        pdf_para_pages[j] = current_p
                
                # Find the first paragraph that belongs to page 2 (or higher)
                for i in range(len(paragraphs_text_list)):
                    if pdf_para_pages.get(i, 1) >= 2:
                        pdf_first_page_end = i
                        break
                        
                logger.info(f"PDF twin page mapping successful: page 2 starts at paragraph index {pdf_first_page_end}")
            except Exception as e:
                logger.error(f"Failed to perform PDF twin page mapping for Google Docs: {e}")
                
        # Always estimate first page end based on content height to serve as a sanity check
        estimated_first_page_end: Optional[int] = None
        # Calculate available height on first page (page height minus margins)
        # Use 100% of printable area for maximum accuracy instead of reducing it
        available_height_pt = (page_height_pt - margin_top - margin_bottom)
        
        # Estimate paragraph heights and accumulate until we exceed first page
        cumulative_height_pt = 0.0
        temp_para_index = 0
        
        for element in content:
            if "paragraph" in element:
                paragraph = element["paragraph"]
                para_style = paragraph.get("paragraphStyle", {})
                
                # Get the paragraph's named style type (e.g., HEADING_1, NORMAL_TEXT)
                para_named_style_type = para_style.get("namedStyleType", "NORMAL_TEXT")
                is_heading = para_named_style_type.startswith("HEADING_")
                
                # Get the paragraph's named style defaults
                para_style_defaults = named_styles_map.get(para_named_style_type, {})
                
                estimated_font_size = para_style_defaults.get("font_size") or fallback_size or 11
                font_vertical_metrics = 1.2 # roughly 1.2x font size
                line_spacing = para_style.get("lineSpacing", 115) / 100
                
                spacing_before = para_style.get("spaceAbove", {}).get("magnitude", 0)
                spacing_after = para_style.get("spaceBelow", {}).get("magnitude", 0)
                
                # Estimate content width based on page size and margins
                content_width_pt = page_width_pt - margin_left - margin_right
                
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
                
                # Calculate paragraph height: 
                # - Base line height = font_size * line_spacing * number_of_lines
                # - Add spacing before and after from paragraph style
                # - Add extra spacing for headings (they typically have more space)
                # - Add a buffer per paragraph (3pt) to account for rendering variations
                base_line_height = (estimated_font_size * font_vertical_metrics) * line_spacing * estimated_lines
                heading_extra_space = estimated_font_size if is_heading else 0
                
                para_height = base_line_height + spacing_before + spacing_after + heading_extra_space
                
                cumulative_height_pt += para_height
                
                # If we've exceeded the first page height, mark this as the boundary
                if cumulative_height_pt > available_height_pt:
                    estimated_first_page_end = temp_para_index
                    break
                
                temp_para_index += 1
        
        # Determine which method to use for first page detection
        if first_page_break_index is not None and (estimated_first_page_end is None or first_page_break_index <= estimated_first_page_end + 12):
            first_page_end_index = first_page_break_index
        elif pdf_first_page_end is not None and (estimated_first_page_end is None or pdf_first_page_end >= estimated_first_page_end * 0.4):
            first_page_end_index = pdf_first_page_end
        else:
            first_page_end_index = estimated_first_page_end
        
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
                # Mark as first page if this paragraph is on the first page
                is_on_first_page = first_page_end_index is None or paragraph_index < first_page_end_index
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
                        
                        # Determine if this segment is on the first page
                        is_on_first_page = first_page_end_index is None or paragraph_index < first_page_end_index
                        
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
        
        # Track physical page numbers for elements
        # Track physical page numbers for elements
        para_pages = {}
        if pdf_para_pages:
            para_pages = pdf_para_pages
            current_page = len(pdf_doc)
        else:
            cumulative_height_pt = 0.0
            current_page = 1
            available_height_pt = (page_height_pt - margin_top - margin_bottom) * 0.87
            
            temp_para_index = 0
            for element in content:
                if "sectionBreak" in element:
                    # section breaks (if Next Page) often act as page breaks, but we will rely on paragraph pageBreak
                    pass
                    
                if "paragraph" in element:
                    paragraph = element["paragraph"]
                    
                    # Check for explicit page break in paragraph elements
                    has_page_break = any("pageBreak" in elem for elem in paragraph.get("elements", []))
                    if has_page_break:
                        current_page += 1
                        cumulative_height_pt = 0.0
                        
                    para_style = paragraph.get("paragraphStyle", {})
                    line_spacing = para_style.get("lineSpacing", 115) / 100
                    spacing_before = para_style.get("spacingBefore", {}).get("magnitude", 0)
                    spacing_after = para_style.get("spacingAfter", {}).get("magnitude", 0)
                    para_named_style_type = para_style.get("namedStyleType", "NORMAL_TEXT")
                    para_style_defaults = named_styles_map.get(para_named_style_type, {})
                    is_heading = para_named_style_type.startswith("HEADING_")
                    estimated_font_size = para_style_defaults.get("font_size") or fallback_size or 11
                    
                    para_text_length = sum(len(elem.get("textRun", {}).get("content", "")) for elem in paragraph.get("elements", []) if "textRun" in elem)
                    avg_char_width_pt = estimated_font_size * 0.62
                    chars_per_line = max(1, content_width_pt / avg_char_width_pt)
                    estimated_lines = math.ceil(para_text_length / chars_per_line) if para_text_length > 0 else 1
                    
                    font_vertical_metrics = 1.2
                    base_line_height = (estimated_font_size * font_vertical_metrics) * line_spacing * estimated_lines
                    heading_extra_space = estimated_font_size if is_heading else 0
                    para_height = base_line_height + spacing_before + spacing_after + heading_extra_space + 3
                    
                    cumulative_height_pt += para_height
                    if cumulative_height_pt > available_height_pt:
                        current_page += 1
                        cumulative_height_pt = para_height
                        
                    para_pages[temp_para_index] = current_page
                    temp_para_index += 1

        # Track sections and their start pages
        section_styles = [doc_style]
        section_start_pages = {0: 1}
        current_section_idx = 0
        temp_para_index = 0
        current_page = 1
        for element in content:
            if "sectionBreak" in element:
                sb = element["sectionBreak"]
                style = sb.get("sectionStyle", {})
                section_styles.append(style)
                
                # A section break of type NEXT_PAGE implies the new section starts on the next page
                if style.get("sectionType") == "NEXT_PAGE":
                    current_page += 1
                
                next_section_idx = current_section_idx + 1
                section_start_pages[next_section_idx] = current_page
                current_section_idx = next_section_idx
            elif "paragraph" in element:
                # Update current_page based on para_pages for accuracy, but don't let it go backwards
                current_page = max(current_page, para_pages.get(temp_para_index, current_page))
                
                # Check for explicit page break in paragraph elements to ensure current_page advances
                has_page_break = any("pageBreak" in elem for elem in element["paragraph"].get("elements", []))
                if has_page_break:
                    current_page += 1
                    
                temp_para_index += 1

        headers = document.get("headers", {})
        footers = document.get("footers", {})

        # Find first numbered section
        first_numbered_section_idx = -1
        for idx, style in enumerate(section_styles):
            if self._section_has_page_numbers(style, headers, footers):
                first_numbered_section_idx = idx
                break

        # Fallback global check if section styles didn't explicitly link it
        has_page_numbers = first_numbered_section_idx != -1
        if not has_page_numbers:
            for h in headers.values():
                if self._contains_page_number(h.get("content", [])):
                    has_page_numbers = True
                    break
            if not has_page_numbers:
                for f in footers.values():
                    if self._contains_page_number(f.get("content", [])):
                        has_page_numbers = True
                        break
        numbering_start_page = 0
        
        # Use doc_style by default, but override if specific section has page numbers
        doc_style_start = doc_style.get("pageNumberStart", 1)
        page_number_start = doc_style_start

        if has_page_numbers:
            if first_numbered_section_idx > 0:
                if "pageNumberStart" in section_styles[first_numbered_section_idx]:
                    page_number_start = section_styles[first_numbered_section_idx]["pageNumberStart"]
                else:
                    # Continues from previous section, calculate the actual displayed number
                    page_number_start = doc_style_start + numbering_start_page - 1

            if first_numbered_section_idx == 0:
                use_first_page_h_f = doc_style.get("useFirstPageHeaderFooter", False)
                if use_first_page_h_f:
                    first_footer_id = doc_style.get("firstPageFooterId")
                    first_header_id = doc_style.get("firstPageHeaderId")
                    first_page_numbered = False
                    if first_footer_id and first_footer_id in footers:
                        if self._contains_page_number(footers[first_footer_id].get("content", [])):
                            first_page_numbered = True
                    if first_header_id and first_header_id in headers:
                        if self._contains_page_number(headers[first_header_id].get("content", [])):
                            first_page_numbered = True
                    
                    if not first_page_numbered:
                        numbering_start_page = 2
                    else:
                        numbering_start_page = 1
                else:
                    numbering_start_page = 1
            else:
                numbering_start_page = section_start_pages.get(first_numbered_section_idx, 1)
        elif has_page_numbers:
            # Found globally but not in a specific section style explicitly
            # Assume it starts where the first section break is, or page 1
            numbering_start_page = section_start_pages.get(1, 1) if len(section_start_pages) > 1 else 1

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
            numbering_start_page=numbering_start_page,
            text_segments=text_segments,
            paragraph_line_spacings=paragraph_line_spacings,
            fallback_font_family=fallback_font,
            fallback_font_size_pt=fallback_size,
            first_page_break_index=first_page_break_index,
            images=images,
            alignments=alignments,
        )

    def _contains_page_number(self, content: list) -> bool:
        """Check if content recursively contains page number element."""
        for element in content:
            if "paragraph" in element:
                for elem in element["paragraph"].get("elements", []):
                    if "autoText" in elem:
                        auto_text = elem["autoText"]
                        if auto_text.get("type") == "PAGE_NUMBER":
                            return True
            elif "table" in element:
                for row in element["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        if self._contains_page_number(cell.get("content", [])):
                            return True
            elif "tableOfContents" in element:
                if self._contains_page_number(element["tableOfContents"].get("content", [])):
                    return True
        return False

    def _section_has_page_numbers(self, style: dict, headers: dict, footers: dict) -> bool:
        header_ids = [style.get("defaultHeaderId"), style.get("firstPageHeaderId"), style.get("evenPageHeaderId")]
        footer_ids = [style.get("defaultFooterId"), style.get("firstPageFooterId"), style.get("evenPageFooterId")]
        
        for h_id in header_ids:
            if h_id and h_id in headers:
                if self._contains_page_number(headers[h_id].get("content", [])):
                    return True
        for f_id in footer_ids:
            if f_id and f_id in footers:
                if self._contains_page_number(footers[f_id].get("content", [])):
                    return True
        return False


def get_google_docs_service() -> GoogleDocsService:
    """Dependency injection for GoogleDocsService."""
    return GoogleDocsService()


GoogleDocsServiceDependency = Annotated[GoogleDocsService, Depends(get_google_docs_service)]
