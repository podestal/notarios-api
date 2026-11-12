"""PDF text extraction via pdfplumber (digital SUNARP boletas)."""

from __future__ import annotations

from pathlib import Path
from typing import Union


def extract_pdf_text(source: Union[str, Path, bytes]) -> str:
    """
    Extract plain text from a digital PDF.

    For scanned/image-only PDFs this returns little text; OCR can be added later.
    """
    import pdfplumber

    pages: list[str] = []
    if isinstance(source, (bytes, bytearray)):
        import io

        opener = pdfplumber.open(io.BytesIO(source))
    else:
        opener = pdfplumber.open(str(source))

    with opener as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
    return "\n\n".join(pages).strip()
