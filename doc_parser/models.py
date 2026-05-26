"""Data models for the document parser module."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedDocument:
    """Structured representation of a parsed document."""
    source: str                         # File path or "manual_input"
    file_type: str                      # pdf / docx / txt / raw_text
    raw_text: str                       # Full extracted text
    page_count: Optional[int] = None    # Page count (PDF only)
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        preview = self.raw_text[:80].replace("\n", " ") + ("..." if len(self.raw_text) > 80 else "")
        return (f"ParsedDocument(source={self.source!r}, type={self.file_type}, "
                f"pages={self.page_count}, text_preview={preview!r})")
