"""
Document Parser Module — Unified parsing interface for PDF, Word (.docx), and plain text.

Usage:
    from doc_parser import parse_document

    result = parse_document("path/to/file.pdf")
    result = parse_document("path/to/file.docx")
    result = parse_document("path/to/file.txt")
    result = parse_document(raw_text="Type your task description here")
"""

from doc_parser.models import ParsedDocument
from doc_parser.parser import parse_document

__all__ = ["parse_document", "ParsedDocument"]
