"""
PDF Parser — Extracts text from PDF files using PyMuPDF (fitz).
"""

import fitz  # PyMuPDF

from doc_parser.models import ParsedDocument


def parse_pdf(file_path: str) -> ParsedDocument:
    """
    Parse a PDF file, extracting text page by page.

    Args:
        file_path: Path to the PDF file

    Returns:
        ParsedDocument with full text and page count

    Raises:
        ValueError: PDF cannot be opened or is encrypted
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}") from e

    if doc.is_encrypted:
        doc.close()
        raise ValueError("PDF is encrypted. Please provide an unencrypted PDF.")

    pages_text: list[str] = []
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        if text.strip():
            pages_text.append(text.strip())

    page_count = doc.page_count
    doc.close()

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        raise ValueError(
            "No text extracted from PDF. This may be a scanned/image-based PDF. "
            "OCR is not yet supported — please convert to a searchable PDF first."
        )

    return ParsedDocument(
        source=file_path,
        file_type="pdf",
        raw_text=full_text,
        page_count=page_count,
        metadata={"pages_with_text": len(pages_text)},
    )
