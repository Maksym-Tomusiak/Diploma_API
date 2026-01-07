"""
Format Checker Service - Compares document properties against expected formatting rules.
"""
from typing import Annotated, Optional, Callable
from dataclasses import dataclass, field
import time

from fastapi import Depends

from core.google_docs import GoogleDocsService, GoogleDocsServiceDependency, DocumentProperties, TextSegment
from schemas.template import TemplateParams


@dataclass
class FormatIssue:
    """A formatting issue found during check."""
    type: str  # e.g., "font_size_mismatch", "margin_error", "line_spacing_mismatch"
    severity: str  # "low", "medium", "high"
    details: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "details": self.details,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class CheckResult:
    """Result of a format check operation."""
    passed: bool
    overall_score: float  # 0.0 - 1.0
    issues: list[FormatIssue] = field(default_factory=list)
    processing_time_ms: int = 0
    document_title: Optional[str] = None

    def issues_as_dicts(self) -> list[dict]:
        return [issue.to_dict() for issue in self.issues]


class FormatCheckerService:
    """Service for checking document formatting against templates or custom parameters."""

    # Tolerance values for comparison
    FONT_SIZE_TOLERANCE = 0.1  # points
    MARGIN_TOLERANCE = 0.5  # mm
    LINE_SPACING_TOLERANCE = 0.1

    def __init__(self, google_docs_service: GoogleDocsServiceDependency):
        self.google_docs_service = google_docs_service

    def check_document(
        self,
        google_token: str,
        doc_id: str,
        params: TemplateParams,
        expected_font_family: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str], None]] = None,
    ) -> CheckResult:
        """
        Check a document's formatting against expected parameters.
        
        Args:
            google_token: User's Google OAuth access token
            doc_id: Google Document ID
            params: Expected formatting parameters
            expected_font_family: Expected font family name (optional)
            refresh_token: Google refresh token for auto-refresh (optional)
            on_token_refresh: Callback when token is refreshed (optional)
            
        Returns:
            CheckResult with pass/fail status, score, and issues list
        """
        start_time = time.time()
        issues: list[FormatIssue] = []
        
        # Fetch document properties
        doc_props = self.google_docs_service.get_document_properties(
            google_token, 
            doc_id,
            refresh_token=refresh_token,
            on_token_refresh=on_token_refresh
        )
        
        # Check ALL text segments for font size and font family issues
        # Skip headings as they typically have different formatting
        font_size_issues: list[TextSegment] = []
        font_family_issues: list[TextSegment] = []
        total_chars = 0
        chars_with_wrong_size = 0
        chars_with_wrong_font = 0
        
        for segment in doc_props.text_segments:
            # Skip headings - they have their own styles
            if segment.is_heading:
                continue
            
            # Skip first page content if requested
            if params.skip_first_page and segment.is_on_first_page:
                continue
                
            total_chars += segment.char_count
            
            # Check font size
            if segment.font_size_pt is not None:
                size_diff = abs(segment.font_size_pt - params.font_size)
                if size_diff > self.FONT_SIZE_TOLERANCE:
                    font_size_issues.append(segment)
                    chars_with_wrong_size += segment.char_count
            
            # Check font family
            if expected_font_family and segment.font_family:
                if segment.font_family.lower() != expected_font_family.lower():
                    font_family_issues.append(segment)
                    chars_with_wrong_font += segment.char_count
        
        # Report font size issues (group by actual size for cleaner output)
        if font_size_issues:
            # Group issues by font size
            size_groups: dict[float, list[TextSegment]] = {}
            for seg in font_size_issues:
                size = seg.font_size_pt or 0
                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(seg)
            
            for actual_size, segments in size_groups.items():
                total_chars_this_size = sum(s.char_count for s in segments)
                # Create excerpt from first few segments
                excerpts = []
                for seg in segments[:3]:
                    excerpt = seg.content[:50] + "..." if len(seg.content) > 50 else seg.content
                    excerpts.append(f'"{excerpt}"')
                excerpt_text = ", ".join(excerpts)
                if len(segments) > 3:
                    excerpt_text += f" and {len(segments) - 3} more segments"
                
                issues.append(FormatIssue(
                    type="font_size_mismatch",
                    severity="high" if abs(actual_size - params.font_size) > 2 else "medium",
                    details=f"Found {total_chars_this_size} characters with font size {actual_size:.1f}pt (expected {params.font_size}pt). Examples: {excerpt_text}",
                    expected=f"{params.font_size}pt",
                    actual=f"{actual_size:.1f}pt",
                ))
        
        # Report font family issues (group by actual font)
        if font_family_issues:
            # Group issues by font family
            font_groups: dict[str, list[TextSegment]] = {}
            for seg in font_family_issues:
                font = seg.font_family or "Unknown"
                if font not in font_groups:
                    font_groups[font] = []
                font_groups[font].append(seg)
            
            for actual_font, segments in font_groups.items():
                total_chars_this_font = sum(s.char_count for s in segments)
                # Create excerpt from first few segments
                excerpts = []
                for seg in segments[:3]:
                    excerpt = seg.content[:50] + "..." if len(seg.content) > 50 else seg.content
                    excerpts.append(f'"{excerpt}"')
                excerpt_text = ", ".join(excerpts)
                if len(segments) > 3:
                    excerpt_text += f" and {len(segments) - 3} more segments"
                
                issues.append(FormatIssue(
                    type="font_family_mismatch",
                    severity="high",
                    details=f"Found {total_chars_this_font} characters with font '{actual_font}' (expected '{expected_font_family}'). Examples: {excerpt_text}",
                    expected=expected_font_family,
                    actual=actual_font,
                ))
        
        # Report if no text segments found
        if not doc_props.text_segments:
            issues.append(FormatIssue(
                type="no_text_found",
                severity="low",
                details="No text content found in document",
            ))
        
        # Check line spacing for paragraphs (skip first page if requested)
        if doc_props.paragraph_line_spacings:
            wrong_spacing_values: dict[float, int] = {}  # spacing -> count of paragraphs
            checked_count = 0
            skipped_count = 0
            
            for pls in doc_props.paragraph_line_spacings:
                # Skip first page paragraphs if requested
                if params.skip_first_page and pls.is_on_first_page:
                    skipped_count += 1
                    continue
                
                checked_count += 1
                spacing_diff = abs(pls.line_spacing - params.line_spacing)
                if spacing_diff > self.LINE_SPACING_TOLERANCE:
                    wrong_spacing_values[pls.line_spacing] = wrong_spacing_values.get(pls.line_spacing, 0) + 1
            
            for actual_spacing, count in wrong_spacing_values.items():
                issues.append(FormatIssue(
                    type="line_spacing_mismatch",
                    severity="medium",
                    details=f"Found {count} paragraph(s) with line spacing {actual_spacing:.2f} (expected {params.line_spacing})",
                    expected=f"{params.line_spacing}",
                    actual=f"{actual_spacing:.2f}",
                ))
        else:
            issues.append(FormatIssue(
                type="line_spacing_unknown",
                severity="low",
                details="Could not determine document line spacing",
            ))
        
        # Check margins
        self._check_margin(issues, "top", doc_props.margin_top_mm(), params.margins.top)
        self._check_margin(issues, "bottom", doc_props.margin_bottom_mm(), params.margins.bottom)
        self._check_margin(issues, "left", doc_props.margin_left_mm(), params.margins.left)
        self._check_margin(issues, "right", doc_props.margin_right_mm(), params.margins.right)
        
        # Check page numbering
        if params.check_numbering:
            if not doc_props.has_page_numbers:
                issues.append(FormatIssue(
                    type="page_numbering_missing",
                    severity="medium",
                    details="Document does not have page numbers, but they are required",
                    expected="Page numbers enabled",
                    actual="No page numbers found",
                ))
            else:
                # Check page numbering configuration
                expected_start = params.start_from_number
                actual_start = doc_props.page_number_start
                
                # If skip_first_page is enabled, page 1 should have no number
                # and page 2 should show the start_from_number value
                if params.skip_first_page:
                    if doc_props.first_page_different:
                        # First page is different (no number) - check if page 2 shows correct number
                        if actual_start != expected_start:
                            issues.append(FormatIssue(
                                type="page_number_start_mismatch",
                                severity="medium",
                                details=f"First numbered page (page 2) shows number {actual_start}, but expected {expected_start}. In Google Docs, go to Insert > Page numbers > More options, and set 'Start at' to {expected_start}",
                                expected=str(expected_start),
                                actual=str(actual_start),
                            ))
                    else:
                        # skip_first_page is enabled but first_page_different is False
                        # This means page 1 has a number, which is wrong!
                        issues.append(FormatIssue(
                            type="page_numbering_on_first_page",
                            severity="high",
                            details=f"Page 1 shows number {actual_start}, but should have no number (skip first page is enabled). Enable 'Different first page' in Google Docs layout settings.",
                            expected=f"Page 1: no number, Page 2: number {expected_start}",
                            actual=f"Page 1: number {actual_start}",
                        ))
                else:
                    # Normal case: page 1 shows the start_from_number value
                    if actual_start != expected_start:
                        issues.append(FormatIssue(
                            type="page_number_start_mismatch",
                            severity="low",
                            details=f"Page numbering starts at {actual_start}, expected {expected_start}",
                            expected=str(expected_start),
                            actual=str(actual_start),
                        ))
        
        # Check skip first page setting (for headers/footers)
        if params.skip_first_page:
            if not doc_props.first_page_different:
                issues.append(FormatIssue(
                    type="first_page_not_different",
                    severity="high",
                    details="First page should be different (skip first page is enabled) but document doesn't have this setting. In Google Docs, go to Format > Page setup, then enable 'Different first page'.",
                    expected="First page header/footer different",
                    actual="First page uses same header/footer",
                ))
                
                # Additionally, if numbering check is enabled, page 1 will incorrectly show a number
                if params.check_numbering and doc_props.has_page_numbers:
                    issues.append(FormatIssue(
                        type="page_1_has_incorrect_number",
                        severity="high",
                        details=f"Page 1 incorrectly shows page number {doc_props.page_number_start}. It should have no number when 'skip first page' is enabled.",
                        expected="Page 1: no number",
                        actual=f"Page 1: number {doc_props.page_number_start}",
                    ))
        
        # Calculate score
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Score calculation: start at 1.0, subtract for each issue based on severity
        score = 1.0
        for issue in issues:
            if issue.severity == "high":
                score -= 0.15
            elif issue.severity == "medium":
                score -= 0.08
            else:  # low
                score -= 0.03
        
        score = max(0.0, min(1.0, score))
        passed = score >= 0.98 and not any(i.severity == "high" for i in issues)
        
        return CheckResult(
            passed=passed,
            overall_score=round(score, 2),
            issues=issues,
            processing_time_ms=processing_time_ms,
            document_title=doc_props.title,
        )

    def _check_margin(
        self,
        issues: list[FormatIssue],
        margin_name: str,
        actual_mm: float,
        expected_mm: float,
    ) -> None:
        """Check a single margin and add issue if mismatch."""
        margin_diff = abs(actual_mm - expected_mm)
        if margin_diff > self.MARGIN_TOLERANCE:
            issues.append(FormatIssue(
                type=f"margin_{margin_name}_mismatch",
                severity="medium" if margin_diff > 5 else "low",
                details=f"{margin_name.capitalize()} margin ({actual_mm:.1f}mm) does not match expected ({expected_mm}mm)",
                expected=f"{expected_mm}mm",
                actual=f"{actual_mm:.1f}mm",
            ))


def get_format_checker_service(
    google_docs_service: GoogleDocsServiceDependency,
) -> FormatCheckerService:
    """Dependency injection for FormatCheckerService."""
    return FormatCheckerService(google_docs_service)


FormatCheckerServiceDependency = Annotated[FormatCheckerService, Depends(get_format_checker_service)]
