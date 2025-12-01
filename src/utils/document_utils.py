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



# ---- New utility: Convert PDF to JPG pages ----

def convert_pdf_to_jpgs(input_pdf: str, output_dir: str, *, dpi: int = 200, quality: int = 90, poppler_path: str | None = None) -> list[str] | dict:
    """
    Convert a PDF file to JPEG images, one per page.

    Args:
        input_pdf: Path to source PDF.
        output_dir: Directory to write JPEG pages.
        dpi: Render DPI for conversion.
        quality: JPEG quality (1-95 typical).
        poppler_path: Optional path to Poppler "bin" directory for pdf2image.

    Returns:
        list[str]: Paths to written JPEG files, on success.
        dict: {"error": "..."} on failure.
    """
    try:
        if not os.path.isfile(input_pdf):
            return {"error": f"Missing file: {input_pdf}"}
        os.makedirs(output_dir, exist_ok=True)

        # Helper: save PIL Images to JPGs with naming
        def _save_pages(pil_pages: list["Image.Image"]) -> list[str] | dict:
            base = os.path.splitext(os.path.basename(input_pdf))[0]
            written: list[str] = []
            idx = 1
            for img in pil_pages:
                try:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    out_name = f"{base}_p{idx:03}.jpg"
                    out_path = os.path.join(output_dir, out_name)
                    img.save(out_path, "JPEG", quality=max(1, min(int(quality), 95)))
                    written.append(out_path)
                    idx += 1
                except Exception as e:
                    log.exception(f"Failed to save page {idx} for {input_pdf}: {e}")
            if not written:
                return {"error": "Failed to write any pages."}
            return written

        # Backend 1: PyMuPDF (fitz) if available — avoids Poppler dependency
        try:
            import fitz  # PyMuPDF
            from PIL import Image as _PILImage
            zoom = max(1.0, float(dpi) / 72.0)
            doc = fitz.open(input_pdf)
            pil_pages = []
            for i in range(doc.page_count):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                # Build PIL Image from pixmap buffer
                img = _PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pil_pages.append(img)
            if pil_pages:
                result = _save_pages(pil_pages)
                if isinstance(result, list):
                    log.info(f"Converted PDF to JPGs using PyMuPDF: {input_pdf} -> {len(result)} pages at {dpi} DPI")
                return result
        except Exception as e:
            # Fall through to pdf2image/Poppler
            try:
                log.debug(f"PyMuPDF not used for conversion (will try pdf2image): {e}")
            except Exception:
                pass

        # Backend 2: pdf2image + Poppler
        try:
            from pdf2image import convert_from_path
            from pdf2image.exceptions import PDFInfoNotInstalledError
        except Exception as e:
            log.error(f"pdf2image import failed: {e}")
            return {"error": "Conversion backend not available (PyMuPDF/pdf2image missing). Please install dependencies."}

        # Resolve Poppler path if not provided
        def _resolve_poppler_dir(user_path: str | None) -> tuple[str | None, list[str]]:
            checked: list[str] = []
            if user_path and os.path.isdir(user_path):
                return user_path, checked
            # environment hints
            for env_key in ("POPPLER_PATH", "POPPLER_BIN", "POPPLER_HOME"):
                p = os.environ.get(env_key)
                if p:
                    checked.append(f"env:{env_key}={p}")
                    if os.path.isdir(p):
                        return p, checked
            # MEIPASS (PyInstaller onefile)
            try:
                import sys
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    cand = os.path.join(meipass, "poppler", "bin")
                    checked.append(cand)
                    if os.path.isdir(cand):
                        return cand, checked
            except Exception:
                pass
            # repo/process-relative candidates
            try:
                here = os.path.abspath(os.path.dirname(__file__))
                # project root is two levels up from src/utils
                root = os.path.abspath(os.path.join(here, "..", ".."))
                for base in (root, os.getcwd(), os.path.dirname(os.path.abspath(__import__('sys').executable))):
                    cand = os.path.join(base, "poppler", "bin")
                    checked.append(cand)
                    if os.path.isdir(cand):
                        return cand, checked
            except Exception:
                pass
            return None, checked

        resolved_poppler, checked_list = _resolve_poppler_dir(poppler_path)
        kwargs: dict = {"dpi": int(dpi)}
        if resolved_poppler:
            kwargs["poppler_path"] = resolved_poppler
        try:
            pages = convert_from_path(input_pdf, **kwargs)
        except Exception as e:
            # Specific message when Poppler is missing
            try:
                from pdf2image.exceptions import PDFInfoNotInstalledError
            except Exception:
                PDFInfoNotInstalledError = Exception  # type: ignore
            if isinstance(e, PDFInfoNotInstalledError):
                msg = (
                    "Poppler not found. Unable to get page count. "
                    "Ensure Poppler is installed or bundled. The app looks for 'poppler\\bin' in these locations: "
                    + "; ".join(checked_list)
                )
                log.error(msg)
                return {"error": msg}
            # Any other error
            log.exception(f"pdf2image conversion failed for {input_pdf}: {e}")
            return {"error": str(e)}

        if not pages:
            return {"error": "No pages rendered (empty PDF or conversion failure)."}

        # Ensure PIL.Image for saving
        from PIL import Image as _Image
        pil_pages: list[_Image.Image] = []
        for p in pages:
            pil_pages.append(p if hasattr(p, "save") else _Image.fromarray(p))

        result = _save_pages(pil_pages)
        if isinstance(result, list):
            backend = f"pdf2image (Poppler at {resolved_poppler})" if resolved_poppler else "pdf2image (system Poppler)"
            log.info(f"Converted PDF to JPGs using {backend}: {input_pdf} -> {len(result)} pages at {dpi} DPI")
        return result
    except Exception as e:
        log.exception(f"Unhandled error converting PDF to JPG: {input_pdf}: {e}")
        return {"error": str(e)}
