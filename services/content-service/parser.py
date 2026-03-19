from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass
class Section:
    heading: str | None
    text: str


def parse_pdf(file_bytes: bytes) -> list[Section]:
    """Extract text sections from PDF, grouped by headings (font-size delta >= 20%)."""
    import pdfplumber

    sections: list[Section] = []
    current_heading: str | None = None
    current_text_parts: list[str] = []
    current_font_sizes: list[float] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size"]) or []
            if not words:
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(Section(heading=None, text=text.strip()))
                continue

            # Determine body font size (median)
            sizes = [float(w.get("size", 12) or 12) for w in words]
            median_size = sorted(sizes)[len(sizes) // 2]

            for word in words:
                word_size = float(word.get("size", median_size) or median_size)
                word_text = word.get("text", "")
                is_heading = word_size >= median_size * 1.2

                if is_heading:
                    if current_text_parts:
                        sections.append(Section(heading=current_heading, text=" ".join(current_text_parts).strip()))
                        current_text_parts = []
                    current_heading = word_text
                else:
                    current_text_parts.append(word_text)

        if current_text_parts:
            sections.append(Section(heading=current_heading, text=" ".join(current_text_parts).strip()))

    if not sections:
        sections = [Section(heading=None, text="")]
    return sections


def parse_docx(file_bytes: bytes) -> list[Section]:
    """Extract text sections from DOCX, grouped by Heading styles."""
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    sections: list[Section] = []
    current_heading: str | None = None
    current_text_parts: list[str] = []
    heading_styles = {"Heading 1", "Heading 2", "Heading 3"}

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style.name in heading_styles:
            if current_text_parts:
                sections.append(Section(heading=current_heading, text="\n".join(current_text_parts)))
                current_text_parts = []
            current_heading = text
        else:
            current_text_parts.append(text)

    if current_text_parts:
        sections.append(Section(heading=current_heading, text="\n".join(current_text_parts)))

    if not sections:
        sections = [Section(heading=None, text="")]
    return sections
