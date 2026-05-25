import os
import tempfile
import subprocess
import logging

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)

def get_page_start_text_via_pdf(docx_bytes: bytes, target_page_index: int, max_words: int = 15) -> str | None:
    """
    Converts a docx document to PDF using LibreOffice and returns the first few words 
    of the specified physical page (0-indexed).
    This helps in mapping physical pages back to the original docx paragraphs.
    """
    if fitz is None:
        logger.error("PyMuPDF (fitz) is not installed.")
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        docx_path = os.path.join(temp_dir, "temp.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
            
        # Run LibreOffice to convert
        try:
            # Note: on Windows it might be 'soffice', on Linux 'libreoffice'
            command = [
                "libreoffice", "--headless", "--convert-to", "pdf", 
                docx_path, "--outdir", temp_dir
            ]
            
            try:
                subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                # Fallback for Windows if 'libreoffice' is not in PATH but 'soffice' is
                command[0] = "soffice"
                try:
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except FileNotFoundError:
                    if os.name == 'nt':
                        win_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
                        if os.path.exists(win_path):
                            command[0] = win_path
                            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        else:
                            raise
                    else:
                        raise
                
        except subprocess.CalledProcessError as e:
            logger.error(f"LibreOffice conversion failed: {e.stderr.decode('utf-8', errors='ignore')}")
            return None
        except Exception as e:
            logger.error(f"Failed to run LibreOffice: {e}")
            return None
            
        pdf_path = os.path.join(temp_dir, "temp.pdf")
        if not os.path.exists(pdf_path):
            logger.error("PDF was not created by LibreOffice.")
            return None
            
        try:
            doc = fitz.open(pdf_path)
            if target_page_index < 0 or target_page_index >= len(doc):
                logger.warning(f"Target page index {target_page_index} is out of bounds (total pages: {len(doc)}).")
                doc.close()
                return None
                
            page = doc[target_page_index]
            text = page.get_text("text").strip()
            doc.close()
            
            if not text:
                return ""
                
            # Take the first few words
            words = text.split()
            first_words = " ".join(words[:max_words])
            return first_words
            
        except Exception as e:
            logger.error(f"Failed to read PDF with PyMuPDF: {e}")
            return None

def find_text_in_pdf_pages(docx_bytes: bytes, target_text: str) -> int | None:
    """
    Converts a docx document to PDF and finds the 1-indexed page number where 
    the target_text appears.
    """
    if fitz is None:
        logger.error("PyMuPDF (fitz) is not installed.")
        return None
        
    if not target_text.strip():
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        docx_path = os.path.join(temp_dir, "temp.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
            
        try:
            command = [
                "libreoffice", "--headless", "--convert-to", "pdf", 
                docx_path, "--outdir", temp_dir
            ]
            try:
                subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                command[0] = "soffice"
                try:
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except FileNotFoundError:
                    if os.name == 'nt':
                        win_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
                        if os.path.exists(win_path):
                            command[0] = win_path
                            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        else:
                            raise
                    else:
                        raise
        except Exception as e:
            logger.error(f"Failed to run LibreOffice: {e}")
            return None
            
        pdf_path = os.path.join(temp_dir, "temp.pdf")
        if not os.path.exists(pdf_path):
            return None
            
        try:
            doc = fitz.open(pdf_path)
            target_words = target_text.split()
            # Try to match the first few words to be robust against slight formatting changes
            search_string = " ".join(target_words[:10]) if len(target_words) > 10 else target_text
            
            found_page = None
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if search_string in text:
                    found_page = page_num + 1
                    break
                    
            doc.close()
            return found_page
            
        except Exception as e:
            logger.error(f"Failed to read PDF with PyMuPDF: {e}")
            return None

