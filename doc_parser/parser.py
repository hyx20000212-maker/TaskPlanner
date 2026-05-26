"""
Unified parsing entry point — auto-detects file type and routes to the correct parser.
"""

import os
from typing import Optional

from doc_parser.models import ParsedDocument
from doc_parser.pdf_parser import parse_pdf
from doc_parser.word_parser import parse_docx
from doc_parser.text_parser import parse_text


# ── File extension → parser function ───────────────────────────────
_EXT_MAP = {
    ".pdf":  parse_pdf,
    ".docx": parse_docx,
    ".txt":  parse_text,
    ".md":   parse_text,
    ".text": parse_text,
    "":      parse_text,   # No extension → treat as plain text
}


def _get_file_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return ext.lstrip(".") if ext else "txt"


def parse_document(
    file_path: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> ParsedDocument:
    """
    Unified document parsing entry point.

    Args:
        file_path: Path to the file (.pdf / .docx / .txt / .md)
        raw_text:  Raw text string (use when no file is provided)

    Returns:
        ParsedDocument: Structured parsed document

    Raises:
        ValueError: Both file_path and raw_text provided, or unsupported file type
        FileNotFoundError: File does not exist
    """
    # ── Parameter validation ────────────────────────────────────────
    if raw_text is not None and file_path is not None:
        raise ValueError("Provide either file_path or raw_text, not both")

    if raw_text is not None:
        return parse_text(raw_text.strip(), source="manual_input")

    if file_path is None:
        raise ValueError("Either file_path or raw_text is required")

    # ── Route to parser (check extension before file existence) ─────
    ext = os.path.splitext(file_path)[1].lower()
    parser_fn = _EXT_MAP.get(ext)

    if parser_fn is None:
        supported = ", ".join(sorted(k for k in _EXT_MAP if k))
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {supported}")

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    return parser_fn(file_path)


# ── CLI test entry ─────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <file_path>")
        print("  or:  python parser.py --text \"your text here\"")
        sys.exit(1)

    if sys.argv[1] == "--text":
        text = " ".join(sys.argv[2:])
        doc = parse_document(raw_text=text)
    else:
        doc = parse_document(sys.argv[1])

    print(doc)
    print("\n─── Extracted Text ───")
    print(doc.raw_text)
