"""Tests for content chunker — chunk-level embeddings and cannibalization."""

import pytest
from app.services.content_chunker import (
    split_into_chunks,
    ContentChunk,
    MIN_CHUNK_WORDS,
    MAX_CHUNK_WORDS,
    SLIDING_WINDOW_WORDS,
    ContentChunkerService,
)


def _words(n: int) -> str:
    """Generate n words of lorem-ish text."""
    base = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua "
    words = (base * ((n // 16) + 2)).split()[:n]
    return " ".join(words)


class TestChunkSplitting:
    """Test the core split_into_chunks function."""

    def test_empty_text_returns_empty(self):
        assert split_into_chunks("") == []
        assert split_into_chunks("   ") == []
        assert split_into_chunks(None) == []

    def test_no_headings_uses_sliding_window(self):
        """Text without headings falls back to sliding window."""
        text = _words(400)
        chunks = split_into_chunks(text)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.heading is None
            assert c.word_count >= MIN_CHUNK_WORDS

    def test_short_text_no_headings_returns_single_chunk(self):
        """Short text without headings that fits in one window."""
        text = _words(100)
        chunks = split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0].word_count >= MIN_CHUNK_WORDS

    def test_h2_splitting(self):
        """Text with H2 headings splits into sections."""
        text = f"""Introduction paragraph with enough words to meet the minimum threshold for chunking.
{_words(50)}

## Email Marketing Basics
{_words(100)}

## Advanced Email Automation
{_words(100)}

## Email Analytics and Reporting
{_words(100)}
"""
        chunks = split_into_chunks(text)
        assert len(chunks) >= 3  # intro + 3 H2 sections (intro might be too small)

        # Check that headings are captured
        headings = [c.heading for c in chunks if c.heading]
        assert "Email Marketing Basics" in headings
        assert "Advanced Email Automation" in headings
        assert "Email Analytics and Reporting" in headings

    def test_h2_heading_levels(self):
        """H2 chunks should have heading_level=2."""
        text = f"""## First Section
{_words(80)}

## Second Section
{_words(80)}
"""
        chunks = split_into_chunks(text)
        for c in chunks:
            if c.heading:
                assert c.heading_level == 2

    def test_h3_subsplitting(self):
        """Large H2 sections get split by H3."""
        text = f"""## Big Section
{_words(100)}

### Subsection A
{_words(200)}

### Subsection B
{_words(200)}
"""
        chunks = split_into_chunks(text)
        # Should have at least the H3 subsections
        h3_chunks = [c for c in chunks if c.heading_level == 3]
        assert len(h3_chunks) >= 2

    def test_tiny_chunks_dropped(self):
        """Chunks below MIN_CHUNK_WORDS are dropped."""
        text = f"""## Real Section
{_words(100)}

## Tiny Section
Just three words.

## Another Real Section
{_words(100)}
"""
        chunks = split_into_chunks(text)
        for c in chunks:
            assert c.word_count >= MIN_CHUNK_WORDS

    def test_chunk_indices_sequential(self):
        """Chunk indices should be sequential starting from 0."""
        text = f"""## Section One
{_words(100)}

## Section Two
{_words(100)}

## Section Three
{_words(100)}
"""
        chunks = split_into_chunks(text)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_intro_chunk_has_no_heading(self):
        """Text before first heading becomes intro chunk with no heading."""
        text = f"""{_words(80)}

## First Section
{_words(100)}
"""
        chunks = split_into_chunks(text)
        intro = chunks[0]
        assert intro.heading is None
        assert intro.heading_level is None

    def test_html_headings(self):
        """HTML h2 tags should be split correctly."""
        text = f"""<h2>Email Marketing</h2>
{_words(100)}

<h2>SEO Strategy</h2>
{_words(100)}
"""
        chunks = split_into_chunks(text)
        headings = [c.heading for c in chunks if c.heading]
        assert "Email Marketing" in headings
        assert "SEO Strategy" in headings

    def test_large_section_sliding_window(self):
        """Sections exceeding MAX_CHUNK_WORDS with no H3 use sliding window."""
        text = f"""## Huge Section
{_words(800)}

## Normal Section
{_words(100)}
"""
        chunks = split_into_chunks(text)
        # The huge section should be split into multiple chunks
        huge_chunks = [c for c in chunks if c.heading == "Huge Section"]
        assert len(huge_chunks) >= 2  # 800 words / 300 window ≈ 3 chunks

    def test_word_count_accuracy(self):
        """Word counts should be accurate."""
        text = f"""## Section
{_words(150)}
"""
        chunks = split_into_chunks(text)
        for c in chunks:
            actual = len(c.body_text.split())
            assert c.word_count == actual

    def test_real_world_blog_post(self):
        """Simulate a real blog post structure."""
        text = f"""The Ultimate Guide to Email Marketing in 2024. This comprehensive guide covers everything you need to know about email marketing. {_words(40)}

## Why Email Marketing Matters
{_words(120)}

## Building Your Email List
{_words(150)}

### Opt-in Forms
{_words(80)}

### Lead Magnets
{_words(80)}

## Email Automation
{_words(100)}

## Measuring Results
{_words(100)}
"""
        chunks = split_into_chunks(text)
        assert len(chunks) >= 4  # intro + 4 major sections
        # Verify all chunks have content
        for c in chunks:
            assert c.body_text.strip()
            assert c.word_count >= MIN_CHUNK_WORDS


class TestContentChunkerService:
    """Test the service class."""

    def test_instantiates(self):
        service = ContentChunkerService()
        assert service is not None

    def test_has_required_methods(self):
        service = ContentChunkerService()
        assert hasattr(service, 'chunk_post')
        assert hasattr(service, 'chunk_site')
        assert hasattr(service, 'embed_chunks')
        assert hasattr(service, 'detect_chunk_cannibalization')


class TestConstants:
    """Verify constants are sensible."""

    def test_min_chunk_words(self):
        assert MIN_CHUNK_WORDS == 50

    def test_max_chunk_words(self):
        assert MAX_CHUNK_WORDS == 500

    def test_sliding_window(self):
        assert SLIDING_WINDOW_WORDS == 300

    def test_max_greater_than_min(self):
        assert MAX_CHUNK_WORDS > MIN_CHUNK_WORDS

    def test_window_greater_than_min(self):
        assert SLIDING_WINDOW_WORDS > MIN_CHUNK_WORDS
