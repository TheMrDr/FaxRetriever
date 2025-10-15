"""
Utility functions for document conversion, normalization, and cover sheet generation.
Used during manual faxing and inbound fax processing.
"""

import datetime
import os
import shutil
import tempfile

from pypdf import PdfReader, PdfWriter

from utils.logging_utils import get_logger
from PIL import Image, ImageDraw, ImageFont

# Try to use reportlab for PDF generation when available
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

log = get_logger("doc_utils")

# Allowed file types (no conversion)
SUPPORTED_TYPES = ('.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.doc', '.docx', '.html', '.txt')

def is_supported_filetype(filepath):
    return filepath.lower().endswith(SUPPORTED_TYPES)


def normalize_orientation(input_path):
    """
    Ensures all pages are portrait oriented and sized to US Letter.
    Only applicable to PDF.

    Args:
        input_path (str): Original file path

    Returns:
        str: Path to orientation-normalized copy (temp file)
    """
    ext = os.path.splitext(input_path)[1].lower()
    if ext != ".pdf":
        log.debug(f"Skipping orientation normalization for non-PDF: {input_path}")
        return copy_to_temp(input_path)

    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if width > height:
                page.rotate(90)
            writer.add_page(page)

        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(temp_path, "wb") as f:
            writer.write(f)

        return temp_path
    except Exception as e:
        log.error(f"Failed to normalize orientation for {input_path}: {e}")
        return copy_to_temp(input_path)


def copy_to_temp(original_path):
    """
    Copies any file to a uniquely-named temp file for fax transmission use.

    Args:
        original_path (str): Source file

    Returns:
        str: Temp file path
    """
    try:
        ext = os.path.splitext(original_path)[1].lower()
        fd, temp_path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        shutil.copy2(original_path, temp_path)
        return temp_path
    except Exception as e:
        log.error(f"Failed to copy to temp: {original_path}: {e}")
        return None

def normalize_document(input_path):
    """
    Validates support and ensures portrait orientation. All files copied to temp.

    Args:
        input_path (str): Path to original file

    Returns:
        str: Path to temp-normalized file, or None on failure
    """
    if not is_supported_filetype(input_path):
        log.warning(f"Unsupported file type: {input_path}")
        return None

    ext = os.path.splitext(input_path)[1].lower()

    try:
        with open(input_path, "rb") as test:
            test.read(1024)
    except Exception as verify_error:
        log.error(f"File unreadable or corrupt: {input_path}: {verify_error}")
        return None

    if ext in (".doc", ".docx"):
        log.warning(f"User uploaded Word document: {input_path}. Cannot enforce orientation.")

    if ext == ".pdf":
        return normalize_orientation(input_path)
    else:
        return copy_to_temp(input_path)


def convert_image_to_pdf(image_path, output_path):
    """
    Converts a single image file to a 1-page PDF.

    Args:
        image_path (str): Path to the image file
        output_path (str): Path where resulting PDF should be written

    Returns:
        str: Output PDF path
    """
    try:
        from PIL import Image
        image = Image.open(image_path)
        rgb_image = image.convert('RGB')
        rgb_image.save(output_path, "PDF", resolution=300.0)
        return output_path
    except Exception as e:
        log.error(f"Image to PDF conversion failed: {e}")
        return None


def normalize_pdf(input_path):
    """
    Returns a normalized PDF path (copies or flattens input) into a temporary file.
    - If the file is not a PDF, returns the original path unchanged.
    - If normalization fails for any reason, returns the original path unchanged.

    Args:
        input_path (str): Path to original file

    Returns:
        str: Path to a valid PDF. This may be a temp file when input is a PDF.
    """
    if not input_path or not input_path.lower().endswith(".pdf"):
        log.warning("Non-PDF passed to normalize_pdf")
        return input_path

    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        fd, normalized_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(normalized_path, "wb") as f:
            writer.write(f)

        return normalized_path
    except Exception as e:
        log.error(f"Failed to normalize PDF: {e}")
        return input_path


