"""
Local Document Service - Handles operations on uploaded .docx files.
"""
from typing import Annotated, Optional
from dataclasses import dataclass, field
from io import BytesIO
import time

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_LINE_SPACING
from fastapi import Depends

from core.format_checker import FormatIssue, CheckResult
from core.document_formatter import FormatChange, FormatResult as FormatterResult
from schemas.template import TemplateParams


@dataclass
class LocalTextSegment:
    """Represents a text segment from a local document."""
    content: str
    font_size_pt: Optional[float] = None
    font_family: Optional[str] = None
    char_count: int = 0
    paragraph_index: int = 0
    is_heading: bool = False
    is_on_first_page: bool = True


@dataclass
class LocalDocumentProperties:
    """Properties extracted from a local document."""
    title: str
    text_segments: list[LocalTextSegment] = field(default_factory=list)
    paragraph_line_spacings: list[float] = field(default_factory=list)
    margins: dict[str, float] = field(default_factory=dict)
    page_size: dict[str, float] = field(default_factory=dict)


class LocalDocumentService:
    """Service for working with local .docx files."""

    FONT_SIZE_TOLERANCE = 0.1
    MARGIN_TOLERANCE = 0.5
    LINE_SPACING_TOLERANCE = 0.1

    def extract_document_properties(self, file_content: bytes) -> LocalDocumentProperties:
        """
        Extract formatting properties from a .docx file.

        Args:
            file_content: Raw bytes of the .docx file

        Returns:
            LocalDocumentProperties with extracted formatting information
        """
        doc = Document(BytesIO(file_content))

        # Get document title (from core properties or filename)
        title = doc.core_properties.title or "Untitled Document"

        text_segments = []
        paragraph_line_spacings = []

        # Get page dimensions for first page detection
        section = doc.sections[0] if doc.sections else None
        page_height_inches = section.page_height.inches if section and section.page_height else 11.0
        top_margin_inches = section.top_margin.inches if section and section.top_margin else 1.0
        bottom_margin_inches = section.bottom_margin.inches if section and section.bottom_margin else 1.0
        left_margin_inches = section.left_margin.inches if section and section.left_margin else 1.0
        right_margin_inches = section.right_margin.inches if section and section.right_margin else 1.0
        page_width_inches = section.page_width.inches if section and section.page_width else 8.5

        # Calculate usable dimensions for content on first page
        # Be conservative: reduce by 20% to account for estimation errors and prevent overflow
        usable_page_height_inches = (page_height_inches - top_margin_inches - bottom_margin_inches) * 0.8
        usable_page_width_inches = page_width_inches - left_margin_inches - right_margin_inches

        # Estimate characters per line based on usable width
        # Using conservative estimate: ~8-9 chars per inch for typical 12pt fonts with spacing
        chars_per_line = max(40, int(usable_page_width_inches * 8.5))

        # Track cumulative height to determine first page boundary
        cumulative_height_inches = 0.0

        # Extract text and formatting from paragraphs
        for para_idx, paragraph in enumerate(doc.paragraphs):
            # Check if paragraph is a heading
            is_heading = paragraph.style.name.startswith('Heading')

            # Get line spacing for paragraph
            if paragraph.paragraph_format.line_spacing is not None:
                # line_spacing can be a float (line spacing multiple) or WD_LINE_SPACING enum
                spacing = paragraph.paragraph_format.line_spacing
                if isinstance(spacing, (int, float)):
                    paragraph_line_spacings.append(float(spacing))

            # Estimate paragraph height (very rough approximation)
            # Average font size of runs in paragraph, or default to 12pt
            para_font_sizes = [run.font.size.pt for run in paragraph.runs if run.font.size]
            avg_font_size = sum(para_font_sizes) / len(para_font_sizes) if para_font_sizes else 12.0

            # Line height is approximately font size * line spacing (default 1.15)
            line_spacing_multiple = 1.15
            if paragraph.paragraph_format.line_spacing is not None:
                spacing = paragraph.paragraph_format.line_spacing
                if isinstance(spacing, (int, float)):
                    line_spacing_multiple = float(spacing)

            # Calculate line height in inches (1 pt = 1/72 inch)
            line_height_inches = (avg_font_size / 72.0) * line_spacing_multiple

            # Count approximate lines in paragraph based on actual page width
            para_text_length = len(paragraph.text)
            estimated_lines = max(1, para_text_length // chars_per_line) if para_text_length > 0 else 1

            # Add paragraph height
            para_height_inches = line_height_inches * estimated_lines

            # Add space before/after if specified
            if paragraph.paragraph_format.space_before:
                para_height_inches += paragraph.paragraph_format.space_before.inches
            if paragraph.paragraph_format.space_after:
                para_height_inches += paragraph.paragraph_format.space_after.inches

            # Determine if this paragraph is on first page
            is_on_first_page = cumulative_height_inches < usable_page_height_inches

            # Update cumulative height
            cumulative_height_inches += para_height_inches

            # Extract runs (text segments with consistent formatting)
            for run in paragraph.runs:
                if not run.text.strip():
                    continue

                # Get font size
                font_size = None
                if run.font.size:
                    font_size = run.font.size.pt

                # Get font family - try run font first, then paragraph style, then document default
                font_family = run.font.name
                if not font_family:
                    # Try to get from paragraph style
                    if hasattr(paragraph.style, 'font') and paragraph.style.font.name:
                        font_family = paragraph.style.font.name
                    else:
                        # Default to common document font if not specified
                        font_family = "Calibri"  # Word's default

                segment = LocalTextSegment(
                    content=run.text,
                    font_size_pt=font_size,
                    font_family=font_family,
                    char_count=len(run.text),
                    paragraph_index=para_idx,
                    is_heading=is_heading,
                    is_on_first_page=is_on_first_page,
                )
                text_segments.append(segment)

        # Extract margins (in inches, convert from twips)
        margins = {}
        section = doc.sections[0] if doc.sections else None
        if section:
            margins = {
                "top": section.top_margin.inches if section.top_margin else 1.0,
                "bottom": section.bottom_margin.inches if section.bottom_margin else 1.0,
                "left": section.left_margin.inches if section.left_margin else 1.0,
                "right": section.right_margin.inches if section.right_margin else 1.0,
            }

            # Page size
            page_size = {
                "width": section.page_width.inches if section.page_width else 8.5,
                "height": section.page_height.inches if section.page_height else 11.0,
            }
        else:
            page_size = {"width": 8.5, "height": 11.0}

        return LocalDocumentProperties(
            title=title,
            text_segments=text_segments,
            paragraph_line_spacings=paragraph_line_spacings,
            margins=margins,
            page_size=page_size,
        )

    def check_document(
        self,
        file_content: bytes,
        params: TemplateParams,
        expected_font_family: Optional[str] = None,
    ) -> CheckResult:
        """
        Check a local document's formatting against parameters.

        Args:
            file_content: Raw bytes of the .docx file
            params: Expected formatting parameters
            expected_font_family: Expected font family name

        Returns:
            CheckResult with formatting issues found
        """
        start_time = time.time()
        issues: list[FormatIssue] = []

        doc_props = self.extract_document_properties(file_content)

        # Font Size & Family Checks
        font_size_issues: list[LocalTextSegment] = []
        font_family_issues: list[LocalTextSegment] = []

        for segment in doc_props.text_segments:
            # Skip first page content if requested
            if params.skip_first_page and segment.is_on_first_page:
                print(segment.content)
                continue

            if segment.font_size_pt is not None:
                size_diff = abs(segment.font_size_pt - params.font_size)
                if size_diff > self.FONT_SIZE_TOLERANCE:
                    font_size_issues.append(segment)

            if expected_font_family and segment.font_family:
                if segment.font_family.lower() != expected_font_family.lower():
                    font_family_issues.append(segment)

        # Report Font Size Issues
        if font_size_issues:
            size_groups: dict[float, list[LocalTextSegment]] = {}
            for seg in font_size_issues:
                size = seg.font_size_pt or 0
                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(seg)

            for actual_size, segments in size_groups.items():
                total_chars_this_size = sum(s.char_count for s in segments)
                excerpts = [f'"{s.content[:50]}..."' for s in segments[:3]]
                excerpt_text = ", ".join(excerpts)

                issues.append(FormatIssue(
                    type="font_size_mismatch",
                    severity="high" if abs(actual_size - params.font_size) > 2 else "medium",
                    details=f"Found {total_chars_this_size} characters with font size {actual_size:.1f}pt (expected {params.font_size}pt). Examples: {excerpt_text}",
                    expected=f"{params.font_size}pt",
                    actual=f"{actual_size:.1f}pt",
                ))

        # Report Font Family Issues
        if font_family_issues:
            font_groups: dict[str, list[LocalTextSegment]] = {}
            for seg in font_family_issues:
                font = seg.font_family or "Unknown"
                if font not in font_groups:
                    font_groups[font] = []
                font_groups[font].append(seg)

            for actual_font, segments in font_groups.items():
                total_chars_this_font = sum(s.char_count for s in segments)
                excerpts = [f'"{s.content[:50]}..."' for s in segments[:3]]
                excerpt_text = ", ".join(excerpts)

                issues.append(FormatIssue(
                    type="font_family_mismatch",
                    severity="high",
                    details=f"Found {total_chars_this_font} characters with font '{actual_font}' (expected '{expected_font_family}'). Examples: {excerpt_text}",
                    expected=expected_font_family,
                    actual=actual_font,
                ))

        # Line Spacing Checks
        if doc_props.paragraph_line_spacings:
            wrong_spacing_values: dict[float, int] = {}
            for spacing in doc_props.paragraph_line_spacings:
                spacing_diff = abs(spacing - params.line_spacing)
                if spacing_diff > self.LINE_SPACING_TOLERANCE:
                    wrong_spacing_values[spacing] = wrong_spacing_values.get(spacing, 0) + 1

            for actual_spacing, count in wrong_spacing_values.items():
                issues.append(FormatIssue(
                    type="line_spacing_mismatch",
                    severity="medium",
                    details=f"{count} paragraphs have line spacing {actual_spacing:.2f} (expected {params.line_spacing:.2f})",
                    expected=f"{params.line_spacing:.2f}",
                    actual=f"{actual_spacing:.2f}",
                ))

        # Margin Checks
        if doc_props.margins:
            for margin_name, actual_value in doc_props.margins.items():
                expected_value = getattr(params, f"margin_{margin_name}", None)
                if expected_value is not None:
                    diff = abs(actual_value - expected_value)
                    if diff > self.MARGIN_TOLERANCE:
                        issues.append(FormatIssue(
                            type=f"margin_{margin_name}_mismatch",
                            severity="medium",
                            details=f"{margin_name.capitalize()} margin is {actual_value:.2f}\" (expected {expected_value:.2f}\")",
                            expected=f"{expected_value:.2f}\"",
                            actual=f"{actual_value:.2f}\"",
                        ))

        # Calculate score
        if not doc_props.text_segments:
            issues.append(FormatIssue(
                type="no_text_found",
                severity="low",
                details="No text content found in document",
            ))

        # Score calculation
        critical_issues = len([i for i in issues if i.severity == "high"])
        medium_issues = len([i for i in issues if i.severity == "medium"])
        low_issues = len([i for i in issues if i.severity == "low"])

        total_checks = max(1, critical_issues + medium_issues + low_issues + 10)
        penalty = (critical_issues * 3) + (medium_issues * 1.5) + (low_issues * 0.5)
        overall_score = max(0.0, (total_checks - penalty) / total_checks)  # Return as fraction 0.0-1.0

        processing_time = int((time.time() - start_time) * 1000)

        return CheckResult(
            passed=len(issues) == 0,
            overall_score=overall_score,
            issues=issues,
            processing_time_ms=processing_time,
            document_title=doc_props.title,
        )
    def format_document(
        self,
        file_content: bytes,
        params: TemplateParams,
        expected_font_family: Optional[str] = None,
    ) -> tuple[bytes, FormatterResult]:
        """
        Apply formatting to a local document and return the modified file.
        
        Args:
            file_content: Raw bytes of the .docx file
            params: Formatting parameters to apply
            expected_font_family: Font family to apply
            
        Returns:
            Tuple of (modified_file_bytes, FormatterResult)
        """
        start_time = time.time()
        changes: list[FormatChange] = []
        
        doc = Document(BytesIO(file_content))
        doc_title = doc.core_properties.title or "Untitled Document"
        
        # Apply formatting to all paragraphs
        for paragraph in doc.paragraphs:
            # Skip headings if needed
            is_heading = paragraph.style.name.startswith('Heading')
            
            # Apply line spacing
            if paragraph.paragraph_format.line_spacing != params.line_spacing:
                old_spacing = paragraph.paragraph_format.line_spacing
                paragraph.paragraph_format.line_spacing = params.line_spacing
                changes.append(FormatChange(
                    type="line_spacing",
                    description=f"Updated line spacing for paragraph",
                    before=f"{old_spacing:.2f}" if old_spacing else "unset",
                    after=f"{params.line_spacing:.2f}",
                ))
            
            # Apply formatting to runs
            for run in paragraph.runs:
                if not run.text.strip() or (is_heading and not params.skip_first_page):
                    continue
                
                # Apply font size
                if run.font.size:
                    old_size = run.font.size.pt
                    if abs(old_size - params.font_size) > self.FONT_SIZE_TOLERANCE:
                        run.font.size = Pt(params.font_size)
                        changes.append(FormatChange(
                            type="font_size",
                            description=f"Changed font size",
                            before=f"{old_size:.1f}pt",
                            after=f"{params.font_size}pt",
                        ))
                else:
                    run.font.size = Pt(params.font_size)
                    changes.append(FormatChange(
                        type="font_size",
                        description=f"Set font size",
                        before="unset",
                        after=f"{params.font_size}pt",
                    ))
                
                # Apply font family
                if expected_font_family:
                    old_font = run.font.name
                    if old_font != expected_font_family:
                        run.font.name = expected_font_family
                        changes.append(FormatChange(
                            type="font_family",
                            description=f"Changed font family",
                            before=old_font or "unset",
                            after=expected_font_family,
                        ))
        
        # Apply margins
        if doc.sections:
            section = doc.sections[0]
            
            # Top margin
            if hasattr(params, 'margin_top'):
                from docx.shared import Inches
                old_top = section.top_margin.inches if section.top_margin else 1.0
                if abs(old_top - params.margin_top) > self.MARGIN_TOLERANCE:
                    section.top_margin = Inches(params.margin_top)
                    changes.append(FormatChange(
                        type="margin_top",
                        description="Updated top margin",
                        before=f"{old_top:.2f}\"",
                        after=f"{params.margin_top:.2f}\"",
                    ))
            
            # Bottom margin
            if hasattr(params, 'margin_bottom'):
                from docx.shared import Inches
                old_bottom = section.bottom_margin.inches if section.bottom_margin else 1.0
                if abs(old_bottom - params.margin_bottom) > self.MARGIN_TOLERANCE:
                    section.bottom_margin = Inches(params.margin_bottom)
                    changes.append(FormatChange(
                        type="margin_bottom",
                        description="Updated bottom margin",
                        before=f"{old_bottom:.2f}\"",
                        after=f"{params.margin_bottom:.2f}\"",
                    ))
            
            # Left margin
            if hasattr(params, 'margin_left'):
                from docx.shared import Inches
                old_left = section.left_margin.inches if section.left_margin else 1.0
                if abs(old_left - params.margin_left) > self.MARGIN_TOLERANCE:
                    section.left_margin = Inches(params.margin_left)
                    changes.append(FormatChange(
                        type="margin_left",
                        description="Updated left margin",
                        before=f"{old_left:.2f}\"",
                        after=f"{params.margin_left:.2f}\"",
                    ))
            
            # Right margin
            if hasattr(params, 'margin_right'):
                from docx.shared import Inches
                old_right = section.right_margin.inches if section.right_margin else 1.0
                if abs(old_right - params.margin_right) > self.MARGIN_TOLERANCE:
                    section.right_margin = Inches(params.margin_right)
                    changes.append(FormatChange(
                        type="margin_right",
                        description="Updated right margin",
                        before=f"{old_right:.2f}\"",
                        after=f"{params.margin_right:.2f}\"",
                    ))
        
        # Save modified document to bytes
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        modified_content = output.getvalue()
        
        processing_time = int((time.time() - start_time) * 1000)
        
        result = FormatterResult(
            success=True,
            changes_applied=len(changes),
            changes=changes,
            processing_time_ms=processing_time,
            document_title=doc_title,
        )
        
        return modified_content, result


# Dependency for FastAPI
LocalDocumentServiceDependency = Annotated[LocalDocumentService, Depends(LocalDocumentService)]
