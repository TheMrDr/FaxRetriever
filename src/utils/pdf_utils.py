"""
PDF utility helpers for FaxRetriever (Sprint 7)

- split_pdf_pages(pdf_bytes: bytes) -> list[bytes]
  Splits a PDF into single-page PDF byte blobs. Uses PyMuPDF (fitz), which is
  already a project dependency for rendering, to avoid introducing new
  dependencies. If splitting fails, returns an empty list.

Notes
- This module must not log PHI. It performs no logging.
- Callers should handle errors by checking for empty return values.
"""
from __future__ import annotations

from typing import List


def split_pdf_pages(pdf_bytes: bytes) -> List[bytes]:
    """Split a PDF into one single-page PDF bytes per page.

    Returns an empty list on failure. On success, returns a list whose length
    equals the number of pages in the input document.
    """
    if not pdf_bytes:
        return []
    try:
        import fitz  # PyMuPDF
    except Exception:
        # PyMuPDF not available; cannot split
        return []

    try:
        src = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return []

    try:
        out_parts: List[bytes] = []
        for page_index in range(src.page_count):
            try:
                # Create a new one-page document and copy the page content
                dst = fitz.open()
                dst.insert_pdf(src, from_page=page_index, to_page=page_index)
                out_parts.append(dst.tobytes())
                dst.close()
            except Exception:
                # If any page fails, abort and return empty to signal error
                try:
                    dst.close()  # type: ignore[name-defined]
                except Exception:
                    pass
                src.close()
                return []
        src.close()
        return out_parts
    except Exception:
        try:
            src.close()
        except Exception:
            pass
        return []
