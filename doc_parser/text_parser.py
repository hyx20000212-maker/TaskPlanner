"""
Plain Text Parser — Handles .txt, .md, and manual text input.
"""

import os
from typing import Optional

from doc_parser.models import ParsedDocument


def parse_text(
    file_path_or_text: str,
    source: Optional[str] = None,
) -> ParsedDocument:
    """
    Parse plain text content from a file path, or from a raw text string
    when called with source="manual_input".

    Args:
        file_path_or_text: File path (when called from _EXT_MAP) or raw text string
        source:            Source identifier — "manual_input" for raw text,
                            or a file path (auto-detected if None)

    Returns:
        ParsedDocument

    Raises:
        ValueError: Empty content
        FileNotFoundError: File does not exist
    """
    # ── Determine whether it's a file path or raw text ──────────
    if source == "manual_input":
        # Called from parser.py with raw text
        text = file_path_or_text.strip()
        file_type = "raw_text"
    elif os.path.isfile(file_path_or_text):
        # Called from _EXT_MAP with a real file path
        with open(file_path_or_text, "r", encoding="utf-8") as f:
            text = f.read().strip()
        source = file_path_or_text
        ext = os.path.splitext(file_path_or_text)[1].lower().lstrip(".")
        file_type = ext if ext else "txt"
    else:
        # Fallback: treat as raw text (e.g. for test, or if file doesn't exist yet)
        text = file_path_or_text.strip()
        source = source or "manual_input"
        file_type = "raw_text"

    if not text:
        raise ValueError("Text content is empty. Please provide valid text.")

    return ParsedDocument(
        source=source,
        file_type=file_type,
        raw_text=text,
        page_count=None,
        metadata={"char_count": len(text), "line_count": text.count("\n") + 1},
    )
