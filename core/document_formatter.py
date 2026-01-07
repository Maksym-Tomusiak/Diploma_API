"""
Document Formatter Service - Applies formatting fixes to Google Docs.
"""
from typing import Annotated, Optional, Callable
from dataclasses import dataclass, field
import time

from fastapi import Depends, HTTPException, status
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from common.app_settings import settings
from core.google_docs import GoogleDocsService, GoogleDocsServiceDependency
from schemas.template import TemplateParams


@dataclass
class FormatChange:
    """A formatting change applied to the document."""
    type: str  # e.g., "font_size", "font_family", "line_spacing", "margin"
    description: str
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass
class FormatResult:
    """Result of a format operation."""
    success: bool
    changes_applied: int
    changes: list[FormatChange] = field(default_factory=list)
    processing_time_ms: int = 0
    document_title: Optional[str] = None
    error_message: Optional[str] = None

    def changes_as_dicts(self) -> list[dict]:
        return [
            {
                "type": change.type,
                "description": change.description,
                "before": change.before,
                "after": change.after,
            }
            for change in self.changes
        ]


class DocumentFormatterService:
    """Service for applying formatting to Google Docs."""

    def __init__(self, google_docs_service: GoogleDocsServiceDependency):
        self.google_docs_service = google_docs_service

    def _get_credentials(
        self,
        google_token: str,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str], None]] = None,
    ) -> Credentials:
        """Create Google credentials, refreshing if needed."""
        credentials = Credentials(
            token=google_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        
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

    def format_document(
        self,
        google_token: str,
        doc_id: str,
        params: TemplateParams,
        expected_font_family: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str], None]] = None,
    ) -> FormatResult:
        """
        Apply formatting to a Google Doc.
        
        Args:
            google_token: User's Google OAuth access token
            doc_id: Google Document ID
            params: Expected formatting parameters to apply
            expected_font_family: Font family to apply (optional)
            refresh_token: Google refresh token for auto-refresh (optional)
            on_token_refresh: Callback when token is refreshed (optional)
            
        Returns:
            FormatResult with success status and applied changes
        """
        start_time = time.time()
        changes: list[FormatChange] = []
        
        try:
            credentials = self._get_credentials(google_token, refresh_token, on_token_refresh)
            service = build("docs", "v1", credentials=credentials)
            
            # Get the document first to understand its structure
            document = service.documents().get(documentId=doc_id).execute()
            document_title = document.get("title", "Untitled")
            
            # Get document properties including first page information
            doc_props = self.google_docs_service.get_document_properties(
                google_token=google_token,
                doc_id=doc_id,
                refresh_token=refresh_token,
                on_token_refresh=on_token_refresh
            )
            
            # Build batch update requests
            requests = []
            
            # 1. Update page margins
            margin_request = self._build_margin_request(params)
            if margin_request:
                requests.append(margin_request)
                changes.append(FormatChange(
                    type="margin",
                    description=f"Set margins: top={params.margins.top}mm, bottom={params.margins.bottom}mm, left={params.margins.left}mm, right={params.margins.right}mm",
                ))
            
            # 2. Enable "different first page" if skip_first_page is enabled
            needs_second_pass_for_first_page = False
            if params.skip_first_page:
                # Always set this, even if it's already enabled, to ensure it's properly configured
                requests.append({
                    "updateDocumentStyle": {
                        "documentStyle": {
                            "useFirstPageHeaderFooter": True,
                        },
                        "fields": "useFirstPageHeaderFooter",
                    }
                })
                if not doc_props.first_page_different:
                    changes.append(FormatChange(
                        type="first_page_different",
                        description="Enabled 'Different first page' for headers and footers",
                    ))
                    # If we're enabling different first page now, we need a second pass
                    # to clear the first page footer (it won't exist until after this request)
                    if doc_props.has_page_numbers:
                        needs_second_pass_for_first_page = True
            
            # 3. Handle page numbering (only if NOT needing second pass, or first_page_different already true)
            if not needs_second_pass_for_first_page:
                page_numbering_requests, page_numbering_changes = self._build_page_numbering_requests(
                    document, params, doc_props
                )
                if page_numbering_requests:
                    requests.extend(page_numbering_requests)
                changes.extend(page_numbering_changes)
            else:
                # Still set page number start value
                if params.check_numbering:
                    requests.append({
                        "updateDocumentStyle": {
                            "documentStyle": {
                                "pageNumberStart": params.start_from_number,
                            },
                            "fields": "pageNumberStart",
                        }
                    })
                    changes.append(FormatChange(
                        type="page_number_start",
                        description=f"Set page numbering to start at {params.start_from_number} on page 2 (page 1 has no number)",
                        before=str(doc_props.page_number_start) if doc_props.has_page_numbers else None,
                        after=f"{params.start_from_number} (on page 2)",
                    ))
            
            # 4. Update body text formatting (font size, font family, line spacing)
            body_content = document.get("body", {}).get("content", [])
            text_requests = self._build_text_formatting_requests(
                body_content, 
                params,
                doc_props,
                expected_font_family
            )
            if text_requests:
                requests.extend(text_requests)
                if expected_font_family:
                    changes.append(FormatChange(
                        type="font_family",
                        description=f"Set font family to: {expected_font_family}",
                    ))
                changes.append(FormatChange(
                    type="font_size",
                    description=f"Set font size to: {params.font_size}pt",
                ))
                changes.append(FormatChange(
                    type="line_spacing",
                    description=f"Set line spacing to: {params.line_spacing}",
                ))
            
            # Execute batch update if we have requests
            if requests:
                service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests}
                ).execute()
            
            # Second pass: Clear first page footer if needed
            if needs_second_pass_for_first_page:
                # Re-fetch the document to get the new first page footer ID
                document = service.documents().get(documentId=doc_id).execute()
                second_pass_requests = self._build_clear_first_page_footer_requests(document)
                if second_pass_requests:
                    service.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": second_pass_requests}
                    ).execute()
                    changes.append(FormatChange(
                        type="remove_first_page_number",
                        description="Removed page number from first page (skip first page is enabled)",
                    ))
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return FormatResult(
                success=True,
                changes_applied=len(changes),
                changes=changes,
                processing_time_ms=processing_time,
                document_title=document_title,
            )
            
        except HttpError as e:
            processing_time = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            if e.resp.status == 404:
                error_msg = f"Google Document not found: {doc_id}"
            elif e.resp.status == 403:
                error_msg = "Access denied. Please ensure you have edit permission for this document."
            elif e.resp.status == 401:
                error_msg = "Google authentication expired. Please log in again."
            
            return FormatResult(
                success=False,
                changes_applied=0,
                changes=[],
                processing_time_ms=processing_time,
                error_message=error_msg,
            )
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            return FormatResult(
                success=False,
                changes_applied=0,
                changes=[],
                processing_time_ms=processing_time,
                error_message=str(e),
            )

    def _build_margin_request(self, params: TemplateParams) -> Optional[dict]:
        """Build request to update document margins."""
        # Convert mm to points (1 inch = 72 points, 1 inch = 25.4 mm)
        def mm_to_pt(mm: float) -> float:
            return mm * 72 / 25.4
        
        return {
            "updateDocumentStyle": {
                "documentStyle": {
                    "marginTop": {"magnitude": mm_to_pt(params.margins.top), "unit": "PT"},
                    "marginBottom": {"magnitude": mm_to_pt(params.margins.bottom), "unit": "PT"},
                    "marginLeft": {"magnitude": mm_to_pt(params.margins.left), "unit": "PT"},
                    "marginRight": {"magnitude": mm_to_pt(params.margins.right), "unit": "PT"},
                },
                "fields": "marginTop,marginBottom,marginLeft,marginRight",
            }
        }

    def _build_clear_first_page_footer_requests(self, document: dict) -> list[dict]:
        """
        Build requests to clear page numbers from the first page footer.
        
        This is called after enabling useFirstPageHeaderFooter, so we need
        to re-read the document to get the new first page footer ID.
        
        Returns:
            List of requests to delete page number elements from first page footer
        """
        requests = []
        
        doc_style = document.get("documentStyle", {})
        footers = document.get("footers", {})
        first_page_footer_id = doc_style.get("firstPageFooterId")
        
        if not first_page_footer_id:
            return requests
        
        first_footer = footers.get(first_page_footer_id, {})
        first_footer_content = first_footer.get("content", [])
        
        # Collect all page number autoText elements to delete
        # We need to delete from end to start to maintain correct indices
        elements_to_delete = []
        
        for element in first_footer_content:
            if "paragraph" in element:
                para = element["paragraph"]
                for elem in para.get("elements", []):
                    if "autoText" in elem:
                        auto_text = elem["autoText"]
                        if auto_text.get("type") == "PAGE_NUMBER":
                            start_idx = elem.get("startIndex", 0)
                            end_idx = elem.get("endIndex", 0)
                            if end_idx > start_idx:
                                elements_to_delete.append((start_idx, end_idx))
        
        # Sort by start index descending so we delete from end first
        elements_to_delete.sort(key=lambda x: x[0], reverse=True)
        
        for start_idx, end_idx in elements_to_delete:
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "segmentId": first_page_footer_id,
                        "startIndex": start_idx,
                        "endIndex": end_idx,
                    }
                }
            })
        
        return requests

    def _build_page_numbering_requests(
        self, 
        document: dict, 
        params: TemplateParams,
        doc_props
    ) -> tuple[list[dict], list[FormatChange]]:
        """
        Build requests to apply page numbering settings.
        
        Returns:
            Tuple of (requests, changes) to be added to the batch update
        """
        requests = []
        changes = []
        
        if not params.check_numbering:
            # User doesn't want page numbers checked/set - we won't modify them
            return requests, changes
        
        # Get document structure
        doc_style = document.get("documentStyle", {})
        headers = document.get("headers", {})
        footers = document.get("footers", {})
        has_page_numbers = doc_props.has_page_numbers
        
        # Get footer IDs
        default_footer_id = doc_style.get("defaultFooterId")
        first_page_footer_id = doc_style.get("firstPageFooterId")
        
        # If skip_first_page is enabled and first_page_different is already true,
        # we need to clear the first page footer of any page numbers
        if params.skip_first_page and first_page_footer_id and doc_props.first_page_different:
            # Check if first page footer has page numbers and clear them
            first_footer = footers.get(first_page_footer_id, {})
            first_footer_content = first_footer.get("content", [])
            
            # Collect all page number autoText elements to delete
            elements_to_delete = []
            for element in first_footer_content:
                if "paragraph" in element:
                    para = element["paragraph"]
                    for elem in para.get("elements", []):
                        if "autoText" in elem:
                            auto_text = elem["autoText"]
                            if auto_text.get("type") == "PAGE_NUMBER":
                                start_idx = elem.get("startIndex", 0)
                                end_idx = elem.get("endIndex", 0)
                                if end_idx > start_idx:
                                    elements_to_delete.append((start_idx, end_idx))
            
            # Sort by start index descending so we delete from end first
            elements_to_delete.sort(key=lambda x: x[0], reverse=True)
            
            for start_idx, end_idx in elements_to_delete:
                requests.append({
                    "deleteContentRange": {
                        "range": {
                            "segmentId": first_page_footer_id,
                            "startIndex": start_idx,
                            "endIndex": end_idx,
                        }
                    }
                })
            
            if elements_to_delete:
                changes.append(FormatChange(
                    type="remove_first_page_number",
                    description="Removed page number from first page (skip first page is enabled)",
                ))
        
        # If no page numbers exist, we can't programmatically add them (Google Docs API limitation)
        # but we can configure the settings and inform the user
        if not has_page_numbers:
            # Note: Google Docs API doesn't support inserting autoText (page numbers) directly
            # We can only configure page number settings (start number, skip first page)
            # User will need to manually add page numbers via Insert > Page numbers
            changes.append(FormatChange(
                type="page_numbering_note",
                description="Page numbers need to be added manually: Insert > Page numbers. "
                           f"Settings configured: start at {params.start_from_number}"
                           f"{', skip first page' if params.skip_first_page else ''}",
                before="No page numbers",
                after="Please add page numbers via Insert > Page numbers",
            ))
        
        # Update page number start value if needed
        expected_start = params.start_from_number
        
        # When page numbering check is enabled, always configure the start page
        if has_page_numbers or params.check_numbering:
            # Calculate what pageNumberStart should be set to in Google Docs
            # 
            # If skip_first_page is True (different first page):
            #   - Page 1 has no number (different first page)
            #   - Page 2 shows the value of pageNumberStart
            #   - If user wants page 2 to show "3", we need pageNumberStart = 3
            # 
            # If skip_first_page is False:
            #   - Page 1 shows the value of pageNumberStart
            #   - Set pageNumberStart = expected_start
            
            if params.skip_first_page:
                # With "different first page", page 2 will be the first numbered page
                # Set pageNumberStart to expected_start so page 2 shows that number
                page_number_value = expected_start
                
                # Note: If expected_start > 2, the user wants higher starting number.
                # Page 2 will show that number, page 3 shows expected_start+1, etc.
            else:
                # Without "different first page", page 1 will be the first numbered page
                page_number_value = expected_start
            
            requests.append({
                "updateDocumentStyle": {
                    "documentStyle": {
                        "pageNumberStart": page_number_value,
                    },
                    "fields": "pageNumberStart",
                }
            })
            
            if params.skip_first_page:
                description = f"Set page numbering to start at {expected_start} on page 2 (page 1 has no number)"
                changes.append(FormatChange(
                    type="page_number_start",
                    description=description,
                    before=str(doc_props.page_number_start) if has_page_numbers else None,
                    after=f"{expected_start} (on page 2)",
                ))
            else:
                changes.append(FormatChange(
                    type="page_number_start",
                    description=f"Set page numbering to start at {expected_start}",
                    before=str(doc_props.page_number_start) if has_page_numbers else None,
                    after=str(expected_start),
                ))
        
        return requests, changes

    def _build_text_formatting_requests(
        self,
        body_content: list,
        params: TemplateParams,
        doc_props,  # DocumentProperties from GoogleDocsService
        font_family: Optional[str] = None,
    ) -> list[dict]:
        """Build requests to update text formatting, respecting skip_first_page."""
        requests = []
        
        # Build a map of paragraph indices to their positions
        paragraph_index_map = {}
        for idx, element in enumerate(body_content):
            if "paragraph" in element:
                paragraph_index_map[idx] = element["paragraph"]
        
        # Find all text ranges in the document
        for paragraph_index, element in enumerate(body_content):
            if "paragraph" in element:
                paragraph = element["paragraph"]
                para_style = paragraph.get("paragraphStyle", {})
                named_style = para_style.get("namedStyleType", "NORMAL_TEXT")
                
                # Skip headings - they have their own formatting
                if named_style.startswith("HEADING_"):
                    continue
                
                # Check if this paragraph is on the first page
                is_on_first_page = False
                if params.skip_first_page:
                    # Find this paragraph in doc_props.paragraph_line_spacings
                    for pls in doc_props.paragraph_line_spacings:
                        if pls.paragraph_index == paragraph_index:
                            is_on_first_page = pls.is_on_first_page
                            break
                    
                    # Skip formatting this paragraph if it's on the first page
                    if is_on_first_page:
                        continue
                
                for elem in paragraph.get("elements", []):
                    if "textRun" in elem:
                        start_index = elem.get("startIndex", 0)
                        end_index = elem.get("endIndex", 0)
                        
                        if end_index > start_index:
                            # Build text style update
                            text_style = {
                                "fontSize": {
                                    "magnitude": params.font_size,
                                    "unit": "PT"
                                }
                            }
                            fields = "fontSize"
                            
                            if font_family:
                                text_style["weightedFontFamily"] = {
                                    "fontFamily": font_family,
                                    "weight": 400
                                }
                                fields += ",weightedFontFamily"
                            
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": start_index,
                                        "endIndex": end_index,
                                    },
                                    "textStyle": text_style,
                                    "fields": fields,
                                }
                            })
                
                # Update paragraph line spacing
                start_index = paragraph.get("elements", [{}])[0].get("startIndex", 0)
                end_index = paragraph.get("elements", [{}])[-1].get("endIndex", 0) if paragraph.get("elements") else 0
                
                if end_index > start_index:
                    requests.append({
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": start_index,
                                "endIndex": end_index,
                            },
                            "paragraphStyle": {
                                "lineSpacing": params.line_spacing * 100,  # API uses percentage
                            },
                            "fields": "lineSpacing",
                        }
                    })
        
        return requests


def get_document_formatter_service(
    google_docs_service: GoogleDocsServiceDependency,
) -> DocumentFormatterService:
    """Dependency injection for DocumentFormatterService."""
    return DocumentFormatterService(google_docs_service)


DocumentFormatterServiceDependency = Annotated[
    DocumentFormatterService, Depends(get_document_formatter_service)
]