def generate_cover_pdf(attn: str, memo: str, *, base_dir: str | None = None) -> str | None:
    """Generate a professional one-page cover PDF.

    Returns temp filepath or None if ReportLab is unavailable or an error occurs.
    """
    if not REPORTLAB_AVAILABLE:
        log.warning("ReportLab not available; cannot generate cover PDF.")
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        c = canvas.Canvas(path, pagesize=letter)
        width, height = letter

        # Header block (kept generic; UI has richer designer but this is a safe fallback)
        top = height - 0.9 * inch
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width / 2.0, top, "FAX COVER SHEET")

        c.setFont("Helvetica", 12)
        center_y = height / 2.0
        c.drawCentredString(width / 2.0, center_y + 0.2 * inch, f"To / Attn: {attn or ''}")
        c.drawCentredString(width / 2.0, center_y - 0.1 * inch, f"Memo: {memo or ''}")

        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(
            width / 2.0, 0.75 * inch, "The remainder of this page is intentionally left blank."
        )

        c.showPage()
        c.save()
        return path
    except Exception as e:
        log.error(f"Failed to generate cover PDF: {e}")
        return None


def generate_cover_pdf_with_multipart_note(
    attn: str,
    memo: str,
    *,
    session_idx: int,
    session_total: int,
    base_dir: str | None = None,
) -> str | None:
    """Generate a cover PDF with an extra multi-part note line.

    Example note: "Multi-part Fax — Session {i} of {N}".
    """
    if not REPORTLAB_AVAILABLE:
        log.warning("ReportLab not available; cannot generate cover-with-note PDF.")
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        c = canvas.Canvas(path, pagesize=letter)
        width, height = letter

        top = height - 0.9 * inch
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width / 2.0, top, "FAX COVER SHEET")

        c.setFont("Helvetica", 12)
        center_y = height / 2.0
        c.drawCentredString(width / 2.0, center_y + 0.25 * inch, f"To / Attn: {attn or ''}")
        c.drawCentredString(width / 2.0, center_y - 0.05 * inch, f"Memo: {memo or ''}")

        # Multi-part note just below Memo
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(
            width / 2.0,
            center_y - 0.35 * inch,
            f"Multi-part Fax — Session {max(1, int(session_idx))} of {max(1, int(session_total))}",
        )

        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(
            width / 2.0, 0.75 * inch, "The remainder of this page is intentionally left blank."
        )

        c.showPage()
        c.save()
        return path
    except Exception as e:
        log.error(f"Failed to generate cover-with-note PDF: {e}")
        return None


def generate_continuation_pdf(*, session_idx: int, session_total: int, base_dir: str | None = None) -> str | None:
    """Generate a compact 1-page continuation indicator PDF.

    Text: "Continuation — Session {i} of {N}" (centered).
    """
    if not REPORTLAB_AVAILABLE:
        log.warning("ReportLab not available; cannot generate continuation PDF.")
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        c = canvas.Canvas(path, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(
            width / 2.0,
            height / 2.0,
            f"Continuation — Session {max(1, int(session_idx))} of {max(1, int(session_total))}",
        )
        c.showPage()
        c.save()
        return path
    except Exception as e:
        log.error(f"Failed to generate continuation PDF: {e}")
        return None


# Deprecated shim retained for backward compatibility

def generate_cover_sheet_pdf(recipient: str, user_fax: str, output_path: str):
    """
    Deprecated in v2: Cover sheets are now generated exclusively by the Cover Sheet designer (UI)
    and inserted into the attachment list by SendFaxPanel. This utility no longer creates files.

    Returns:
        None: Always returns None and does not write a file.
    """
    try:
        log.info("generate_cover_sheet_pdf is deprecated; using designer-provided cover if enabled.")
    except Exception:
        pass
    return None
