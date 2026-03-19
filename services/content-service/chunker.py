from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from parser import Section

_enc = None


def _get_encoder():
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


@dataclass
class Chunk:
    text: str
    heading: str | None
    token_count: int


def chunk_sections(
    sections: list[Section],
    max_tokens: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """Split sections into token-bounded chunks with overlap."""
    enc = _get_encoder()
    chunks: list[Chunk] = []

    for section in sections:
        text = section.text.strip()
        if not text:
            continue

        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            chunks.append(Chunk(text=text, heading=section.heading, token_count=len(tokens)))
            continue

        # Split into overlapping windows
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = enc.decode(chunk_tokens)
            chunks.append(Chunk(text=chunk_text, heading=section.heading, token_count=len(chunk_tokens)))
            if end == len(tokens):
                break
            start = end - overlap

    return chunks
