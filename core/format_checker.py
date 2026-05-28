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
    type: str
    severity: str
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
    overall_score: float
    issues: list[FormatIssue] = field(default_factory=list)
    processing_time_ms: int = 0
    document_title: Optional[str] = None

    def issues_as_dicts(self) -> list[dict]:
        return [issue.to_dict() for issue in self.issues]


class FormatCheckerService:
    """Service for checking document formatting against templates or custom parameters."""

    FONT_SIZE_TOLERANCE = 0.01
    MARGIN_TOLERANCE = 0.1
    LINE_SPACING_TOLERANCE = 0.01

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
        start_time = time.time()
        issues: list[FormatIssue] = []
        
        doc_props = self.google_docs_service.get_document_properties(
            google_token, 
            doc_id,
            refresh_token=refresh_token,
            on_token_refresh=on_token_refresh
        )
        
        # --- Font Size & Family Checks (Unchanged) ---
        font_size_issues: list[TextSegment] = []
        font_family_issues: list[TextSegment] = []
        
        for segment in doc_props.text_segments:
            if params.skip_first_page and segment.is_on_first_page:
                continue
            
            if segment.font_size_pt is not None:
                size_diff = abs(segment.font_size_pt - params.font_size)
                if size_diff > self.FONT_SIZE_TOLERANCE:
                    font_size_issues.append(segment)
            
            if expected_font_family and segment.font_family:
                if segment.font_family.lower() != expected_font_family.lower():
                    font_family_issues.append(segment)
        
        # Reporting Font Issues
        if font_size_issues:
            size_groups: dict[float, list[TextSegment]] = {}
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
                    details=f"Знайдено {total_chars_this_size} символів з розміром шрифту {actual_size:.1f}pt (очікувалося {params.font_size}pt). Приклади: {excerpt_text}",
                    expected=f"{params.font_size}pt",
                    actual=f"{actual_size:.1f}pt",
                ))
        
        if font_family_issues:
            font_groups: dict[str, list[TextSegment]] = {}
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
                    details=f"Знайдено {total_chars_this_font} символів зі шрифтом '{actual_font}' (очікувалося '{expected_font_family}'). Приклади: {excerpt_text}",
                    expected=expected_font_family,
                    actual=actual_font,
                ))

        if not doc_props.text_segments:
            issues.append(FormatIssue(
                type="no_text_found",
                severity="low",
                details="У документі не знайдено текстового вмісту",
            ))
        
        # --- Line Spacing Checks (Unchanged) ---
        if doc_props.paragraph_line_spacings:
            wrong_spacing_values: dict[float, int] = {}
            for pls in doc_props.paragraph_line_spacings:
                if params.skip_first_page and pls.is_on_first_page:
                    continue
                
                spacing_diff = abs(pls.line_spacing - params.line_spacing)
                if spacing_diff > self.LINE_SPACING_TOLERANCE:
                    wrong_spacing_values[pls.line_spacing] = wrong_spacing_values.get(pls.line_spacing, 0) + 1
            
            for actual_spacing, count in wrong_spacing_values.items():
                issues.append(FormatIssue(
                    type="line_spacing_mismatch",
                    severity="medium",
                    details=f"Знайдено {count} абзац(ів) з міжрядковим інтервалом {actual_spacing:.2f} (очікувалося {params.line_spacing})",
                    expected=f"{params.line_spacing}",
                    actual=f"{actual_spacing:.2f}",
                ))
        
        # --- Margin Checks (Unchanged) ---
        self._check_margin(issues, "top", doc_props.margin_top_mm(), params.margins.top)
        self._check_margin(issues, "bottom", doc_props.margin_bottom_mm(), params.margins.bottom)
        self._check_margin(issues, "left", doc_props.margin_left_mm(), params.margins.left)
        self._check_margin(issues, "right", doc_props.margin_right_mm(), params.margins.right)
        
        # --- Image and Caption Checks ---
        import re
        # Strict pattern for Рис. X.X. (exactly two numbers)
        caption_pattern = re.compile(r'^(Рис\.|Зоб\.|Фото|Рисунок)\s+\d+\.\d+\.?\s+.+')
        
        for img in doc_props.images:
            if params.skip_first_page and img.is_on_first_page:
                continue
                
            # 1. Image alignment
            if img.alignment != 'CENTER':
                # Try to get caption for better identification
                caption_para = next((a for a in doc_props.alignments if a.paragraph_index == img.paragraph_index + 1), None)
                img_ref = "Зображення"
                if caption_para and caption_para.text:
                    # Extract the first part like "Рис. 1.1."
                    match = re.match(r'^(Рис\.|Зоб\.|Рисунок|Фото)\s+\d+\.\d+\.?\s*', caption_para.text)
                    if match:
                        img_ref = match.group(0).strip()
                    else:
                        img_ref = f"Зображення '{caption_para.text[:20]}...'"

                issues.append(FormatIssue(
                    type="image_alignment_error",
                    severity="medium",
                    details=f"{img_ref} має бути вирівняно по центру",
                    expected="CENTER",
                    actual=img.alignment
                ))
            
            # 2. Check for caption (next paragraph)
            caption_para = next((a for a in doc_props.alignments if a.paragraph_index == img.paragraph_index + 1), None)
            if not caption_para or not caption_para.text:
                issues.append(FormatIssue(
                    type="image_caption_missing",
                    severity="high",
                    details=f"Відсутній підпис під зображенням у параграфі {img.paragraph_index + 2}",
                    expected="Рис. X.X. Назва",
                    actual="порожньо"
                ))
            else:
                # Split by newline to check if source is in the same paragraph (Shift+Enter case)
                import re
                para_lines = re.split(r'[\n\r\v\u000b]', caption_para.text)
                caption_lines = []
                source_line = None
                for line in para_lines:
                    cleaned_line = line.strip()
                    if not cleaned_line:
                        continue
                    if cleaned_line.lower().startswith("джерело:"):
                        source_line = cleaned_line
                    else:
                        caption_lines.append(cleaned_line)
                
                caption_text = " ".join(caption_lines) if caption_lines else caption_para.text

                # Check format
                if not caption_pattern.match(caption_text):
                    issues.append(FormatIssue(
                        type="image_caption_format_error",
                        severity="low",
                        details=f"Неправильний формат підпису: '{caption_text[:30]}...'. Очікується: 'Рис. X.X. Опис'",
                        expected="Рис. X.X. Назва",
                        actual=caption_text[:30]
                    ))
                
                # Check alignment
                if caption_para.alignment != "CENTER":
                    issues.append(FormatIssue(
                        type="image_caption_alignment_error",
                        severity="low",
                        details=f"Підпис під зображенням '{caption_text[:20]}' має бути відцентрований",
                        expected="CENTER",
                        actual=caption_para.alignment
                    ))

                # 3. Check for source (either embedded or in the paragraph after caption)
                if source_line is not None:
                    # Source is embedded in the caption paragraph
                    # Check format
                    if not source_line.lower().startswith("джерело:"):
                        issues.append(FormatIssue(
                            type="image_source_format_error",
                            severity="low",
                            details=f"Неправильний формат джерела: '{source_line[:30]}...'. Очікується: 'Джерело: опис'",
                            expected="Джерело: ...",
                            actual=source_line[:30]
                        ))
                    else:
                        # Check alignment
                        if caption_para.alignment != "CENTER":
                            issues.append(FormatIssue(
                                type="image_source_alignment_error",
                                severity="low",
                                details=f"Рядок джерела '{source_line[:20]}' має бути відцентрований",
                                expected="CENTER",
                                actual=caption_para.alignment
                            ))
                        # Check italic
                        if not caption_para.is_italic:
                            issues.append(FormatIssue(
                                type="image_source_style_error",
                                severity="low",
                                details=f"Рядок джерела '{source_line[:20]}' має бути написаний курсивом",
                                expected="italic",
                                actual="normal"
                            ))
                else:
                    # Source is in the paragraph after caption
                    source_para = next((a for a in doc_props.alignments if a.paragraph_index == img.paragraph_index + 2), None)
                    if not source_para or not source_para.text:
                        issues.append(FormatIssue(
                            type="image_source_missing",
                            severity="medium",
                            details=f"Відсутнє джерело під зображенням '{caption_text[:20]}...'",
                            expected="Джерело: розроблено автором (або інше)",
                            actual="порожньо"
                        ))
                    elif not source_para.text.lower().startswith("джерело:"):
                        issues.append(FormatIssue(
                            type="image_source_format_error",
                            severity="low",
                            details=f"Неправильний формат джерела: '{source_para.text[:30]}...'. Очікується: 'Джерело: опис'",
                            expected="Джерело: ...",
                            actual=source_para.text[:30]
                        ))
                    else:
                        # Check alignment
                        if source_para.alignment != "CENTER":
                            issues.append(FormatIssue(
                                type="image_source_alignment_error",
                                severity="low",
                                details=f"Рядок джерела '{source_para.text[:20]}' має бути відцентрований",
                                expected="CENTER",
                                actual=source_para.alignment
                            ))
                        # Check italic
                        if not source_para.is_italic:
                            issues.append(FormatIssue(
                                type="image_source_style_error",
                                severity="low",
                                details=f"Рядок джерела '{source_para.text[:20]}' має бути написаний курсивом",
                                expected="italic",
                                actual="normal"
                            ))
        
        # --- Page Numbering Checks (Updated) ---
        if params.check_numbering:
            if not doc_props.has_page_numbers:
                issues.append(FormatIssue(
                    type="page_numbering_missing",
                    severity="medium",
                    details="У документі відсутня нумерація сторінок, хоча вона є обов'язковою",
                    expected="Нумерація сторінок увімкнена",
                    actual="Нумерацію не знайдено",
                ))
            else:
                # Support numbering_start_page generically with backward compatibility for skip_first_page
                expected_start_page = params.numbering_start_page
                if params.skip_first_page and expected_start_page == 1:
                    expected_start_page = 2
                expected_start_number = params.start_from_number
                actual_start_page = doc_props.numbering_start_page
                actual_start_number = doc_props.page_number_start
                
                # Check 1: Start Page mismatch
                if actual_start_page != expected_start_page:
                    if expected_start_page == 2:
                        issues.append(FormatIssue(
                            type="page_numbering_on_first_page",
                            severity="high",
                            details=f"На 1-й сторінці відображається номер сторінки, але нумерація повинна починатися з 2-ї сторінки. Увімкніть 'Окрема перша сторінка' в налаштуваннях макета Google Docs.",
                            expected="Стор 1: без номера, Стор 2: номер",
                            actual=f"Стор 1: номер {actual_start_number}",
                        ))
                    elif expected_start_page == 1:
                        issues.append(FormatIssue(
                            type="page_numbering_first_page_different",
                            severity="medium",
                            details="Перша сторінка встановлена як окрема (нумерація прихована), хоча очікується нумерація з 1-ї сторінки. Будь ласка, вимкніть 'Окрема перша сторінка' у параметрах макета Google Docs.",
                            expected="Нумерація з 1-ї сторінки",
                            actual="Нумерація прихована на 1-й сторінці",
                        ))
                    else:
                        issues.append(FormatIssue(
                            type="page_numbering_start_page_mismatch",
                            severity="medium",
                            details=f"Нумерація починається зі сторінки {actual_start_page}, а очікувалося зі сторінки {expected_start_page}.",
                            expected=f"Початок нумерації на сторінці {expected_start_page}",
                            actual=f"Початок нумерації на сторінці {actual_start_page}",
                        ))
                
                actual_start_number_attr = doc_props.page_number_start
                if actual_start_number_attr is not None:
                    actual_displayed_number = actual_start_number_attr
                else:
                    actual_displayed_number = max(1, actual_start_page)
                if actual_displayed_number != expected_start_number:
                    doc_suggested = expected_start_number - actual_start_page + 1 if actual_start_page >= 1 else expected_start_number
                    if doc_suggested <= 0:
                        suggested_text = f"на {expected_start_number} (увімкнувши 'Почати нову нумерацію' для цього розділу)"
                    else:
                        suggested_text = f"на {doc_suggested} (або {expected_start_number} якщо це новий розділ)"
                    
                    issues.append(FormatIssue(
                        type="page_number_start_mismatch",
                        severity="medium",
                        details=f"На першій пронумерованій сторінці відображається номер {actual_displayed_number}, а очікувався номер {expected_start_number}. У Google Docs перейдіть у Вставка > Номери сторінок > Додаткові параметри та встановіть 'Почати з' {suggested_text}.",
                        expected=str(expected_start_number),
                        actual=str(actual_displayed_number),
                    ))

        # Calculate score
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        score = 1.0
        for issue in issues:
            if issue.severity == "high":
                score -= 0.15
            elif issue.severity == "medium":
                score -= 0.08
            else:
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
        margin_translations = {
            "top": "Верхнє поле",
            "bottom": "Нижнє поле",
            "left": "Ліве поле",
            "right": "Праве поле"
        }
        translated_name = margin_translations.get(margin_name, margin_name.capitalize())
        
        margin_diff = abs(actual_mm - expected_mm)
        if margin_diff > self.MARGIN_TOLERANCE:
            issues.append(FormatIssue(
                type=f"margin_{margin_name}_mismatch",
                severity="medium" if margin_diff > 5 else "low",
                details=f"{translated_name} ({actual_mm:.1f}мм) не відповідає очікуваному значенню ({expected_mm}мм)",
                expected=f"{expected_mm}мм",
                actual=f"{actual_mm:.1f}мм",
            ))


def get_format_checker_service(
    google_docs_service: GoogleDocsServiceDependency,
) -> FormatCheckerService:
    return FormatCheckerService(google_docs_service)


FormatCheckerServiceDependency = Annotated[FormatCheckerService, Depends(get_format_checker_service)]