"""Tests for the token guard utility."""

import pytest
from app.utils.token_guard import truncate_for_api, truncate_body_texts


class TestTruncateForApi:
    """Test single-text truncation."""

    def test_short_text_unchanged(self):
        text = "Hello world"
        assert truncate_for_api(text, max_chars=100) == text

    def test_exact_limit_unchanged(self):
        text = "a" * 100
        assert truncate_for_api(text, max_chars=100) == text

    def test_over_limit_truncated(self):
        text = "a" * 200
        result = truncate_for_api(text, max_chars=100)
        assert len(result) < 200
        assert result.startswith("a" * 100)
        assert "[Content truncated" in result

    def test_empty_string(self):
        assert truncate_for_api("", max_chars=100) == ""

    def test_none_passthrough(self):
        """None should pass through (empty check)."""
        assert truncate_for_api(None, max_chars=100) is None

    def test_default_limit(self):
        """Should use 80k default if not specified."""
        text = "a" * 90000
        result = truncate_for_api(text)
        assert len(result) < 90000


class TestTruncateBodyTexts:
    """Test batch text truncation."""

    def test_within_limits(self):
        texts = ["hello", "world"]
        result = truncate_body_texts(texts, max_per_text=100, max_total=1000)
        assert result == ["hello", "world"]

    def test_per_text_limit(self):
        texts = ["a" * 200, "b" * 200]
        result = truncate_body_texts(texts, max_per_text=50, max_total=10000)
        assert len(result) == 2
        # Each should be truncated to ~50 chars + truncation note
        assert result[0].startswith("a" * 50)

    def test_total_limit_stops_early(self):
        texts = ["a" * 100] * 20
        result = truncate_body_texts(texts, max_per_text=100, max_total=250)
        assert len(result) < 20  # Should stop before processing all

    def test_empty_list(self):
        assert truncate_body_texts([]) == []

    def test_mixed_lengths(self):
        texts = ["short", "a" * 5000, "another"]
        result = truncate_body_texts(texts, max_per_text=100, max_total=10000)
        assert len(result) == 3
        assert result[0] == "short"
