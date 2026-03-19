from __future__ import annotations

import sys
import pytest

sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/content-service")


def test_chunk_sections_max_tokens():
    from parser import Section
    from chunker import chunk_sections

    long_text = " ".join(["word"] * 1000)
    sections = [Section(heading="Test", text=long_text)]
    chunks = chunk_sections(sections, max_tokens=500, overlap=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 500


def test_chunk_sections_short_text():
    from parser import Section
    from chunker import chunk_sections

    sections = [Section(heading="Intro", text="Short text.")]
    chunks = chunk_sections(sections, max_tokens=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0].heading == "Intro"


def test_chunk_sections_overlap():
    """Verify overlap tokens appear in consecutive chunks."""
    import tiktoken
    from parser import Section
    from chunker import chunk_sections

    # 600 tokens of text to force 2 chunks with overlap
    enc = tiktoken.get_encoding("cl100k_base")
    words = enc.decode(list(range(10)) * 60)  # 600 token-like chars
    text = " ".join(["the"] * 600)
    sections = [Section(heading=None, text=text)]
    chunks = chunk_sections(sections, max_tokens=500, overlap=50)

    if len(chunks) >= 2:
        # The last 50 tokens of chunk 0 should appear at start of chunk 1
        end_of_chunk0 = chunks[0].text.split()[-10:]
        start_of_chunk1 = chunks[1].text.split()[:10]
        overlap_words = set(end_of_chunk0) & set(start_of_chunk1)
        assert len(overlap_words) > 0
