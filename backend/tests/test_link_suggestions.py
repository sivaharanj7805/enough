"""Tests for automated internal link suggestion engine."""

import pytest
from uuid import uuid4
from app.services.link_suggestions import (
    extract_keywords,
    generate_anchor_text,
    LinkSuggestionEngine,
    LinkSuggestion,
    MAX_SUGGESTIONS_PER_POST,
    MIN_SIMILARITY_FOR_LINK,
    MAX_SIMILARITY_FOR_CROSS,
)


class TestExtractKeywords:
    """Test keyword extraction."""

    def test_basic_extraction(self):
        text = "email marketing automation helps businesses grow their email list"
        kws = extract_keywords(text)
        assert "email" in kws
        assert "marketing" in kws
        assert "automation" in kws

    def test_removes_stop_words(self):
        text = "the best way to do email marketing is with automation tools"
        kws = extract_keywords(text)
        assert "the" not in kws
        assert "with" not in kws

    def test_empty_text(self):
        assert extract_keywords("") == []
        assert extract_keywords(None) == []

    def test_respects_top_n(self):
        text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 " * 3
        kws = extract_keywords(text, top_n=5)
        assert len(kws) <= 5

    def test_frequency_ordering(self):
        """Most frequent keywords should come first."""
        text = "email email email email seo seo marketing"
        kws = extract_keywords(text, top_n=3)
        assert kws[0] == "email"  # Most frequent


class TestGenerateAnchorText:
    """Test anchor text generation."""

    def test_shared_keyword_in_title(self):
        """Should use phrase from title containing shared keyword."""
        anchor = generate_anchor_text(
            source_keywords=["email", "marketing", "automation"],
            target_title="Complete Email Marketing Guide for 2024",
            shared_keywords=["email", "marketing"],
        )
        assert len(anchor) > 0
        assert len(anchor.split()) <= 5

    def test_fallback_to_shared_keywords(self):
        """When no keyword in title, use shared keywords."""
        anchor = generate_anchor_text(
            source_keywords=["python", "django"],
            target_title="How to Build a Web App",
            shared_keywords=["python", "django"],
        )
        assert "python" in anchor or "django" in anchor

    def test_fallback_to_title(self):
        """When no shared keywords, use shortened title."""
        anchor = generate_anchor_text(
            source_keywords=["unrelated"],
            target_title="The Ultimate Guide to Everything",
            shared_keywords=[],
        )
        assert len(anchor) > 0

    def test_short_title_used_as_is(self):
        anchor = generate_anchor_text(
            source_keywords=[],
            target_title="SEO Tips",
            shared_keywords=[],
        )
        assert anchor == "seo tips"


class TestLinkSuggestionEngine:
    """Test the engine class."""

    def test_instantiates(self):
        engine = LinkSuggestionEngine()
        assert engine is not None

    def test_has_generate_method(self):
        engine = LinkSuggestionEngine()
        assert hasattr(engine, 'generate_suggestions')


class TestLinkSuggestionDataclass:
    """Test the LinkSuggestion dataclass."""

    def test_creates_correctly(self):
        s = LinkSuggestion(
            source_post_id=uuid4(),
            source_title="How to Send Emails",
            target_post_id=uuid4(),
            target_title="Email Deliverability Guide",
            target_url="/email-deliverability",
            similarity=0.42,
            suggested_anchor_text="email deliverability",
            reason="Cross-cluster link",
            source_cluster="Email Marketing",
            target_cluster="Technical Email",
            priority="high",
        )
        assert s.similarity == 0.42
        assert s.priority == "high"
        assert s.suggested_anchor_text == "email deliverability"


class TestConstants:
    """Verify configuration constants."""

    def test_max_suggestions(self):
        assert MAX_SUGGESTIONS_PER_POST == 5

    def test_similarity_range(self):
        assert MIN_SIMILARITY_FOR_LINK < MAX_SIMILARITY_FOR_CROSS
        assert MIN_SIMILARITY_FOR_LINK > 0
        assert MAX_SIMILARITY_FOR_CROSS < 1.0
